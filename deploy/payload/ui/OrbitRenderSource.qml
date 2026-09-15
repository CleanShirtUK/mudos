import QtQuick

Item {
    id: root
    anchors.fill: parent

    property var presentationCoordinator
    readonly property real shaderTime: presentationCoordinator
        ? presentationCoordinator.orbitShaderTime : 0
    readonly property real shaderBrightness: presentationCoordinator
        ? presentationCoordinator.orbitBrightness : 1
    readonly property real shaderVisibility: presentationCoordinator
        ? presentationCoordinator.orbitVisibility : 1
    property vector2d shaderOrigin: Qt.vector2d(0, 0)
    property vector2d shaderCanvas: Qt.vector2d(width, height)
    property vector3d primaryColor: Qt.vector3d(0.478, 0.635, 0.969)
    property vector3d secondaryColor: Qt.vector3d(0.733, 0.604, 0.969)
    property vector3d surfaceColor: Qt.vector3d(0.141, 0.165, 0.231)
    property vector3d errorColor: Qt.vector3d(0.969, 0.463, 0.557)

    ShaderEffect {
        anchors.fill: parent
        fragmentShader: "shaders/orbit-wave.frag.qsb"
        property vector2d u_resolution: Qt.vector2d(width, height)
        property vector2d u_origin: root.shaderOrigin
        property vector2d u_canvas: root.shaderCanvas
        property real u_time: root.shaderTime
        property real u_brightness: root.shaderBrightness
        property real u_visibility: root.shaderVisibility
        property vector3d u_primary: root.primaryColor
        property vector3d u_secondary: root.secondaryColor
        property vector3d u_surface: root.surfaceColor
        property vector3d u_error: root.errorColor
    }

}
