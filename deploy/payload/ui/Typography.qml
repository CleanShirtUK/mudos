import QtQuick

QtObject {
    property real uiScale: 1

    readonly property string displayFamily: "JetBrains Mono"
    readonly property int displayWeight: Font.Black
    readonly property string interfaceFamily: "JetBrains Mono"
    readonly property string majorHeadingFamily: "JetBrains Mono"
    // Qt's Black weight maps to the ExtraBlack face when the font provides it.
    readonly property int majorHeadingWeight: Font.Black

    function size(role, value) {
        return value * uiScale
    }
}
