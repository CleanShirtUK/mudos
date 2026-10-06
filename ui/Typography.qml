import QtQuick

QtObject {
    property real uiScale: 1
    readonly property var themeFonts: typeof mudosTheme !== "undefined" ? mudosTheme.fonts : ({})

    property FontLoader regularFont: FontLoader {
        source: themeFonts.regular || ""
    }
    property FontLoader boldFont: FontLoader {
        source: themeFonts.bold || ""
    }
    property FontLoader extraBoldFont: FontLoader {
        source: themeFonts.heavy || ""
    }

    readonly property string bundledFamily: regularFont.status === FontLoader.Ready
        ? regularFont.name : "JetBrains Mono"
    readonly property string displayFamily: bundledFamily
    readonly property int displayWeight: Font.Black
    readonly property string interfaceFamily: bundledFamily
    readonly property string majorHeadingFamily: bundledFamily
    readonly property string iconFamily: bundledFamily
    // Qt's Black weight maps to the ExtraBlack face when the font provides it.
    readonly property int majorHeadingWeight: Font.Black

    function size(role, value) {
        return value * uiScale
    }
}
