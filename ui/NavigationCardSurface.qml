import QtQuick

GlassSurface {
    id: root

    property var canonicalCoordinateRoot
    property real uiScale: 1
    cornerRadius: 16 * uiScale
    useExplicitSceneGeometry: true
    sceneCoordinateRoot: root.canonicalCoordinateRoot
    useLiveSceneCoordinates: true
    sceneSizeOverride: Qt.size(root.width, root.height)
    refractionPixels: 80 * uiScale
    dispersionIor: 0.0175
    diffusionPixels: 5 * uiScale
    transmission: 1
    bevelWidthPx: 3 * uiScale
    bulgeStrength: 100
    edgeLightStrength: 0.10
    edgeLightDirection: Qt.vector2d(1, -1)
}
