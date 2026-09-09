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
    property point liveSceneOrigin: Qt.point(0, 0)

    readonly property real surfaceX: homeX + (fullscreenX - homeX) * progress
    readonly property real surfaceY: homeY + (fullscreenY - homeY) * progress
    readonly property real surfaceWidth: homeWidth + (fullscreenWidth - homeWidth) * progress
    readonly property real surfaceHeight: homeHeight + (fullscreenHeight - homeHeight) * progress

    x: surfaceX
    y: surfaceY + verticalOffset
    width: surfaceWidth
    height: surfaceHeight
    visible: surfaceVisible

    GlassSurface {
        anchors.fill: parent
        canonicalTexture: root.canonicalTexture
        canonicalSize: root.canonicalSize
        cornerRadius: 16 * root.uiScale + 12 * root.uiScale * root.progress
        useExplicitSceneGeometry: true
        sceneOriginOverride: root.liveSceneOrigin
        sceneSizeOverride: Qt.size(root.width, root.height)
        refractionPixels: 80 * root.uiScale
        dispersionIor: 0.0175
        diffusionPixels: 5 * root.uiScale
        transmission: 1
        bevelWidthPx: 3 * root.uiScale + 3 * root.uiScale * root.progress
        bulgeStrength: 100
        edgeLightStrength: 0.10
        edgeLightDirection: Qt.vector2d(1, -1)
    }

    Timer {
        interval: 16
        running: root.canonicalCoordinateRoot !== null
            && root.canonicalCoordinateRoot !== undefined
        repeat: true
        onTriggered: root.liveSceneOrigin = root.mapToItem(
            root.canonicalCoordinateRoot, 0, 0)
    }
}
