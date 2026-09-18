import QtQuick

Item {
    id: root

    property Item sourceItem
    property real blurRadius: 7
    property size sourceTextureSize: Qt.size(width, height)
    property int stage: 2 // 1 = horizontal, 2 = horizontal + vertical

    ShaderEffectSource {
        id: sourceTexture
        anchors.fill: parent
        sourceItem: root.sourceItem
        sourceRect: Qt.rect(0, 0, root.width, root.height)
        textureSize: root.sourceTextureSize
        live: true
        smooth: true
    }

    ShaderEffect {
        id: horizontalPass
        anchors.fill: parent
        property var source: sourceTexture
        property real blurRadius: root.blurRadius
        property vector2d sourceTextureSize: Qt.vector2d(
            Math.max(1, root.sourceTextureSize.width),
            Math.max(1, root.sourceTextureSize.height))
        fragmentShader: "shaders/mudos-blur-horizontal.frag.qsb"
        visible: root.stage >= 1
    }

    ShaderEffectSource {
        id: horizontalTexture
        anchors.fill: parent
        sourceItem: horizontalPass
        textureSize: root.sourceTextureSize
        live: true
        smooth: true
    }

    ShaderEffect {
        anchors.fill: parent
        property var source: horizontalTexture
        property real blurRadius: root.blurRadius
        property vector2d sourceTextureSize: Qt.vector2d(
            Math.max(1, root.sourceTextureSize.width),
            Math.max(1, root.sourceTextureSize.height))
        fragmentShader: "shaders/mudos-blur-vertical.frag.qsb"
        visible: root.stage >= 2
    }
}
