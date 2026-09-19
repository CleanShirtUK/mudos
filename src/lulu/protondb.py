"""Best-effort ProtonDB summary adapter keyed strictly by Steam AppID."""

from __future__ import annotations

import json
import logging
from typing import Callable
from urllib.request import Request, urlopen

from .provider_config import ProviderConfigurationService


LOGGER = logging.getLogger("lulu.protondb")
TIERS = {"native", "platinum", "gold", "silver", "bronze", "borked", "unknown"}


class ProtonDBError(RuntimeError):
    pass


class ProtonDBClient:
    def __init__(self, config: ProviderConfigurationService | None = None,
                 request: Callable[[Request, float], tuple[int, bytes]] | None = None) -> None:
        self.config = (config or ProviderConfigurationService.from_environment()).provider("metadata.protondb")
        self.endpoint = str(self.config.get("endpoint", "https://www.protondb.com/api/v1/reports/summaries")).rstrip("/")
        try:
            self.timeout = float(self.config.get("timeout", 4.0))
        except (TypeError, ValueError):
            self.timeout = 4.0
        self._request = request or self._http_request

    @property
    def enabled(self) -> bool:
        return self.config.enabled

    def summary(self, app_id: str) -> dict[str, object] | None:
        if not self.enabled or not app_id.isdecimal():
            return None
        try:
            status, payload = self._request(Request(f"{self.endpoint}/{app_id}.json", headers={"Accept": "application/json"}), self.timeout)
        except (OSError, TimeoutError) as error:
            raise ProtonDBError("unavailable") from error
        if status == 404:
            return {"tier": "unknown"}
        if status < 200 or status >= 300:
            raise ProtonDBError(f"http-{status}")
        try:
            value = json.loads(payload)
        except (TypeError, ValueError, json.JSONDecodeError) as error:
            raise ProtonDBError("malformed-response") from error
        if not isinstance(value, dict):
            raise ProtonDBError("malformed-response")
        result: dict[str, object] = {}
        for target, keys in (("tier", ("tier", "best_reported_tier")),
                             ("confidence", ("confidence",)), ("score", ("score",)),
                             ("trending_tier", ("trending_tier", "trending")),
                             ("best_tier", ("best_reported_tier",)),
                             ("report_count", ("report_count", "reports"))):
            for key in keys:
                if key in value:
                    result[target] = value[key]
                    break
        tier = str(result.get("tier", "unknown")).casefold()
        result["tier"] = tier if tier in TIERS else "unknown"
        return result

    @staticmethod
    def _http_request(request: Request, timeout: float) -> tuple[int, bytes]:
        try:
            with urlopen(request, timeout=timeout) as response:
                return int(response.status), response.read()
        except Exception as error:
            status = getattr(error, "code", None)
            if status is not None:
                return int(status), getattr(error, "read", lambda: b"")()
            raise
