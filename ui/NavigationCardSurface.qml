import QtQuick

GlassSurface {
    id: root

    property var canonicalCoordinateRoot
    property point liveSceneOrigin: Qt.point(0, 0)
    property real uiScale: 1

    cornerRadius: 16 * uiScale
    useExplicitSceneGeometry: true
    sceneOriginOverride: root.liveSceneOrigin
    sceneSizeOverride: Qt.size(root.width, root.height)
    refractionPixels: 80 * uiScale
    dispersionIor: 0.0175
    diffusionPixels: 5 * uiScale
    transmission: 1
    bevelWidthPx: 3 * uiScale
    bulgeStrength: 100
    edgeLightStrength: 0.10
    edgeLightDirection: Qt.vector2d(1, -1)

    Timer {
        interval: 16
        running: root.visible && root.canonicalCoordinateRoot !== null
            && root.canonicalCoordinateRoot !== undefined
        repeat: true
        onTriggered: root.liveSceneOrigin = root.mapToItem(
            root.canonicalCoordinateRoot, 0, 0)
    }
}
