import QtQuick
import Mudos.Poc 1.0

Rectangle {
    id: root

    property var canonicalTexture
    property var canonicalCoordinateRoot
    property size canonicalSize: Qt.size(1280, 720)
    property real uiScale: 1
    property real selectionProgress: 0
    property var luluPalette
    property var mappingItem: root

    readonly property rect mappedCanonicalRect: {
        var sourceItem = mappingItem || root
        var dependency = selectionProgress + uiScale
        var dependencyItem = sourceItem
        while (dependencyItem) {
            dependency += dependencyItem.x + dependencyItem.y
                + dependencyItem.width + dependencyItem.height
                + dependencyItem.scale
            dependencyItem = dependencyItem.parent
        }
        var topLeft = canonicalCoordinateRoot
            ? sourceItem.mapToItem(canonicalCoordinateRoot, 0, 0) : Qt.point(0, 0)
        var bottomRight = canonicalCoordinateRoot
            ? sourceItem.mapToItem(canonicalCoordinateRoot, sourceItem.width,
                                   sourceItem.height)
            : Qt.point(width, height)
        return Qt.rect(topLeft.x + dependency - dependency,
                       topLeft.y + dependency - dependency,
                       bottomRight.x - topLeft.x,
                       bottomRight.y - topLeft.y)
    }

    radius: 10 * root.uiScale
    color: Qt.rgba(
        luluPalette.cardSurface.r
            + (luluPalette.focusedCardSurface.r - luluPalette.cardSurface.r)
                * root.selectionProgress,
        luluPalette.cardSurface.g
            + (luluPalette.focusedCardSurface.g - luluPalette.cardSurface.g)
                * root.selectionProgress,
        luluPalette.cardSurface.b
            + (luluPalette.focusedCardSurface.b - luluPalette.cardSurface.b)
                * root.selectionProgress,
        luluPalette.cardSurface.a
            + (luluPalette.focusedCardSurface.a - luluPalette.cardSurface.a)
                * root.selectionProgress)
    border.color: Qt.rgba(
        luluPalette.glassBorder.r
            + (luluPalette.focusIndicator.r - luluPalette.glassBorder.r)
                * root.selectionProgress,
        luluPalette.glassBorder.g
            + (luluPalette.focusIndicator.g - luluPalette.glassBorder.g)
                * root.selectionProgress,
        luluPalette.glassBorder.b
            + (luluPalette.focusIndicator.b - luluPalette.glassBorder.b)
                * root.selectionProgress,
        luluPalette.glassBorder.a
            + (luluPalette.focusIndicator.a - luluPalette.glassBorder.a)
                * root.selectionProgress)
    border.width: (1 + 2 * root.selectionProgress) * root.uiScale
    clip: true

    MudosGlassItem {
        anchors.fill: parent
        backdrop: root.canonicalTexture
        canonicalSize: root.canonicalSize
        canonicalRect: root.mappedCanonicalRect
        cornerRadius: root.radius
        refractionPixels: 80 * root.uiScale
        dispersionIor: 0.0175
        diffusionPixels: 5 * root.uiScale
        transmission: 0.75
        bevelWidthPx: 3 * root.uiScale
        bulgeStrength: 100
        sceneLightStrength: 0
        sceneLightPixels: 24
        edgeLightStrength: 0.10
        edgeLightDirection: Qt.vector2d(1, -1)
        transparentOutsideMask: true
    }
}
