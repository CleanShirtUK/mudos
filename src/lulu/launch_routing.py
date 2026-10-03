"""Canonical interpretation of catalogue game launch identifiers.

This module resolves an identifier to its provider identity and the existing
launch API family. It does not start providers or own session lifecycle.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class LaunchDispatch(StrEnum):
    STEAM = "steam"
    AURELIA = "steam-aurelia"
    CONSOLED = "consoled"


@dataclass(frozen=True, slots=True)
class GameLaunchRoute:
    game_id: str
    provider_id: str
    provider_game_id: str
    dispatch: LaunchDispatch


def _positive_app_id(value: str, provider: str) -> str:
    if not value.isdecimal() or int(value) < 1:
        raise ValueError(f"{provider} AppID must be a positive integer")
    return value


def resolve_game_launch_route(
    game_id: str,
    *,
    steam_launch_provider: str | None = None,
    catalogue_provider: str | None = None,
    catalogue_provider_id: str | None = None,
) -> GameLaunchRoute:
    """Resolve a launch ID using the canonical provider-selection rules.

    Explicit ``steam-aurelia:<AppID>`` IDs always use Aurelia. A canonical
    ``steam:<AppID>`` ID uses Aurelia only when the existing override is set
    exactly to ``steam-aurelia``; otherwise it uses the supervised Steam path.
    Other providers remain Consoled/catalogue dispatched and are validated by
    that application boundary.

    Catalogue metadata, when supplied by Consoled, is authoritative for the
    provider identity. Parsing the ID remains necessary to preserve provider
    prefixes and reject malformed Steam identifiers consistently at either
    entry boundary.
    """
    if not isinstance(game_id, str) or not game_id:
        raise ValueError("game launch identifier is required")

    prefix, separator, suffix = game_id.partition(":")
    prefix = prefix if separator else ""
    is_steam_id = prefix in {"steam", "steam-aurelia"}

    if is_steam_id:
        app_id = _positive_app_id(suffix, "Steam")
        provider_id = catalogue_provider or prefix
        if catalogue_provider is not None and catalogue_provider != prefix:
            raise ValueError(f"launch identity/provider mismatch for {game_id}")
        provider_game_id = catalogue_provider_id or app_id
        provider_name = "Steam Aurelia" if provider_id == "steam-aurelia" else "Steam"
        provider_game_id = _positive_app_id(provider_game_id, provider_name)
        if provider_id == "steam-aurelia":
            dispatch = LaunchDispatch.AURELIA
        elif provider_id == "steam" and steam_launch_provider == "steam-aurelia":
            dispatch = LaunchDispatch.AURELIA
        elif provider_id == "steam":
            dispatch = LaunchDispatch.STEAM
        else:
            # Catalogue disagreement must not silently route a Steam-shaped ID
            # through an unrelated provider.
            raise ValueError(f"launch identity/provider mismatch for {game_id}")
        return GameLaunchRoute(game_id, provider_id, provider_game_id, dispatch)

    provider_id = catalogue_provider or prefix
    provider_game_id = catalogue_provider_id or (suffix if separator else game_id)
    return GameLaunchRoute(game_id, provider_id, provider_game_id, LaunchDispatch.CONSOLED)
