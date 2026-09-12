import QtQuick

Item {
    id: root
    property real cardHeight: 0
    property real cardWidth: 0
    property real uiScale: 1
    property var typography
    property var luluPalette
    property var canonicalTexture
    property var canonicalCoordinateRoot
    property size canonicalSize: Qt.size(1280, 720)
    signal steamStoreRequested()

    NavigationCard {
        width: root.cardWidth
        height: root.cardHeight
        displayTitle: "Store"
        symbolicArtwork: ""
        artworkRole: "raster"
        artworkSource: Qt.resolvedUrl("artwork/store.png")
        uiScale: root.uiScale
        typography: root.typography
        luluPalette: root.luluPalette
        canonicalTexture: root.canonicalTexture
        canonicalCoordinateRoot: root.canonicalCoordinateRoot
        canonicalSize: root.canonicalSize
        onActivated: root.steamStoreRequested()
    }
}
