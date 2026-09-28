"""Canonical normalized Flatpak/AppStream classification policy."""

from __future__ import annotations

from collections.abc import Iterable

_GAME_CATEGORIES = frozenset({
    "game", "actiongame", "adventuregame", "arcadegame", "boardgame",
    "blocksgame", "cardgame", "kidsgame", "logicgame", "rolegame",
    "roleplaying", "shooter", "simulation", "sportsgame", "strategygame",
})


def classify_flatpak(component_type: str, categories: Iterable[str]) -> str:
    """Classify only metadata-asserted games and desktop applications."""
    normalized = {str(value).strip().casefold() for value in categories if str(value).strip()}
    if normalized & _GAME_CATEGORIES:
        return "game"
    if component_type.strip().casefold() in {"desktop-application", "desktopapplication"}:
        return "utility"
    return "unclassified"


def is_flatpak_game(component_type: str, categories: Iterable[str]) -> bool:
    return classify_flatpak(component_type, categories) == "game"
