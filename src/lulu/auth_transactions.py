"""Ephemeral provider authentication transactions.

Transactions contain only handoff metadata. Provider tokens and refresh
material remain in the provider's private store or SecretStore.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import StrEnum
import secrets
import threading
import time
from typing import Any


class AuthTransactionState(StrEnum):
    SIGNED_OUT = "signed_out"
    WAITING_FOR_USER = "waiting_for_user"
    WAITING_FOR_2FA = "waiting_for_2fa"
    EXCHANGING_TOKEN = "exchanging_token"
    AUTHENTICATED = "authenticated"
    EXPIRED = "expired"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(slots=True)
class AuthTransaction:
    provider: str
    transaction_id: str
    auth_method: str
    state: AuthTransactionState
    verification_url: str = ""
    user_code: str = ""
    qr_payload: str = ""
    expiry: float = 0.0
    error: str = ""

    def public(self) -> dict[str, object]:
        value = asdict(self)
        value["state"] = self.state.value
        value["expires_in"] = max(0, int(self.expiry - time.time())) if self.expiry else 0
        value.pop("expiry", None)
        return value


class AuthTransactionStore:
    """Thread-safe in-memory transaction store shared by Admin/OOBE callers."""

    def __init__(self, ttl: int = 600) -> None:
        self.ttl = ttl
        self._items: dict[str, AuthTransaction] = {}
        self._lock = threading.RLock()

    def create(self, provider: str, auth_method: str, **handoff: str) -> AuthTransaction:
        now = time.time()
        item = AuthTransaction(provider, secrets.token_urlsafe(24), auth_method,
                               AuthTransactionState.WAITING_FOR_USER,
                               expiry=now + self.ttl, **handoff)
        with self._lock:
            self._purge_locked(now)
            self._items[item.transaction_id] = item
        return item

    def get(self, transaction_id: str) -> AuthTransaction | None:
        with self._lock:
            self._purge_locked(time.time())
            return self._items.get(transaction_id)

    def update(self, transaction_id: str, state: AuthTransactionState, *,
               error: str = "") -> AuthTransaction:
        with self._lock:
            item = self._items[transaction_id]
            item.state = state
            item.error = error
            return item

    def remove(self, transaction_id: str) -> None:
        with self._lock:
            self._items.pop(transaction_id, None)

    def _purge_locked(self, now: float) -> None:
        for key, item in tuple(self._items.items()):
            if item.expiry and item.expiry <= now:
                item.state = AuthTransactionState.EXPIRED
