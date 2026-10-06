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
    property string themeShader: typeof mudosTheme !== "undefined" ? mudosTheme.wallpaperShader : ""
    readonly property var themeWallpaper: typeof mudosTheme !== "undefined" ? mudosTheme.wallpaper : ({})

    ShaderEffect {
        anchors.fill: parent
        fragmentShader: root.themeShader
        property vector2d u_resolution: Qt.vector2d(width, height)
        property vector2d u_origin: root.shaderOrigin
        property vector2d u_canvas: root.shaderCanvas
        property real u_time: root.shaderTime
        property real u_brightness: root.shaderBrightness
        property real u_visibility: root.shaderVisibility
        property vector3d u_primary: root.themeWallpaper.primary ? Qt.vector3d(Qt.color(root.themeWallpaper.primary).r, Qt.color(root.themeWallpaper.primary).g, Qt.color(root.themeWallpaper.primary).b) : root.primaryColor
        property vector3d u_secondary: root.themeWallpaper.secondary ? Qt.vector3d(Qt.color(root.themeWallpaper.secondary).r, Qt.color(root.themeWallpaper.secondary).g, Qt.color(root.themeWallpaper.secondary).b) : root.secondaryColor
        property vector3d u_surface: root.themeWallpaper.surface ? Qt.vector3d(Qt.color(root.themeWallpaper.surface).r, Qt.color(root.themeWallpaper.surface).g, Qt.color(root.themeWallpaper.surface).b) : root.surfaceColor
        property vector3d u_error: root.themeWallpaper.error ? Qt.vector3d(Qt.color(root.themeWallpaper.error).r, Qt.color(root.themeWallpaper.error).g, Qt.color(root.themeWallpaper.error).b) : root.errorColor
    }

}
