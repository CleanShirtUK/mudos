import QtQuick

Item {
    id: root
    anchors.fill: parent

    property real shaderTime: 0
    property vector2d shaderOrigin: Qt.vector2d(0, 0)
    property vector2d shaderCanvas: Qt.vector2d(width, height)
    required property var palette
    readonly property vector3d primaryColor: palette.accentVector
    readonly property vector3d secondaryColor: palette.headingAccentVector
    readonly property vector3d surfaceColor: palette.glassVector
    readonly property vector3d errorColor: palette.errorVector
    property bool shaderAvailable: orbitShader.status === ShaderEffect.Compiled

    Rectangle {
        anchors.fill: parent
        color: root.palette.background
        visible: !root.shaderAvailable
    }

    ShaderEffect {
        id: orbitShader
        anchors.fill: parent
        fragmentShader: "shaders/orbit-wave.frag.qsb"
        property vector2d u_resolution: Qt.vector2d(width, height)
        property vector2d u_origin: root.shaderOrigin
        property vector2d u_canvas: root.shaderCanvas
        property real u_time: root.shaderTime
        property real u_brightness: 1.0
        property real u_visibility: 1.0
        property vector3d u_primary: root.primaryColor
        property vector3d u_secondary: root.secondaryColor
        property vector3d u_surface: root.surfaceColor
        property vector3d u_error: root.errorColor

    }

    NumberAnimation on shaderTime {
        from: 0
        to: 100000
        duration: 100000000
        loops: Animation.Infinite
        running: true
    }
}
