import QtQuick
import QtQuick.Effects
import "MudosAssetCatalog.js" as MudosAssetCatalog

// Fixed-slot Nerd Font glyph with optical centering based on painted bounds.
Item {
    id: root

    property string glyph: ""
    property string fontFamily: "monospace"
    property real glyphSize: 18
    property real targetPaintedHeight: glyphSize * 0.72
    property real uiScale: 1
    property real safeInset: Math.min(1.5 * uiScale, glyphSize * 0.1)
    property color glyphColor: "white"
    property string iconName: ""
    readonly property var iconAsset: {
        if (iconName === "" || typeof mudosTheme === "undefined") return ({})
        var themeRevision = mudosTheme.activeId
        if (typeof mudosTheme.iconAsset === "function")
            return mudosTheme.iconAsset(iconName) || ({})
        var legacyUrl = typeof mudosTheme.iconUrl === "function"
            ? mudosTheme.iconUrl(iconName) : ""
        return legacyUrl ? ({url: legacyUrl, renderMode: "tint", format: "svg"}) : ({})
    }
    readonly property string overrideUrl: String(iconAsset.url || "")
    readonly property string renderMode: iconAsset.renderMode || "tint"
    readonly property bool paintsOriginal: overrideUrl !== "" && renderMode === "original"
    readonly property bool appliesSemanticTint: overrideUrl !== "" && renderMode === "tint"
    readonly property bool usesFallbackGlyph: overrideUrl === ""
    readonly property string resolvedGlyph: iconName !== ""
        ? MudosAssetCatalog.icon(iconName) : glyph

    width: glyphSize
    height: glyphSize

    readonly property real availablePaintedSize: Math.max(0,
        glyphSize - 2 * safeInset)

    TextMetrics {
        id: baseMetrics
        text: root.resolvedGlyph
        font.family: root.fontFamily
        font.pixelSize: root.glyphSize
    }

    readonly property real heightFitScale: Math.min(root.targetPaintedHeight,
        root.availablePaintedSize) / Math.max(1, baseMetrics.tightBoundingRect.height)
    readonly property real widthFitScale: root.availablePaintedSize
        / Math.max(1, baseMetrics.tightBoundingRect.width)
    readonly property real normalizedGlyphSize: root.glyphSize
        * Math.min(heightFitScale, widthFitScale)
    readonly property bool fittedToWidth: widthFitScale < heightFitScale

    TextMetrics {
        id: metrics
        text: root.resolvedGlyph
        font.family: root.fontFamily
        font.pixelSize: root.normalizedGlyphSize
    }

    readonly property rect paintedBounds: Qt.rect(
        glyphText.x + metrics.tightBoundingRect.x,
        glyphText.y + glyphText.baselineOffset + metrics.tightBoundingRect.y,
        metrics.tightBoundingRect.width, metrics.tightBoundingRect.height)

    Text {
        id: glyphText
        objectName: "statusGlyphText"
        x: parent.width / 2
            - (metrics.tightBoundingRect.x + metrics.tightBoundingRect.width / 2)
        y: parent.height / 2 - metrics.tightBoundingRect.height / 2
            - baselineOffset - metrics.tightBoundingRect.y
        width: metrics.advanceWidth
        height: parent.height
        // Semantic IDs resolve to the bundled Nerd Font glyph unless the
        // active theme supplies an SVG override. Keep the Text item bound to
        // the same fallback glyph used by TextMetrics and optical fitting.
        text: root.resolvedGlyph
        color: root.glyphColor
        font.family: root.fontFamily
        font.pixelSize: root.normalizedGlyphSize
        horizontalAlignment: Text.AlignLeft
        verticalAlignment: Text.AlignTop
        renderType: Text.NativeRendering
        visible: !root.overrideUrl
    }
    Image {
        id: iconImage
        objectName: "statusTintImage"
        anchors.centerIn: parent
        width: root.availablePaintedSize
        height: root.availablePaintedSize
        source: root.overrideUrl
        sourceSize: Qt.size(width * 2, height * 2)
        fillMode: Image.PreserveAspectFit
        visible: false
    }
    Image {
        id: originalIconImage
        objectName: "statusOriginalImage"
        anchors.centerIn: parent
        width: root.availablePaintedSize
        height: root.availablePaintedSize
        source: root.paintsOriginal ? root.overrideUrl : ""
        sourceSize: Qt.size(width * 2, height * 2)
        fillMode: Image.PreserveAspectFit
        // An empty source paints nothing; keep the item enabled so the source
        // binding can switch synchronously across live theme changes.
        visible: true
    }
    MultiEffect {
        objectName: "statusTintEffect"
        anchors.fill: iconImage
        source: iconImage
        colorization: 1
        colorizationColor: root.glyphColor
        visible: root.overrideUrl !== "" && root.renderMode === "tint"
    }
}
