import QtQuick

Item {
    id: root
    anchors.fill: parent

    property real shaderTime: 0
    property vector2d shaderOrigin: Qt.vector2d(0, 0)
    property vector2d shaderCanvas: Qt.vector2d(width, height)
    property vector3d primaryColor: Qt.vector3d(0.478, 0.635, 0.969)
    property vector3d secondaryColor: Qt.vector3d(0.733, 0.604, 0.969)
    property vector3d surfaceColor: Qt.vector3d(0.141, 0.165, 0.231)
    property vector3d errorColor: Qt.vector3d(0.969, 0.463, 0.557)
    property bool shaderAvailable: orbitShader.status === ShaderEffect.Compiled

    Rectangle {
        anchors.fill: parent
        color: "#060b16"
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
