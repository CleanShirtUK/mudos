import QtQuick

QtObject {
    readonly property var labels: typeof mudosTheme !== "undefined" ? mudosTheme.labels : ({})
    readonly property var styles: typeof mudosTheme !== "undefined" ? mudosTheme.textStyles : ({})
    function homeLabel(identity) {
        var home = labels.home || ({})
        var canonical = ({system: "System", store: "Store", library: "Library", recent: "Recent"})
        return home[identity] || canonical[identity] || identity
    }
    function homeTitle(identity) {
        var value = homeLabel(identity)
        var style = styles.homeTitle || ({})
        if (style.case === "upper") return value.toUpperCase()
        if (style.case === "lower") return value.toLowerCase()
        return value
    }
    function homeTitleSpacing(uiScale) {
        var style = styles.homeTitle || ({})
        return Number(style.letterSpacing || 0) * uiScale
    }
}
