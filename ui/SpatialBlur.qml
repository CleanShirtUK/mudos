import QtQuick

// Explicit source/effect pair. Unlike an Item layer effect, this makes the
// captured card texture and the effect output separate, inspectable surfaces.
Item {
    id: root
    property Item sourceItem
    property rect sourceRect: Qt.rect(0, 0, width, height)
    property real blurRadius: 0
    property real cornerRadius: 0
    property real outputScale: 1
    property bool active: true

    transform: Scale {
        origin.x: root.width * 0.5
        origin.y: root.height * 0.5
        xScale: root.outputScale
        yScale: root.outputScale
    }

    ShaderEffectSource {
        id: sourceTexture
        anchors.fill: parent
        sourceItem: root.sourceItem
        sourceRect: root.sourceRect
        textureSize: Qt.size(Math.max(1, Math.round(root.width)),
                             Math.max(1, Math.round(root.height)))
        live: root.active
        hideSource: root.active
    }

    ShaderEffect {
        anchors.fill: parent
        visible: root.active && root.blurRadius > 0
        property var source: sourceTexture
        property real blurRadius: root.blurRadius
        property real cornerRadius: root.cornerRadius
        property vector2d sourceTextureSize: Qt.vector2d(
            Math.max(1, root.width), Math.max(1, root.height))
        fragmentShader: "shaders/spatial-depth-blur.frag.qsb"
    }
}
