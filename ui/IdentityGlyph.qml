import QtQuick
import QtQuick.Effects
import "IdentityGlyphResolver.js" as IdentityGlyphResolver

Item {
    id: root

    property string namespace: ""
    property string identity: ""
    property real size: 20
    property color semanticColor: "white"
    readonly property var resolution: IdentityGlyphResolver.resolve(namespace, identity)
    readonly property bool resolved: image.status === Image.Ready

    width: resolved ? size : 0
    height: resolved ? size : 0
    visible: resolved

    Image {
        id: image
        anchors.fill: parent
        source: root.resolution.assetPath
        sourceSize: Qt.size(root.size, root.size)
        fillMode: Image.PreserveAspectFit
        asynchronous: true
        retainWhileLoading: false
        visible: false
    }

    MultiEffect {
        anchors.fill: image
        source: image
        colorization: 1.0
        colorizationColor: root.semanticColor
        visible: root.resolved
    }
}
