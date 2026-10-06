import QtQuick
import "MudosAssetCatalog.js" as MudosAssetCatalog

Item {
    id: root

    property string name: "info"
    property string glyph: ""
    property var typography
    property color semanticColor: "white"
    property real iconSize: 20

    implicitWidth: glyphMetrics.advanceWidth
    implicitHeight: root.iconSize

    TextMetrics {
        id: glyphMetrics
        text: root.glyph || MudosAssetCatalog.icon(root.name)
        font.family: root.typography ? root.typography.iconFamily : "monospace"
        font.pixelSize: root.iconSize
    }

    Text {
        x: root.width / 2
            - (glyphMetrics.tightBoundingRect.x
               + glyphMetrics.tightBoundingRect.width / 2)
        y: 0
        width: glyphMetrics.advanceWidth
        height: root.height
        text: glyphMetrics.text
        color: root.semanticColor
        font.family: root.typography ? root.typography.iconFamily : "monospace"
        font.pixelSize: root.iconSize
        verticalAlignment: Text.AlignVCenter
        renderType: Text.NativeRendering
    }
}
