import QtQuick
import QtQuick.Effects
import "MudosAssetCatalog.js" as MudosAssetCatalog

Item {
    id: root

    property string name: "info"
    property string glyph: ""
    property var typography
    property color semanticColor: "white"
    property real iconSize: 20
    readonly property var iconAsset: {
        if (typeof mudosTheme === "undefined") return ({})
        var themeRevision = mudosTheme.activeId
        if (typeof mudosTheme.iconAsset === "function")
            return mudosTheme.iconAsset(root.name) || ({})
        var legacyUrl = typeof mudosTheme.iconUrl === "function"
            ? mudosTheme.iconUrl(root.name) : ""
        return legacyUrl ? ({url: legacyUrl, renderMode: "tint", format: "svg"}) : ({})
    }
    readonly property string overrideUrl: String(iconAsset.url || "")
    readonly property string renderMode: iconAsset.renderMode || "tint"
    readonly property bool paintsOriginal: overrideUrl !== "" && renderMode === "original"
    readonly property bool appliesSemanticTint: overrideUrl !== "" && renderMode === "tint"
    readonly property bool usesFallbackGlyph: overrideUrl === ""

    implicitWidth: glyphMetrics.advanceWidth
    implicitHeight: root.iconSize

    TextMetrics {
        id: glyphMetrics
        text: root.glyph || MudosAssetCatalog.icon(root.name)
        font.family: root.typography ? root.typography.iconFamily : "monospace"
        font.pixelSize: root.iconSize
    }

    Text {
        objectName: "semanticFallbackText"
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
        visible: !root.overrideUrl
    }
    Image {
        id: overrideImage
        objectName: "semanticTintImage"
        anchors.centerIn: parent
        width: root.iconSize
        height: root.iconSize
        source: root.overrideUrl
        sourceSize: Qt.size(width * 2, height * 2)
        fillMode: Image.PreserveAspectFit
        visible: false
    }
    Image {
        id: originalImage
        objectName: "semanticOriginalImage"
        anchors.centerIn: parent
        width: root.iconSize
        height: root.iconSize
        source: root.paintsOriginal ? root.overrideUrl : ""
        sourceSize: Qt.size(width * 2, height * 2)
        fillMode: Image.PreserveAspectFit
        // An empty source paints nothing; keep the item enabled so the source
        // binding can switch synchronously across live theme changes.
        visible: true
    }
    MultiEffect {
        objectName: "semanticTintEffect"
        anchors.fill: overrideImage
        source: overrideImage
        colorization: 1
        colorizationColor: root.semanticColor
        visible: root.overrideUrl !== "" && root.renderMode === "tint"
    }
}
