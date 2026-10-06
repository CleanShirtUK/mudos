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
    property FontLoader iconFont: FontLoader {
        source: themeFonts.icons || ""
    }

    readonly property var themeRoles: themeFonts.roles || ({})
    function familyForRole(role, fallback) {
        var face = themeRoles[role] || fallback
        if (face === "bold" && boldFont.status === FontLoader.Ready) return boldFont.name
        if ((face === "heavy" || face === "display")
                && extraBoldFont.status === FontLoader.Ready) return extraBoldFont.name
        if ((face === "icons" || face === "icon") && iconFont.status === FontLoader.Ready)
            return iconFont.name
        if (regularFont.status === FontLoader.Ready) return regularFont.name
        return "sans-serif"
    }

    readonly property string bundledFamily: familyForRole("interface", "regular")
    readonly property string displayFamily: familyForRole("display", "heavy")
    readonly property int displayWeight: themeRoles.display === "bold" ? Font.Bold : Font.Black
    readonly property string interfaceFamily: familyForRole("interface", "regular")
    readonly property string majorHeadingFamily: familyForRole("majorHeading", "heavy")
    readonly property string iconFamily: familyForRole("icon", "icons")
    // Qt's Black weight maps to the ExtraBlack face when the font provides it.
    readonly property int majorHeadingWeight: themeRoles.majorHeading === "bold" ? Font.Bold : Font.Black

    function size(role, value) {
        return value * uiScale
    }
}
