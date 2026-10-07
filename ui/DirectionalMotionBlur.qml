import QtQuick

// Captures one already-composed presentation surface and applies a bounded
// directional blur. The source item is hidden by ShaderEffectSource, so the
// effect is the only visible copy and cannot capture itself.
Item {
    id: root
    ThemeMotion { id: themeMotion }

    property Item sourceItem
    // Coordinates are local to sourceItem. Padding belongs here rather than
    // in sourceItem's hierarchy, so the observed scene geometry is unchanged.
    property rect sourceRect: Qt.rect(0, 0, width, height)
    property real blurPixels: 0
    property vector2d blurVector: Qt.vector2d(blurPixels, 0)
    property bool active: true
    readonly property bool motionEnabled: themeMotion.enabled("motionBlur")

    ShaderEffectSource {
        id: sourceTexture
        objectName: "motionBlurSourceTexture"
        anchors.fill: parent
        sourceItem: root.active && root.motionEnabled ? root.sourceItem : null
        sourceRect: root.sourceRect
        textureSize: Qt.size(Math.max(1, Math.round(root.width)),
                             Math.max(1, Math.round(root.height)))
        live: root.active && root.motionEnabled
        hideSource: root.active && root.motionEnabled
        visible: false
    }

        ShaderEffect {
        anchors.fill: parent
        visible: root.active && root.motionEnabled
        property var source: sourceTexture
        property vector2d blurVector: root.blurVector
        property vector2d sourceTextureSize: Qt.vector2d(
            Math.max(1, root.width), Math.max(1, root.height))
        fragmentShader: "shaders/presentation-motion-blur.frag.qsb"
    }
}
