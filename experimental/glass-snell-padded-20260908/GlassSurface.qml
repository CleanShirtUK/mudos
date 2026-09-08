import QtQuick

Item {
    id: root

    property var sourceItem
    property real refractionStrength: 0.65
    property real chromaticSeparation: 1.0
    property real ior: 1.08
    property real snellMagnitudePixels: 6
    property real dispersionPixels: 1.25
    property real sourcePaddingPixels: 8
    property real diffusion: 0.0025
    property real focusAmount: 0
    property real cornerRadius: 0
    property real attenuation: 0.72
    property real edgeHighlight: 0.045
    property color tint: Qt.rgba(0.30, 0.39, 0.68, 0.30)
    property bool shaderAvailable: glassShader.status === ShaderEffect.Compiled

    readonly property point sourceOrigin: sourceItem ? mapToItem(sourceItem, 0, 0) : Qt.point(0, 0)
    readonly property vector2d sourceCanvas: sourceItem
        ? Qt.vector2d(sourceItem.width, sourceItem.height)
        : Qt.vector2d(width, height)
    readonly property point captureOrigin: Qt.point(
        sourceOrigin.x - sourcePaddingPixels, sourceOrigin.y - sourcePaddingPixels)
    readonly property size captureSize: Qt.size(
        Math.max(1, width + 2 * sourcePaddingPixels), Math.max(1, height + 2 * sourcePaddingPixels))

    Rectangle {
        anchors.fill: parent
        visible: !root.shaderAvailable
        radius: Math.min(width, height) * 0.06
        color: root.tint
        border.color: Qt.rgba(0.82, 0.86, 1.0, 0.30 + root.focusAmount * 0.18)
        border.width: 1
    }

    ShaderEffectSource {
        id: backdropTexture
        sourceItem: root.sourceItem ? root.sourceItem : null
        sourceRect: Qt.rect(root.captureOrigin.x, root.captureOrigin.y,
                            root.captureSize.width, root.captureSize.height)
        textureSize: root.captureSize
        live: true
        visible: false
    }

    ShaderEffect {
        id: glassShader
        anchors.fill: parent
        fragmentShader: "shaders/liquid-glass.frag.qsb"
        property var source: backdropTexture
        property point u_origin: root.sourceOrigin
        property vector2d u_captureSize: Qt.vector2d(root.captureSize.width, root.captureSize.height)
        property vector2d u_size: Qt.vector2d(root.width, root.height)
        property real u_padding: root.sourcePaddingPixels
        property real u_time: root.sourceItem && root.sourceItem.shaderTime !== undefined
            ? root.sourceItem.shaderTime : 0
        property real u_refraction: root.refractionStrength
        property real u_chromatic: root.chromaticSeparation
        property real u_ior: root.ior
        property real u_snellMagnitudePixels: root.snellMagnitudePixels
        property real u_dispersionPixels: root.dispersionPixels
        property real u_diffusion: root.diffusion
        property real u_focus: root.focusAmount
        property real u_cornerRadius: root.cornerRadius
        property real u_attenuation: root.attenuation
        property real u_edgeHighlight: root.edgeHighlight
        property color u_tint: root.tint
    }
}
