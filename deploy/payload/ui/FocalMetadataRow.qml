import QtQuick

Item {
    id: root
    property string glyph: ""
    property string text: ""
    property string fontFamily: "JetBrains Mono"
    property string iconFamily: fontFamily
    property color textColor: "white"
    property real uiScale: 1
    property real glyphSize: 18 * uiScale
    property real textSize: 17 * uiScale
    property real glyphColumnWidth: 18 * uiScale
    property bool wrapText: false
    property int maximumLineCount: 1
    property bool fitText: false
    property real minimumTextSize: 9 * uiScale
    readonly property real leftTextMargin: glyphColumnWidth + 8 * uiScale
    implicitHeight: Math.max(22 * uiScale, metadataText.implicitHeight)

    StatusGlyph {
        anchors.left: parent.left
        anchors.top: root.wrapText ? parent.top : undefined
        anchors.verticalCenter: root.wrapText ? undefined : parent.verticalCenter
        glyph: root.glyph
        fontFamily: root.iconFamily
        glyphSize: root.glyphSize
        glyphColor: root.textColor
        width: root.glyphColumnWidth
    }
    Text {
        id: metadataText
        anchors.left: parent.left
        anchors.leftMargin: root.leftTextMargin
        anchors.right: parent.right
        anchors.top: root.wrapText ? parent.top : undefined
        anchors.verticalCenter: root.wrapText ? undefined : parent.verticalCenter
        text: root.text
        color: root.textColor
        font.family: root.fontFamily
        font.pixelSize: root.textSize
        fontSizeMode: root.fitText ? Text.Fit : Text.FixedSize
        minimumPixelSize: root.fitText ? root.minimumTextSize : root.textSize
        wrapMode: root.wrapText ? Text.WordWrap : Text.NoWrap
        maximumLineCount: root.maximumLineCount > 0 ? root.maximumLineCount : -1
        elide: root.wrapText || root.fitText ? Text.ElideNone : Text.ElideRight
        height: root.wrapText ? implicitHeight : parent.height
    }
}
