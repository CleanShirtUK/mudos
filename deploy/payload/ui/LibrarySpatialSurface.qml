import QtQuick

Item {
    id: root

    property var canonicalTexture
    property var canonicalCoordinateRoot
    property size canonicalSize: Qt.size(1280, 720)
    property real progress: 0
    property real homeX: 0
    property real homeY: 0
    property real homeWidth: 0
    property real homeHeight: 0
    property real fullscreenX: 0
    property real fullscreenY: 0
    property real fullscreenWidth: 0
    property real fullscreenHeight: 0
    property real uiScale: 1
    property real verticalOffset: 0
    property bool surfaceVisible: false

    readonly property real surfaceX: homeX + (fullscreenX - homeX) * progress
    readonly property real surfaceY: homeY + (fullscreenY - homeY) * progress
    readonly property real surfaceWidth: homeWidth + (fullscreenWidth - homeWidth) * progress
    readonly property real surfaceHeight: homeHeight + (fullscreenHeight - homeHeight) * progress

    x: surfaceX
    y: surfaceY + verticalOffset
    width: surfaceWidth
    height: surfaceHeight
    visible: surfaceVisible

    NavigationCardSurface {
        anchors.fill: parent
        canonicalTexture: root.canonicalTexture
        canonicalSize: root.canonicalSize
        canonicalCoordinateRoot: root.canonicalCoordinateRoot
        cornerRadius: 16 * root.uiScale + 12 * root.uiScale * root.progress
        bevelWidthPx: 3 * root.uiScale + 3 * root.uiScale * root.progress
    }
}
