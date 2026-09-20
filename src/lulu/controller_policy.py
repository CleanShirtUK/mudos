"""Mudos-owned controller policy shared by native emulator renderers."""

# SDL reports the InputPlumber virtual Xbox target with this stable GUID.
MUDOS_XBOX360_SDL_GUID = "030081b85e0400008e02000001000000"

# Eden 0.2.x applies its own face-button interpretation to these bindings.
# The inverse of the historical swap is required for the requested physical
# A/B and X/Y behaviour in the installed build.
NINTENDO_FACE_BUTTONS = {
    "a": 0,
    "b": 1,
    "x": 2,
    "y": 3,
}


def nintendo_face_binding(name: str) -> str:
    """Return Dolphin's SDL semantic binding for one Nintendo face button."""
    return {
        "a": "Button B",
        "b": "Button A",
        "x": "Button Y",
        "y": "Button X",
    }[name]
