import QtQuick

QtObject {
    // Base roles are the single source for both interface and backdrop colors.
    readonly property color background: "#060b16"
    readonly property color foreground: "#ffffff"
    readonly property color muted: "#9aa8c2"
    readonly property color selected: "#ffffff"
    readonly property color accent: "#e0c5ff"
    readonly property color glass: "#1d2a49"
    readonly property color error: "#f7788e"
    readonly property vector3d accentVector: Qt.vector3d(accent.r, accent.g, accent.b)
    readonly property vector3d headingAccentVector: Qt.vector3d(headingAccent.r, headingAccent.g, headingAccent.b)
    readonly property vector3d glassVector: Qt.vector3d(glass.r, glass.g, glass.b)
    readonly property vector3d errorVector: Qt.vector3d(error.r, error.g, error.b)

    readonly property color primaryText: foreground
    readonly property color secondaryText: "#c5cee2"
    readonly property color mutedText: muted
    readonly property color selectedText: selected
    readonly property color focusIndicator: accent
    readonly property color warning: accent
    readonly property color glassTint: glass
    readonly property color glassBorder: "#455274"
    readonly property color backdrop: background
    readonly property color navigationText: "#8492ad"
    readonly property color headingAccent: "#eadcff"
    readonly property color cardSurface: "#182540"
    readonly property color focusedCardSurface: "#283761"
    readonly property color actionSurface: "#394b78"
    readonly property color actionText: "#f1e7ff"
    readonly property color artworkSurface: "#10182b"
    readonly property color librarySurface: "#14213b"
    readonly property color libraryCardSurface: "#1b2a4a"
    readonly property color libraryBorder: "#6675ac"
    readonly property color libraryHighlight: "#7884c6"
    readonly property color transparent: "transparent"
    readonly property color scrollFadeStart: "#0014213b"
    readonly property color scrollFadeEnd: "#e614213b"
}
