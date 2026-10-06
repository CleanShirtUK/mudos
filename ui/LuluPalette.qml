import QtQuick

QtObject {
    readonly property var themeColors: typeof mudosTheme !== "undefined" ? mudosTheme.colors : ({})
    function role(name, fallback) { return themeColors[name] || fallback }
    readonly property color primaryText: role("primaryText", headingAccent)
    readonly property color secondaryText: role("secondaryText", "#cec9d1")
    readonly property color mutedText: role("mutedText", "#9b969f")
    readonly property color selectedText: role("selectedText", headingAccent)
    readonly property color accent: role("accent", "#e0c5ff")
    readonly property color focusIndicator: role("focusIndicator", "#e0c5ff")
    readonly property color warning: role("warning", "#e0c5ff")
    // Structural glass transmits most of the animated backdrop; modal overlays
    // use separate, deliberately stronger dimming roles below.
    readonly property color glassTint: role("surface", "#6b070809")
    readonly property color glassBorder: role("border", "#665f68")
    readonly property color backdrop: role("backdrop", "#060607")
    readonly property color navigationText: role("navigationText", "#aaa5ad")
    readonly property color headingAccent: role("headingAccent", "#eadcff")
    readonly property color cardSurface: role("cardSurface", "#7a0e0e10")
    readonly property color focusedCardSurface: role("focusedCardSurface", "#9e1f1b24")
    readonly property color selectionSurface: role("selectionSurface", "#521f1a29")
    readonly property color actionSurface: role("actionSurface", "#f529222e")
    readonly property color actionText: role("actionText", "#f1e7ff")
    readonly property color artworkSurface: role("artworkSurface", "#cc050507")
    readonly property color librarySurface: role("librarySurface", "#75070809")
    readonly property color libraryCardSurface: role("libraryCardSurface", cardSurface)
    readonly property color libraryBorder: role("libraryBorder", glassBorder)
    readonly property color libraryHighlight: focusIndicator
    readonly property color guideSurface: role("guideSurface", "#d6050506")
    readonly property color guideBorder: glassBorder
    readonly property color guideItemSurface: role("guideItemSurface", "#f0050506")
    readonly property color guideSelectedText: role("guideSelectedText", "#ff0b1018")
    readonly property color overlayBackdrop: role("overlayBackdrop", "#b8000002")
    readonly property color overlaySurface: role("overlaySurface", "#f7050506")
    readonly property color launchOverlaySurface: role("launchOverlaySurface", "#f5050506")
    readonly property color transparent: "transparent"
    readonly property color scrollFadeStart: role("scrollFadeStart", "#0008090b")
    readonly property color scrollFadeEnd: role("scrollFadeEnd", "#e6090a0c")
}
