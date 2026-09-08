import QtQuick

Item {
    id: libraryHome
    property real cardHeight: 0
    property var typography
    property var luluPalette
    property var canonicalTexture
    property var canonicalCoordinateRoot
    property size canonicalSize: Qt.size(1280, 720)
    property real compactCardWidth: 160 * uiScale
    property point allGamesSceneOrigin: Qt.point(0, 0)
    property string transitionState: "RESTING"
    property real uiScale: 1
    readonly property string navigationObject: "library"
    signal openRequested()

    GameCard {
        id: libraryHomeCard
        x: 0
        y: 0
        width: compactCardWidth
        height: cardHeight
        compact: true
        homeCard: true
        presentationState: "COMPACT"
        displayTitle: "All Games"
        presentationId: "library:all"
        symbolicArtwork: "[ ]"
        identitySampling: false
        typography: libraryHome.typography
        luluPalette: libraryHome.luluPalette
        canonicalTexture: libraryHome.canonicalTexture
        canonicalCoordinateRoot: libraryHome.canonicalCoordinateRoot
        canonicalSize: libraryHome.canonicalSize
        sceneOriginOverride: libraryHome.allGamesSceneOrigin
        sceneSizeOverride: Qt.size(libraryHomeCard.actualGlassSurface.width,
                                   libraryHomeCard.actualGlassSurface.height)

        MouseArea {
            anchors.fill: parent
            onClicked: openRequested()
        }
    }

    Timer {
        interval: 16
        running: libraryHome.visible
        repeat: true
        onTriggered: libraryHome.allGamesSceneOrigin =
            libraryHomeCard.actualGlassSurface.mapToItem(
                libraryHome.canonicalCoordinateRoot, 0, 0)
    }
}
