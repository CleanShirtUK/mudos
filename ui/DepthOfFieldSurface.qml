import QtQuick

// Non-focal cards use a live padded RGBA surface. The focal card never
// instantiates this item, so native glass remains the authoritative depth-0
// representation.
Item {
    id: root
    property Item sourceItem
    property real blurRadius: 0
    property real padding: 28
    property real outputScale: 1
    property bool active: false

    // Three modest iterations avoid stretching one kernel into visible lobes.
    // blurRadius remains continuous while the pass footprint changes smoothly.
    readonly property real passRadius: Math.max(0.01,
        root.blurRadius / Math.sqrt(3))
    readonly property real blurProgress: Math.max(0, Math.min(1,
        (root.blurRadius - 0.5) / 7.5))

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

    // This texture includes transparent padding on every side. It is also
    // the sharp branch of the composite, ensuring that blur never replaces
    // the live source with an opaque rectangular backing.
    ShaderEffectSource {
        id: sourceTexture
        anchors.fill: parent
        sourceItem: paddedInput
        textureSize: Qt.size(Math.max(1, Math.round(root.width)),
                             Math.max(1, Math.round(root.height)))
        live: root.active
        opacity: 1 - root.blurProgress
        z: 1
    }

    ShaderEffect {
        id: horizontalOne
        anchors.fill: parent
        property var source: sourceTexture
        property real blurRadius: root.passRadius
        property vector2d direction: Qt.vector2d(1, 0)
        property vector2d sourceTextureSize: Qt.vector2d(
            Math.max(1, root.width), Math.max(1, root.height))
        fragmentShader: "shaders/depth-gaussian-blur.frag.qsb"
        z: -6
    }
    ShaderEffectSource {
        id: horizontalOneTexture
        anchors.fill: parent
        sourceItem: horizontalOne
        live: root.active
        z: -6
    }
    ShaderEffect {
        id: verticalOne
        anchors.fill: parent
        property var source: horizontalOneTexture
        property real blurRadius: root.passRadius
        property vector2d direction: Qt.vector2d(0, 1)
        property vector2d sourceTextureSize: Qt.vector2d(
            Math.max(1, root.width), Math.max(1, root.height))
        fragmentShader: "shaders/depth-gaussian-blur.frag.qsb"
        z: -6
    }
    ShaderEffectSource {
        id: verticalOneTexture
        anchors.fill: parent
        sourceItem: verticalOne
        live: root.active
        z: -6
    }

    ShaderEffect {
        id: horizontalTwo
        anchors.fill: parent
        property var source: verticalOneTexture
        property real blurRadius: root.passRadius
        property vector2d direction: Qt.vector2d(1, 0)
        property vector2d sourceTextureSize: Qt.vector2d(
            Math.max(1, root.width), Math.max(1, root.height))
        fragmentShader: "shaders/depth-gaussian-blur.frag.qsb"
        z: -5
    }
    ShaderEffectSource {
        id: horizontalTwoTexture
        anchors.fill: parent
        sourceItem: horizontalTwo
        live: root.active
        z: -5
    }
    ShaderEffect {
        id: verticalTwo
        anchors.fill: parent
        property var source: horizontalTwoTexture
        property real blurRadius: root.passRadius
        property vector2d direction: Qt.vector2d(0, 1)
        property vector2d sourceTextureSize: Qt.vector2d(
            Math.max(1, root.width), Math.max(1, root.height))
        fragmentShader: "shaders/depth-gaussian-blur.frag.qsb"
        z: -5
    }
    ShaderEffectSource {
        id: verticalTwoTexture
        anchors.fill: parent
        sourceItem: verticalTwo
        live: root.active
        z: -5
    }

    ShaderEffect {
        id: horizontalThree
        anchors.fill: parent
        property var source: verticalTwoTexture
        property real blurRadius: root.passRadius
        property vector2d direction: Qt.vector2d(1, 0)
        property vector2d sourceTextureSize: Qt.vector2d(
            Math.max(1, root.width), Math.max(1, root.height))
        fragmentShader: "shaders/depth-gaussian-blur.frag.qsb"
        z: -4
    }
    ShaderEffectSource {
        id: horizontalThreeTexture
        anchors.fill: parent
        sourceItem: horizontalThree
        live: root.active
        z: -4
    }
    ShaderEffect {
        id: verticalThree
        anchors.fill: parent
        property var source: horizontalThreeTexture
        property real blurRadius: root.passRadius
        property vector2d direction: Qt.vector2d(0, 1)
        property vector2d sourceTextureSize: Qt.vector2d(
            Math.max(1, root.width), Math.max(1, root.height))
        fragmentShader: "shaders/depth-gaussian-blur.frag.qsb"
        opacity: root.blurProgress
        z: 2
    }
}
