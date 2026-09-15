import QtQuick

Item {
    id: root
    property string displayTitle: ""
    property string symbolicArtwork: ""
    property url artworkSource: ""
    property string artworkRole: "icon"
    property bool focused: false
    property bool selectedOpacityOwner: focused
    property real selectionProgress: focused ? 1 : 0
    property real uiScale: 1
    property var typography
    property var luluPalette
    property var canonicalTexture
    property var canonicalCoordinateRoot
    property size canonicalSize: Qt.size(1280, 720)
    property bool motionBlurActive: false
    property real motionStartX: 0
    property real motionTargetX: 0
    property real motionProgress: 1
    property real motionDuration: 500
    property real motionBlurPixels: 0
    property real motionBlurPadding: 64
    readonly property real motionVelocity: motionBlurActive
        ? (motionTargetX - motionStartX) * 5
            * Math.pow(1 - Math.max(0, Math.min(1, motionProgress)), 4)
            / motionDuration : 0
    signal activated()

    Item {
        id: logicalCard
        anchors.fill: parent

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
        // Selection ownership changes with the logical focus immediately;
        // selectionProgress remains presentation-only for the existing 180 ms
        // focus choreography.
        focusBrightness: root.selectedOpacityOwner ? 1 : 0.68
            displayTitle: root.displayTitle
            symbolicArtwork: root.symbolicArtwork
            artworkRole: root.artworkRole
            artworkSource: root.artworkSource
            uiScale: root.uiScale
            typography: root.typography
            luluPalette: root.luluPalette
            MouseArea {
                anchors.fill: parent
                onClicked: root.activated()
            }
        }
    }

    DirectionalMotionBlur {
        id: motionBlur
        x: -root.motionBlurPadding
        y: -root.motionBlurPadding
        width: root.width + 2 * root.motionBlurPadding
        height: root.height + 2 * root.motionBlurPadding
        active: root.motionBlurActive && root.visible
        sourceItem: logicalCard
        sourceRect: Qt.rect(-root.motionBlurPadding, -root.motionBlurPadding,
                            width, height)
        blurPixels: root.motionBlurPixels
    }
}
