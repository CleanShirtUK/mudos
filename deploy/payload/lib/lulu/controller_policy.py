"""Mudos-owned controller policy shared by native emulator renderers."""

# Nintendo-family logical face buttons on the standard Xbox-style target.
NINTENDO_FACE_BUTTONS = {
    "a": 1,
    "b": 0,
    "x": 3,
    "y": 2,
}


def nintendo_face_binding(name: str) -> str:
    """Return Dolphin's SDL semantic binding for one Nintendo face button."""
    return {
        "a": "Button B",
        "b": "Button A",
        "x": "Button Y",
        "y": "Button X",
    }[name]
