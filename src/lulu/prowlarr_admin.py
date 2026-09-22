"""Controlled migration of a temporary Prowlarr handoff into Mudos config."""

from __future__ import annotations

from pathlib import Path
import re

from .provider_config import ProviderConfigurationService


def migrate_temporary_key(source: Path, service: ProviderConfigurationService) -> None:
    """Import the handoff key into SecretStore and persist only its reference."""
    text = source.read_text(errors="ignore")
    candidates = re.findall(r"[A-Za-z0-9_-]{32}", text)
    if len(candidates) != 1:
        raise ValueError("temporary Prowlarr handoff did not contain one API key")
    service.update_provider(
        "providers.prowlarr",
        {"enabled": True, "endpoint": "http://192.168.0.197:9696/",
         "secrets": {"api_key": "prowlarr/api-key"}},
        {"api_key": candidates[0]},
    )
