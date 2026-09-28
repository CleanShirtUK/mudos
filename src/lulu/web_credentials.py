"""Mudos-owned credentials for explicitly trusted built-in web apps."""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlsplit

from .credential import SecretStore


@dataclass(frozen=True, slots=True)
class WebCredentialProfile:
    profile_id: str
    origin: str

    @property
    def username_ref(self) -> tuple[str, str]:
        return (f"web/{self.profile_id}", "username")

    @property
    def password_ref(self) -> tuple[str, str]:
        return (f"web/{self.profile_id}", "password")


TRUSTED_WEB_PROFILES: dict[str, WebCredentialProfile] = {}


def exact_origin(url: str) -> str:
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return ""
    try:
        port = parsed.port
    except ValueError:
        return ""
    host = parsed.hostname.lower()
    default = (parsed.scheme == "http" and port in (None, 80)) or (
        parsed.scheme == "https" and port in (None, 443))
    return f"{parsed.scheme.lower()}://{host}" + (f":{port}" if port and not default else "")


class WebCredentialStore:
    """SecretStore-backed credentials gated by profile identity and origin."""

    def __init__(self, secrets: SecretStore | None = None) -> None:
        self.secrets = secrets or SecretStore()

    def profile(self, profile_id: str, origin: str) -> WebCredentialProfile:
        profile = TRUSTED_WEB_PROFILES.get(profile_id)
        if profile is None or exact_origin(origin) != profile.origin:
            raise ValueError("web credential profile is not authorised for this origin")
        return profile

    def get(self, profile_id: str, origin: str) -> dict[str, object]:
        profile = self.profile(profile_id, origin)
        namespace, username_name = profile.username_ref
        password_namespace, password_name = profile.password_ref
        configured = self.secrets.configured(namespace, username_name) and self.secrets.configured(
            password_namespace, password_name)
        if not configured:
            return {"configured": False, "profile": profile_id, "origin": profile.origin}
        return {
            "configured": True,
            "profile": profile_id,
            "origin": profile.origin,
            "username": self.secrets.get(namespace, username_name) or "",
            "password": self.secrets.get(password_namespace, password_name) or "",
        }

    def save(self, profile_id: str, origin: str, username: str, password: str) -> dict[str, object]:
        profile = self.profile(profile_id, origin)
        if not username or not password:
            raise ValueError("web credential values must be non-empty")
        namespace, username_name = profile.username_ref
        password_namespace, password_name = profile.password_ref
        self.secrets.put(namespace, username_name, username)
        self.secrets.put(password_namespace, password_name, password)
        return {"configured": True, "profile": profile_id, "origin": profile.origin}

    def clear(self, profile_id: str, origin: str) -> dict[str, object]:
        profile = self.profile(profile_id, origin)
        namespace, username_name = profile.username_ref
        password_namespace, password_name = profile.password_ref
        self.secrets.clear(namespace, username_name)
        self.secrets.clear(password_namespace, password_name)
        return {"configured": False, "profile": profile_id, "origin": profile.origin}
