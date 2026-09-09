import QtQuick

Item {
    id: root
    property string displayTitle: ""
    property string symbolicArtwork: "[ ]"
    property bool focused: false
    property real selectionProgress: focused ? 1 : 0
    property real uiScale: 1
    property var typography
    property var luluPalette
    property var canonicalTexture
    property var canonicalCoordinateRoot
    property size canonicalSize: Qt.size(1280, 720)
    signal activated()

    NavigationCardSurface {
        anchors.fill: parent
        canonicalTexture: root.canonicalTexture
        canonicalSize: root.canonicalSize
        canonicalCoordinateRoot: root.canonicalCoordinateRoot
        uiScale: root.uiScale
    }

    GameCard {
        anchors.fill: parent
        compact: true
        homeCard: false
        glassVisible: false
        librarySurfaceMaterial: true
        focused: root.focused
        selectionProgress: root.selectionProgress
        focusBrightness: 0.68 + 0.32 * root.selectionProgress
        displayTitle: root.displayTitle
        symbolicArtwork: root.symbolicArtwork
        uiScale: root.uiScale
        typography: root.typography
        luluPalette: root.luluPalette
        MouseArea {
            anchors.fill: parent
            onClicked: root.activated()
        }
    }

}
