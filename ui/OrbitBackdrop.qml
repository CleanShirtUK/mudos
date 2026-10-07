import QtQuick

Item {
    id: root
    ThemeMotion { id: themeMotion }
    anchors.fill: parent

    property real shaderTime: 0
    property vector2d shaderOrigin: Qt.vector2d(0, 0)
    property vector2d shaderCanvas: Qt.vector2d(width, height)
    property vector3d primaryColor: Qt.vector3d(0.478, 0.635, 0.969)
    property vector3d secondaryColor: Qt.vector3d(0.733, 0.604, 0.969)
    property vector3d surfaceColor: Qt.vector3d(0.141, 0.165, 0.231)
    property vector3d errorColor: Qt.vector3d(0.969, 0.463, 0.557)
    property bool shaderAvailable: orbitShader.status === ShaderEffect.Compiled
    readonly property string themeShader: typeof mudosTheme !== "undefined" ? mudosTheme.wallpaperShader : ""
    readonly property var themeWallpaper: typeof mudosTheme !== "undefined" ? mudosTheme.wallpaper : ({})

    LuluPalette {
        id: luluPalette
    }

    Rectangle {
        anchors.fill: parent
        color: luluPalette.backdrop
        visible: !root.shaderAvailable
    }

    ShaderEffect {
        id: orbitShader
        anchors.fill: parent
        fragmentShader: root.themeShader
        property vector2d u_resolution: Qt.vector2d(width, height)
        property vector2d u_origin: root.shaderOrigin
        property vector2d u_canvas: root.shaderCanvas
        property real u_time: root.shaderTime
        property real u_brightness: 1.0
        property real u_visibility: 1.0
        property vector3d u_primary: root.themeWallpaper.primary ? Qt.vector3d(Qt.color(root.themeWallpaper.primary).r, Qt.color(root.themeWallpaper.primary).g, Qt.color(root.themeWallpaper.primary).b) : root.primaryColor
        property vector3d u_secondary: root.themeWallpaper.secondary ? Qt.vector3d(Qt.color(root.themeWallpaper.secondary).r, Qt.color(root.themeWallpaper.secondary).g, Qt.color(root.themeWallpaper.secondary).b) : root.secondaryColor
        property vector3d u_surface: root.themeWallpaper.surface ? Qt.vector3d(Qt.color(root.themeWallpaper.surface).r, Qt.color(root.themeWallpaper.surface).g, Qt.color(root.themeWallpaper.surface).b) : root.surfaceColor
        property vector3d u_error: root.themeWallpaper.error ? Qt.vector3d(Qt.color(root.themeWallpaper.error).r, Qt.color(root.themeWallpaper.error).g, Qt.color(root.themeWallpaper.error).b) : root.errorColor

    }

    NumberAnimation on shaderTime {
        to: 100000
        duration: themeMotion.speed("wallpaper", 1) > 0
            ? 100000000 / themeMotion.speed("wallpaper", 1) : 100000000
        loops: Animation.Infinite
        running: themeMotion.enabled("wallpaper")
            && themeMotion.speed("wallpaper", 1) > 0
    }
}
