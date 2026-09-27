"""Mudos-owned controller policy shared by native emulator renderers."""

"""Canonical face-button policy for standard SDL gamepads.

Provider-specific config renderers translate these logical face names to
their own syntax; the swap itself lives here so providers cannot drift.
"""

from .paths import PATHS
from .settings import SettingsStore


def nintendo_layout_enabled() -> bool:
    """Read the persisted Mudos setting; new installs default to Nintendo layout."""
    store = SettingsStore(PATHS.config_root / "settings.sqlite3")
    try:
        return bool(store.get("controllers.nintendo_button_layout"))
    finally:
        store.connection.close()


def face_button_indices(nintendo_layout: bool = True) -> dict[str, int]:
    """Map Nintendo-style logical buttons to standard SDL face-button indices."""
    return {"a": 1, "b": 0, "x": 3, "y": 2} if nintendo_layout else {
        "a": 0, "b": 1, "x": 2, "y": 3,
    }


def face_button_swap(nintendo_layout: bool = True) -> dict[str, str]:
    """Map standard physical face positions to the projected logical positions."""
    if nintendo_layout:
        return {"south": "east", "east": "south", "west": "north", "north": "west"}
    return {position: position for position in ("south", "east", "west", "north")}


def nintendo_face_binding(name: str, enabled: bool = True) -> str:
    """Return Dolphin's SDL binding for one logical face button."""
    buttons = face_button_indices(enabled)
    return f"Button {('A', 'B', 'X', 'Y')[buttons[name]]}"
