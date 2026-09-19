"""Mudos-owned controller policy shared by native emulator renderers."""

# SDL reports the InputPlumber virtual Xbox target with this stable GUID.
MUDOS_XBOX360_SDL_GUID = "030081b85e0400008e02000001000000"

# Nintendo-family logical face buttons on the standard Xbox-style target.
# Eden and Dolphin consume the same policy through different native formats.
NINTENDO_FACE_BUTTONS = {
    "a": 1,  # physical Xbox B
    "b": 0,  # physical Xbox A
    "x": 3,  # physical Xbox Y
    "y": 2,  # physical Xbox X
}


def nintendo_face_binding(name: str) -> str:
    """Return Dolphin's SDL semantic binding for one Nintendo face button."""
    return {
        "a": "Button B",
        "b": "Button A",
        "x": "Button Y",
        "y": "Button X",
    }[name]
