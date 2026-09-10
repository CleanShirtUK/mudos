import QtQuick

QtObject {
    property real uiScale: 1

    readonly property string displayFamily: "Zalando Sans Condensed Black"
    readonly property int displayWeight: Font.Black
    readonly property string interfaceFamily: "JetBrains Mono"

    function size(role, value) {
        return value * uiScale
    }
}
