"""Generic controller-facing credential and challenge state.

The broker owns ephemeral request state only. It never persists values and its
public snapshots intentionally contain metadata, not submitted credentials.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
import asyncio
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import tempfile
from uuid import uuid4

from .paths import PATHS


class CredentialInput(StrEnum):
    TEXT = "text"
    SECRET = "secret"
    CODE = "code"
    CHOICE = "choice"
    WAITING = "waiting"
    INFO = "info"


class CredentialStatus(StrEnum):
    REQUESTED = "requested"
    SUBMITTED = "submitted"
    WAITING = "waiting"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(frozen=True, slots=True)
class CredentialRequest:
    request_id: str
    title: str
    prompt: str
    input_type: CredentialInput
    secret: bool = False
    min_length: int = 0
    max_length: int = 4096
    choices: tuple[str, ...] = ()
    help_text: str = ""
    owner_id: str = ""
    owner: dict[str, object] = field(default_factory=dict)
    multiline: bool = False


@dataclass(slots=True)
class CredentialSession:
    request: CredentialRequest
    status: CredentialStatus = CredentialStatus.REQUESTED
    message: str = ""
    _value: str | None = field(default=None, repr=False)

    def public_state(self) -> dict[str, object]:
        return {"id": self.request.request_id, "title": self.request.title,
                "prompt": self.request.prompt, "input_type": self.request.input_type.value,
                "secret": self.request.secret, "min_length": self.request.min_length,
                "max_length": self.request.max_length, "choices": self.request.choices,
                "help_text": self.request.help_text, "status": self.status.value,
                "message": self.message, "owner_id": self.request.owner_id,
                "owner": self.request.owner, "multiline": self.request.multiline}


class CredentialBroker:
    """One active controller credential request with explicit lifecycle."""

    def __init__(self) -> None:
        self._active: CredentialSession | None = None
        self._lock = asyncio.Lock()
        self._changed = asyncio.Event()

    @property
    def active(self) -> CredentialSession | None:
        return self._active

    async def request(self, title: str, prompt: str, input_type: CredentialInput,
                      *, secret: bool = False, min_length: int = 0,
                      max_length: int = 4096, choices: tuple[str, ...] = (),
                      help_text: str = "", owner_id: str = "",
                      owner: dict[str, object] | None = None,
                      multiline: bool = False) -> CredentialSession:
        async with self._lock:
            if self._active is not None and self._active.status in {
                    CredentialStatus.REQUESTED, CredentialStatus.WAITING}:
                raise RuntimeError("another credential request is active")
            if input_type is CredentialInput.SECRET:
                secret = True
            request = CredentialRequest(uuid4().hex, title, prompt, input_type, secret,
                                         min_length, max_length, choices, help_text,
                                          owner_id, dict(owner or {}), multiline)
            self._active = CredentialSession(request)
            self._changed.set()
            return self._active

    async def submit(self, request_id: str, value: str) -> CredentialSession:
        async with self._lock:
            session = self._require(request_id)
            if session.status not in {CredentialStatus.REQUESTED, CredentialStatus.WAITING}:
                raise ValueError("credential request is not accepting input")
            if not session.request.min_length <= len(value) <= session.request.max_length:
                raise ValueError("credential value length is invalid")
            if session.request.choices and value not in session.request.choices:
                raise ValueError("credential choice is invalid")
            session._value = value
            session.status = CredentialStatus.SUBMITTED
            self._changed.set()
            return session

    async def take_value(self, request_id: str) -> str:
        async with self._lock:
            session = self._require(request_id)
            value = session._value
            session._value = None
            return value or ""

    async def wait_for_submission(self, request_id: str) -> str:
        while True:
            async with self._lock:
                session = self._require(request_id)
                if session.status is CredentialStatus.SUBMITTED:
                    value = session._value or ""
                    session._value = None
                    return value
                if session.status in {CredentialStatus.CANCELLED, CredentialStatus.FAILED}:
                    raise RuntimeError("credential request ended")
                self._changed.clear()
            try:
                await asyncio.wait_for(self._changed.wait(), timeout=0.5)
            except asyncio.TimeoutError:
                pass

    async def update(self, request_id: str, status: CredentialStatus, message: str = "") -> None:
        async with self._lock:
            session = self._require(request_id)
            session.status = status
            session.message = message
            self._changed.set()

    async def cancel(self, request_id: str) -> None:
        await self.update(request_id, CredentialStatus.CANCELLED)

    async def withdraw(self, request_id: str, owner_id: str = "",
                       message: str = "") -> None:
        async with self._lock:
            session = self._require(request_id)
            if owner_id and session.request.owner_id != owner_id:
                raise PermissionError("credential request owner mismatch")
            if session.status in {CredentialStatus.REQUESTED, CredentialStatus.WAITING,
                                  CredentialStatus.SUBMITTED}:
                session.status = CredentialStatus.CANCELLED
                session.message = message or "credential request owner ended"
                session._value = None
                self._changed.set()

    def _require(self, request_id: str) -> CredentialSession:
        if self._active is None or self._active.request.request_id != request_id:
            raise KeyError("unknown credential request")
        return self._active

    def state(self) -> dict[str, object]:
        return self._active.public_state() if self._active is not None else {"status": "idle"}


class SecretStore:
    """Mudos-owned secret storage backed by systemd-creds.

    Only the configured bit and backend are exposed to callers that serve UI.
    Values are decrypted into a short-lived subprocess pipe and are never
    written to plugin TOML, environment, argv, or logs. ``host+tpm2`` is
    attempted first; the host-key backend is the fallback for hardware without
    a usable TPM2.
    """

    def __init__(self, root: Path | None = None, *, creds: str = "systemd-creds") -> None:
        self.root = root or (PATHS.data_root / "secrets")
        self.creds = creds

    def _path(self, namespace: str, name: str) -> Path:
        namespace_parts = namespace.split("/") if namespace else []
        if (not namespace_parts or not name
                or any(not part or part in {".", ".."} or "\\" in part or "\0" in part
                       for part in namespace_parts)
                or any(part in {".", ".."} or "\0" in part for part in name.split("/"))
                or "/" in name or "\\" in name):
            raise ValueError("invalid secret name")
        return self.root / namespace / f"{name}.cred"

    def backend(self, namespace: str, name: str) -> str | None:
        path = self._path(namespace, name)
        if not path.is_file():
            return None
        return "systemd-creds"

    def configured(self, namespace: str, name: str) -> bool:
        return self._path(namespace, name).is_file()

    def put(self, namespace: str, name: str, value: str) -> None:
        if not value:
            raise ValueError("secret cannot be empty")
        destination = self._path(namespace, name)
        destination.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
        os.chmod(destination.parent, 0o700)
        with tempfile.TemporaryDirectory(prefix="mudos-secret-") as temporary:
            plain = Path(temporary) / "input"
            encrypted = Path(temporary) / "output"
            plain.write_text(value)
            os.chmod(plain, 0o600)
            credential_name = f"{name}.cred"
            command = [self.creds, "encrypt", "--user", f"--name={credential_name}", "--with-key=host+tpm2",
                       str(plain), str(encrypted)]
            result = subprocess.run(command, stdin=subprocess.DEVNULL,
                                    stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                                    text=True, check=False)
            if result.returncode != 0:
                # TPM2 is preferred, not mandatory. Host binding still avoids
                # plaintext-at-rest and works on machines without TPM support.
                subprocess.run([self.creds, "encrypt", "--user", f"--name={credential_name}", "--with-key=host",
                                str(plain), str(encrypted)], stdin=subprocess.DEVNULL,
                                stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                                check=True)
            os.chmod(encrypted, 0o600)
            temporary_destination = destination.with_name(f".{destination.name}.{secrets.token_hex(8)}")
            # systemd-creds uses a temporary filesystem for the input/output
            # staging area on some appliances, so os.replace() cannot cross
            # that mount boundary. Copy into the protected destination
            # directory, then atomically rename within that directory.
            shutil.copyfile(encrypted, temporary_destination)
            encrypted.unlink()
            os.chmod(temporary_destination, 0o600)
            os.replace(temporary_destination, destination)

    def get(self, namespace: str, name: str) -> str | None:
        path = self._path(namespace, name)
        if not path.is_file():
            return None
        with tempfile.TemporaryDirectory(prefix="mudos-secret-read-") as temporary:
            output = Path(temporary) / path.name
            result = subprocess.run([self.creds, "decrypt", "--user", str(path), str(output)],
                                    stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                    stderr=subprocess.PIPE, check=False)
            if result.returncode != 0:
                return None
            return output.read_text().rstrip("\n")

    def clear(self, namespace: str, name: str) -> None:
        self._path(namespace, name).unlink(missing_ok=True)
