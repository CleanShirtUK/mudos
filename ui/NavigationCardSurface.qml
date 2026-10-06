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
    readonly property var themeRadii: typeof mudosTheme !== "undefined" ? mudosTheme.radii : ({})
    property real cornerRadius: (themeRadii.card === 0 ? 0 : 16) * uiScale
    property real refractionPixels: 80 * uiScale
    property real dispersionIor: 0.0175
    property real diffusionPixels: 5 * uiScale
    property real transmission: 1
    property real bevelWidthPx: 3 * uiScale
    property real bulgeStrength: 100
    property real edgeLightStrength: 0.10
    property vector2d edgeLightDirection: Qt.vector2d(1, -1)
    property bool transparentOutsideMask: false
    readonly property var themeGlass: typeof mudosTheme !== "undefined" ? mudosTheme.glass : ({})
    readonly property var themeOptics: themeGlass.navigation || themeGlass.card || themeGlass
    readonly property var themeColors: typeof mudosTheme !== "undefined" ? mudosTheme.colors : ({})
    property var luluPalette

    Rectangle {
        anchors.fill: parent
        radius: root.cornerRadius
        color: root.themeColors.cardSurface || "#7a0e0e10"
        border.color: root.themeColors.border || "#665f68"
        visible: root.themeGlass.enabled === false
    }

    MudosGlassItem {
        id: nativeGlass
        anchors.fill: parent
        visible: root.themeGlass.enabled !== false && !!root.canonicalTexture
        backdrop: root.canonicalTexture
        canonicalSize: root.canonicalSize
        canonicalRect: root.canonicalRect
        cornerRadius: root.cornerRadius
        ior: root.themeOptics.ior || 1.08
        glassDepth: root.themeOptics.depth || 0.32
        refractionPixels: (root.themeOptics.refractionPixels || root.refractionPixels / root.uiScale) * root.uiScale
        dispersionIor: root.themeOptics.dispersionIor === undefined ? root.dispersionIor : root.themeOptics.dispersionIor
        diffusionPixels: (root.themeOptics.diffusionPixels || root.diffusionPixels / root.uiScale) * root.uiScale
        transmission: root.themeOptics.transmission === undefined ? root.transmission : root.themeOptics.transmission
        bevelWidthPx: (root.themeOptics.bevelWidth || root.bevelWidthPx / root.uiScale) * root.uiScale
        bulgeStrength: root.themeOptics.bulgeStrength === undefined ? root.bulgeStrength : root.themeOptics.bulgeStrength
        sceneLightStrength: root.themeOptics.sceneLightStrength || 0
        sceneLightPixels: root.themeOptics.sceneLightPixels || 24
        edgeLightStrength: root.themeOptics.edgeLightStrength === undefined ? root.edgeLightStrength : root.themeOptics.edgeLightStrength
        edgeLightDirection: root.themeOptics.edgeLightDirection ? Qt.vector2d(root.themeOptics.edgeLightDirection[0], root.themeOptics.edgeLightDirection[1]) : root.edgeLightDirection
        transparentOutsideMask: root.transparentOutsideMask
    }

    MudosChromeFrame {
        anchors.fill: parent
        luluPalette: root.luluPalette
        uiScale: root.uiScale
        cornerRadius: root.cornerRadius
        raised: true
    }

}
