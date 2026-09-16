import QtQuick
import Mudos.Poc 1.0

Item {
    id: root

    property var canonicalTexture
    property size canonicalSize: Qt.size(1280, 720)
    property var canonicalCoordinateRoot
    property rect canonicalRect: Qt.rect(0, 0, width, height)
    property var canonicalMappingDependency
    property bool nativeGlassEnabled: false
    property bool glassDiscriminatorEnabled: false
    property bool selected: false
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

    GlassSurface {
        id: legacyGlass
        anchors.fill: parent
        visible: !root.nativeGlassEnabled
        debugCoordinateRoot: root.canonicalCoordinateRoot
        canonicalTexture: root.canonicalTexture
        canonicalSize: root.canonicalSize
        cornerRadius: root.cornerRadius
        useExplicitSceneGeometry: true
        sceneCoordinateRoot: root.canonicalCoordinateRoot
        useLiveSceneCoordinates: true
        sceneSizeOverride: Qt.size(root.width, root.height)
        refractionPixels: root.refractionPixels
        dispersionIor: root.dispersionIor
        diffusionPixels: root.diffusionPixels
        transmission: root.transmission
        bevelWidthPx: root.bevelWidthPx
        bulgeStrength: root.bulgeStrength
        edgeLightStrength: root.edgeLightStrength
        edgeLightDirection: root.edgeLightDirection
    }

    MudosGlassItem {
        id: nativeGlass
        anchors.fill: parent
        visible: root.nativeGlassEnabled
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

    function dumpNativeMapping(position) {
        if (!root.nativeGlassEnabled)
            return
        var r = root.canonicalRect
        console.log("MUDOS_NAVIGATION_GLASS_MAPPING",
                    "canonicalRect", r.x, r.y, r.width, r.height,
                    "canonicalSize", root.canonicalSize.width,
                        root.canonicalSize.height,
                    "sourceTextureSize", root.canonicalTexture
                        ? root.canonicalTexture.width + "x" + root.canonicalTexture.height
                        : "none",
                    "uvRect", r.x / root.canonicalSize.width,
                        r.y / root.canonicalSize.height,
                        r.width / root.canonicalSize.width,
                        r.height / root.canonicalSize.height,
                    "presentationPosition", position.x, position.y)
    }

    function dumpRuntimeState(position) {
        if (root.nativeGlassEnabled)
            nativeGlass.dumpRuntimeState(position)
        else
            legacyGlass.dumpRuntimeState(position)
    }

    function dumpRendererState(cardIdentity) {
        var legacyRenderable = root.visible && root.opacity > 0
                && legacyGlass.visible && legacyGlass.opacity > 0
                && legacyGlass.width > 0 && legacyGlass.height > 0
        var nativeRenderable = root.visible && root.opacity > 0
                && nativeGlass.visible && nativeGlass.opacity > 0
                && nativeGlass.width > 0 && nativeGlass.height > 0
        console.log("MUDOS_GLASS_RENDERER_RUNTIME",
                    "card", cardIdentity,
                    "selected", root.selected,
                    "requestedMode", root.nativeGlassEnabled ? "native" : "legacy",
                    "resolvedMode", nativeRenderable ? "native" : legacyRenderable ? "legacy" : "none",
                    "surfaceVisible", root.visible,
                    "surfaceOpacity", root.opacity,
                    "legacyVisible", legacyGlass.visible,
                    "legacyOpacity", legacyGlass.opacity,
                    "legacyRenderable", legacyRenderable,
                    "nativeVisible", nativeGlass.visible,
                    "nativeOpacity", nativeGlass.opacity,
                    "nativeRenderable", nativeRenderable,
                    "bothRenderable", legacyRenderable && nativeRenderable)
    }

    function dumpPresentationState(mark, identity) {
        console.log("MUDOS_NAVIGATION_SURFACE_PRESENTATION",
                    "mark", mark, "identity", identity,
                    "surfaceVisible", root.visible,
                    "surfaceOpacity", root.opacity,
                    "requestedNative", root.nativeGlassEnabled,
                    "legacyVisible", legacyGlass.visible,
                    "legacyOpacity", legacyGlass.opacity,
                    "legacyRenderable", root.visible && legacyGlass.visible
                        && legacyGlass.opacity > 0,
                    "nativeVisible", nativeGlass.visible,
                    "nativeOpacity", nativeGlass.opacity,
                    "nativeRenderable", root.visible && nativeGlass.visible
                        && nativeGlass.opacity > 0,
                    "canonicalRect", root.canonicalRect.x, root.canonicalRect.y,
                        root.canonicalRect.width, root.canonicalRect.height)
    }
}
