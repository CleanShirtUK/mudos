import QtQuick

// Non-focal cards are captured live and blurred as a single visual surface.
// The focal card never instantiates this surface.
Item {
    id: root
    property Item sourceItem
    property real blurRadius: 0
    property real padding: 28
    property real outputScale: 1
    property bool active: false

    visible: root.active
    anchors.margins: -root.padding
    transform: Scale {
        origin.x: root.width * 0.5
        origin.y: root.height * 0.5
        xScale: root.outputScale
        yScale: root.outputScale
    }

    Item {
        id: paddedInput
        anchors.fill: parent

        ShaderEffectSource {
            id: cardTexture
            x: root.padding
            y: root.padding
            width: root.sourceItem ? root.sourceItem.width : 1
            height: root.sourceItem ? root.sourceItem.height : 1
            sourceItem: root.sourceItem
            sourceRect: Qt.rect(0, 0, width, height)
            textureSize: Qt.size(Math.max(1, Math.round(width)),
                                 Math.max(1, Math.round(height)))
            live: root.active
            hideSource: root.active
        }
    }

    ShaderEffectSource {
        id: sourceTexture
        anchors.fill: parent
        sourceItem: paddedInput
        textureSize: Qt.size(Math.max(1, Math.round(root.width)),
                             Math.max(1, Math.round(root.height)))
        live: root.active
    }

    ShaderEffect {
        anchors.fill: parent
        property var source: sourceTexture
        property real blurRadius: root.blurRadius
        property vector2d sourceTextureSize: Qt.vector2d(
            Math.max(1, root.width), Math.max(1, root.height))
        fragmentShader: "shaders/depth-gaussian-blur.frag.qsb"
    }
}
