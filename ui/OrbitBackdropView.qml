import QtQuick

ShaderEffect {
    id: root
    property var texture
    anchors.fill: parent
    fragmentShader: "shaders/orbit-texture-view.frag.qsb"
    property var source: root.texture
}
