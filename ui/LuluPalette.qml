import QtQuick

QtObject {
    readonly property color primaryText: headingAccent
    readonly property color secondaryText: "#cec9d1"
    readonly property color mutedText: "#9b969f"
    readonly property color selectedText: headingAccent
    readonly property color accent: "#e0c5ff"
    readonly property color focusIndicator: "#e0c5ff"
    readonly property color warning: "#e0c5ff"
    // Structural glass transmits most of the animated backdrop; modal overlays
    // use separate, deliberately stronger dimming roles below.
    readonly property color glassTint: Qt.rgba(0.025, 0.027, 0.032, 0.42)
    readonly property color glassBorder: "#665f68"
    readonly property color backdrop: "#060607"
    readonly property color navigationText: "#aaa5ad"
    readonly property color headingAccent: "#eadcff"
    readonly property color cardSurface: Qt.rgba(0.055, 0.057, 0.064, 0.48)
    readonly property color focusedCardSurface: Qt.rgba(0.12, 0.105, 0.14, 0.62)
    readonly property color selectionSurface: Qt.rgba(0.13, 0.105, 0.16, 0.32)
    readonly property color actionSurface: Qt.rgba(0.16, 0.135, 0.18, 0.96)
    readonly property color actionText: "#f1e7ff"
    readonly property color artworkSurface: Qt.rgba(0.018, 0.019, 0.022, 0.80)
    readonly property color librarySurface: Qt.rgba(0.025, 0.027, 0.032, 0.46)
    readonly property color libraryCardSurface: Qt.rgba(0.055, 0.057, 0.064, 0.48)
    readonly property color libraryBorder: "#665f68"
    readonly property color libraryHighlight: focusIndicator
    readonly property color guideSurface: Qt.rgba(0.018, 0.019, 0.022, 0.84)
    readonly property color guideBorder: glassBorder
    readonly property color guideItemSurface: Qt.rgba(0.055, 0.057, 0.064, 0.94)
    readonly property color guideSelectedText: "#ff0b1018"
    readonly property color overlayBackdrop: Qt.rgba(0.005, 0.005, 0.007, 0.72)
    readonly property color overlaySurface: Qt.rgba(0.018, 0.019, 0.022, 0.97)
    readonly property color launchOverlaySurface: Qt.rgba(0.012, 0.013, 0.016, 0.96)
    readonly property color transparent: "transparent"
    readonly property color scrollFadeStart: "#0008090b"
    readonly property color scrollFadeEnd: "#e6090a0c"
}
