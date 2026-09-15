import QtQuick

Item {
    id: root

    property var canonicalTexture
    property size canonicalSize: Qt.size(1280, 720)
    property real ior: 1.08
    property real glassDepth: 0.32
    property real refractionPixels: 12
    property real dispersionIor: 0
    property real diffusionPixels: 0
    property real transmission: 1
    property real bevelWidthPx: 6
    property real bulgeStrength: 0
    property real sceneLightStrength: 0
    property real sceneLightPixels: 24
    property real edgeLightStrength: 0
    property vector2d edgeLightDirection: Qt.vector2d(1, -1)
    property real focusAmount: 0
    property real cornerRadius: 0
    property bool useExplicitSceneGeometry: false
    property bool identitySampling: false
    property bool transparentOutsideMask: false
    property var sceneCoordinateRoot
    property bool useLiveSceneCoordinates: false
    property point liveSceneOrigin: Qt.point(0, 0)
    property bool liveSceneOriginInitialized: false
    property point sceneOriginOverride: Qt.point(0, 0)
    property size sceneSizeOverride: Qt.size(0, 0)
    // Developer-only diagnostics; production rendering uses mode 0.
    property int diagnosticMode: 0
    property string debugLabel: ""
    property var debugCoordinateRoot
    readonly property point mappedSceneOrigin: sceneCoordinateRoot
        ? mapToItem(sceneCoordinateRoot, 0, 0) : sceneOriginOverride
    readonly property point sceneOrigin: useExplicitSceneGeometry
        ? (useLiveSceneCoordinates && sceneCoordinateRoot
            ? (liveSceneOriginInitialized ? liveSceneOrigin : mappedSceneOrigin)
            : sceneOriginOverride)
        : (canonicalTexture ? mapToItem(canonicalTexture, 0, 0) : Qt.point(0, 0))
    readonly property vector2d sceneSize: useExplicitSceneGeometry
        ? Qt.vector2d(sceneSizeOverride.width, sceneSizeOverride.height)
        : Qt.vector2d(width, height)

    function invalidateLiveSceneOrigin() {
        liveSceneOriginInitialized = false
    }

    onSceneCoordinateRootChanged: invalidateLiveSceneOrigin()
    onParentChanged: invalidateLiveSceneOrigin()
    onXChanged: invalidateLiveSceneOrigin()
    onYChanged: invalidateLiveSceneOrigin()
    onWidthChanged: invalidateLiveSceneOrigin()
    onHeightChanged: invalidateLiveSceneOrigin()

    ShaderEffect {
        anchors.fill: parent
        fragmentShader: root.identitySampling
            ? "shaders/canonical-identity.frag.qsb"
            : "shaders/canonical-snell-refraction.frag.qsb"
        property var source: root.canonicalTexture
        property vector2d u_sceneOrigin: Qt.vector2d(root.sceneOrigin.x, root.sceneOrigin.y)
        property vector2d u_sceneSize: root.sceneSize
        property vector2d u_canonicalSize: Qt.vector2d(root.canonicalSize.width, root.canonicalSize.height)
        property real u_ior: root.ior
        property real u_depth: root.glassDepth
        property real u_refractionPixels: root.refractionPixels
        property real u_dispersionIor: root.dispersionIor
        property real u_diffusionPixels: root.diffusionPixels
        property real u_transmission: root.transmission
        property real u_bevelWidthPx: root.bevelWidthPx
        property real u_bulgeStrength: root.bulgeStrength
        property real u_sceneLightStrength: root.sceneLightStrength
        property real u_sceneLightPixels: root.sceneLightPixels
        property real u_edgeLightStrength: root.edgeLightStrength
        property vector2d u_edgeLightDirection: root.edgeLightDirection
        property real u_cornerRadius: root.cornerRadius
        property real u_transparentOutsideMask: root.transparentOutsideMask ? 1.0 : 0.0
        property int u_diagnostic: root.diagnosticMode
    }

    Timer {
        interval: 16
        running: root.useLiveSceneCoordinates && root.visible
            && root.sceneCoordinateRoot !== null
            && root.sceneCoordinateRoot !== undefined
        repeat: true
        onTriggered: {
            root.liveSceneOrigin = root.mapToItem(root.sceneCoordinateRoot, 0, 0)
            root.liveSceneOriginInitialized = true
        }
    }

    Timer {
        interval: 1500
        running: root.debugLabel !== ""
        repeat: false
        onTriggered: {
            var mapped = root.mapToItem(root.debugCoordinateRoot, 0, 0)
            console.log("FOCAL_PRODUCTION_PROBE", root.debugLabel,
                        "mapped", mapped.x, mapped.y,
                        "sceneOrigin", root.sceneOrigin.x, root.sceneOrigin.y,
                        "sceneSize", root.sceneSize.x, root.sceneSize.y,
                        "canonicalSize", root.canonicalSize.width, root.canonicalSize.height,
                        "textureSize", root.canonicalTexture.width, root.canonicalTexture.height)
        }
    }
}
