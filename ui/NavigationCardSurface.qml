import QtQuick
import Mudos.Poc 1.0

Item {
    id: root

    property var canonicalTexture
    property size canonicalSize: Qt.size(1280, 720)
    property var canonicalCoordinateRoot
    property rect canonicalRect: Qt.rect(0, 0, width, height)
    property var canonicalMappingDependency
    property real uiScale: 1
    property real cornerRadius: 16 * uiScale
    property real refractionPixels: 80 * uiScale
    property real dispersionIor: 0.0175
    property real diffusionPixels: 5 * uiScale
    property real transmission: 1
    property real bevelWidthPx: 3 * uiScale
    property real bulgeStrength: 100
    property real edgeLightStrength: 0.10
    property vector2d edgeLightDirection: Qt.vector2d(1, -1)
    property bool transparentOutsideMask: false

    MudosGlassItem {
        id: nativeGlass
        anchors.fill: parent
        backdrop: root.canonicalTexture
        canonicalSize: root.canonicalSize
        canonicalRect: root.canonicalRect
        cornerRadius: root.cornerRadius
        refractionPixels: root.refractionPixels
        dispersionIor: root.dispersionIor
        diffusionPixels: root.diffusionPixels
        transmission: root.transmission
        bevelWidthPx: root.bevelWidthPx
        bulgeStrength: root.bulgeStrength
        edgeLightStrength: root.edgeLightStrength
        edgeLightDirection: root.edgeLightDirection
        transparentOutsideMask: root.transparentOutsideMask
    }

}
