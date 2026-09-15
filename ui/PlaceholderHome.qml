import QtQuick

Item {
    property string title: ""
    property string description: ""
    property real uiScale: 1
    property var typography
    property var luluPalette

    Column {
        x: 0
        y: 0
        spacing: 14 * uiScale

        Text {
            anchors.horizontalCenter: parent.horizontalCenter
            text: title.toUpperCase()
            color: luluPalette.headingAccent
            font.family: typography ? typography.majorHeadingFamily : "JetBrains Mono"
            font.weight: typography ? typography.majorHeadingWeight : Font.Black
            font.pixelSize: typography ? typography.size("section", 26) : 26 * uiScale
            font.letterSpacing: 4 * uiScale
        }

        Text {
            anchors.horizontalCenter: parent.horizontalCenter
            text: description
            color: luluPalette.mutedText
            font.family: typography ? typography.interfaceFamily : "JetBrains Mono"
            font.pixelSize: typography ? typography.size("secondary", 22) : 22 * uiScale
        }
    }
}
