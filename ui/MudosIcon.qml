import QtQuick
import "MudosAssetCatalog.js" as MudosAssetCatalog

Text {
    id: root

    property string name: "info"
    property string glyph: ""
    property var typography
    property color semanticColor: "white"
    property real iconSize: 20

    text: root.glyph || MudosAssetCatalog.icon(root.name)
    color: root.semanticColor
    font.family: root.typography ? root.typography.iconFamily : "JetBrains Mono"
    font.pixelSize: root.iconSize
    horizontalAlignment: Text.AlignHCenter
    verticalAlignment: Text.AlignVCenter
    renderType: Text.NativeRendering
}
