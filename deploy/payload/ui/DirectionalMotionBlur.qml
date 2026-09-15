import QtQuick

// Captures one already-composed presentation surface and applies a bounded
// directional blur. The source item is hidden by ShaderEffectSource, so the
// effect is the only visible copy and cannot capture itself.
Item {
    id: root

    property Item sourceItem
    // Coordinates are local to sourceItem. Padding belongs here rather than
    // in sourceItem's hierarchy, so the observed scene geometry is unchanged.
    property rect sourceRect: Qt.rect(0, 0, width, height)
    property real blurPixels: 0

    ShaderEffectSource {
        id: sourceTexture
        anchors.fill: parent
        sourceItem: root.sourceItem
        sourceRect: root.sourceRect
        textureSize: Qt.size(Math.max(1, Math.round(root.width)),
                             Math.max(1, Math.round(root.height)))
        live: true
        hideSource: true
        visible: false
    }

    ShaderEffect {
        anchors.fill: parent
        property var source: sourceTexture
        property real blurPixels: root.blurPixels
        property vector2d sourceTextureSize: Qt.vector2d(
            Math.max(1, root.width), Math.max(1, root.height))
        fragmentShader: "shaders/presentation-motion-blur.frag.qsb"
    }
}
