import QtQuick
import "."

Item {
    width: 1280
    height: 720

    Component.onCompleted: console.info("Desktop wallpaper theme:", mudosTheme.activeId,
                                        "shader:", mudosTheme.wallpaperShader)

    OrbitRenderSource {
        anchors.fill: parent
        continuousTime: true
        shaderOrigin: Qt.vector2d(0, 0)
        shaderCanvas: Qt.vector2d(width, height)
        // Desktop Mode has no shell presentation coordinator: keep the selected
        // theme continuously visible without replaying shell transitions.
    }
}
