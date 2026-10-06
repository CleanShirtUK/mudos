import QtQuick

// Fixed-slot Nerd Font glyph with optical centering based on painted bounds.
Item {
    id: root

    property string glyph: ""
    property string fontFamily: "monospace"
    property real glyphSize: 18
    property real targetPaintedHeight: glyphSize * 0.72
    property color glyphColor: "white"

    width: glyphSize
    height: glyphSize

    TextMetrics {
        id: baseMetrics
        text: root.glyph
        font.family: root.fontFamily
        font.pixelSize: root.glyphSize
    }

    readonly property real normalizedGlyphSize: root.glyphSize
        * root.targetPaintedHeight / Math.max(1, baseMetrics.tightBoundingRect.height)

    TextMetrics {
        id: metrics
        text: root.glyph
        font.family: root.fontFamily
        font.pixelSize: root.normalizedGlyphSize
    }

    Text {
        x: parent.width / 2
            - (metrics.tightBoundingRect.x + metrics.tightBoundingRect.width / 2)
        y: 0
        width: metrics.advanceWidth
        height: parent.height
        text: root.glyph
        color: root.glyphColor
        font.family: root.fontFamily
        font.pixelSize: root.normalizedGlyphSize
        horizontalAlignment: Text.AlignLeft
        verticalAlignment: Text.AlignVCenter
        renderType: Text.NativeRendering
    }
}
