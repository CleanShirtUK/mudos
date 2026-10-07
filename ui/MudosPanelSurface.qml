import QtQuick
import Mudos.Poc 1.0

// Structural glass substrate. Use once per visual elevation; descendants are
// flat controls and must not sample canonicalTexture again.
Rectangle {
    id: root

    property var canonicalTexture
    property var canonicalCoordinateRoot
    property size canonicalSize: Qt.size(1280, 720)
    property var mappingItem: root
    property var luluPalette
    property real uiScale: 1
    property real cornerRadius: luluPalette
        ? luluPalette.radius("panel", 18) * uiScale : 18 * uiScale
    property real tintOpacity: 0.12
    property string materialRole: "panel"
    property string decorationRole: "panel"
    readonly property var themeGlass: typeof mudosTheme !== "undefined" ? mudosTheme.glass : ({})
    readonly property var themeOptics: themeGlass.panel || themeGlass
    readonly property var materialProfile: luluPalette ? luluPalette.material(materialRole) : ({})
    readonly property bool materialEnabled: materialProfile.style === "linearGradient"
    property bool glassEnabled: themeGlass.enabled !== false

    readonly property rect mappedCanonicalRect: {
        var sourceItem = mappingItem || root
        var dependency = uiScale + x + y + width + height
        var item = sourceItem
        while (item) {
            dependency += item.x + item.y + item.width + item.height + item.scale
            item = item.parent
        }
        var topLeft = canonicalCoordinateRoot
            ? sourceItem.mapToItem(canonicalCoordinateRoot, 0, 0) : Qt.point(0, 0)
        var bottomRight = canonicalCoordinateRoot
            ? sourceItem.mapToItem(canonicalCoordinateRoot, sourceItem.width, sourceItem.height)
            : Qt.point(width, height)
        return Qt.rect(topLeft.x + dependency - dependency,
                       topLeft.y + dependency - dependency,
                       bottomRight.x - topLeft.x, bottomRight.y - topLeft.y)
    }

    radius: cornerRadius
    color: luluPalette && materialEnabled && glassEnabled && !!canonicalTexture
        ? "transparent" : luluPalette ? luluPalette.glassTint : Qt.rgba(0.025, 0.027, 0.032, 0.42)
    border.color: materialEnabled ? "transparent" : luluPalette ? luluPalette.glassBorder : "#665f68"
    border.width: Math.max(1, uiScale)
    clip: true

    MudosGlassItem {
        objectName: "mudosPanelGlassItem"
        anchors.fill: parent
        visible: root.glassEnabled && !!root.canonicalTexture
        backdrop: root.canonicalTexture
        canonicalSize: root.canonicalSize
        canonicalRect: root.mappedCanonicalRect
        cornerRadius: root.cornerRadius
        ior: root.themeOptics.ior || 1.08
        glassDepth: root.themeOptics.depth || 0.32
        refractionPixels: (root.themeOptics.refractionPixels || 80) * root.uiScale
        dispersionIor: root.themeOptics.dispersionIor || 0
        diffusionPixels: (root.themeOptics.diffusionPixels || 0) * root.uiScale
        transmission: root.themeOptics.transmission === undefined ? 0.94 : root.themeOptics.transmission
        bevelWidthPx: (root.themeOptics.bevelWidth || 3) * root.uiScale
        bulgeStrength: root.themeOptics.bulgeStrength || 0
        sceneLightStrength: root.themeOptics.sceneLightStrength || 0
        sceneLightPixels: root.themeOptics.sceneLightPixels || 24
        edgeLightStrength: root.themeOptics.edgeLightStrength || 0
        edgeLightDirection: root.themeOptics.edgeLightDirection ? Qt.vector2d(root.themeOptics.edgeLightDirection[0], root.themeOptics.edgeLightDirection[1]) : Qt.vector2d(1, -1)
        transparentOutsideMask: true
    }

    Rectangle {
        anchors.fill: parent
        radius: root.cornerRadius
        color: Qt.rgba(0.008, 0.009, 0.012, root.tintOpacity)
        border.width: 0
        visible: root.glassEnabled && !root.materialEnabled
    }

    MudosMaterialLayer {
        anchors.fill: parent
        luluPalette: root.luluPalette
        role: root.materialRole
        cornerRadius: root.cornerRadius
        uiScale: root.uiScale
    }

    MudosChromeFrame {
        anchors.fill: parent
        luluPalette: root.luluPalette
        uiScale: root.uiScale
        cornerRadius: root.cornerRadius
    }

    MudosDecorationLayer {
        anchors.fill: parent
        luluPalette: root.luluPalette
        role: root.decorationRole
        cornerRadius: root.cornerRadius
        uiScale: root.uiScale
    }
}
