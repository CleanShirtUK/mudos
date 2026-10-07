import QtQuick

QtObject {
    readonly property var labels: typeof mudosTheme !== "undefined" ? mudosTheme.labels : ({})
    readonly property var styles: typeof mudosTheme !== "undefined" ? mudosTheme.textStyles : ({})
    function homeLabel(identity) {
        var home = labels.home || ({})
        var canonical = ({system: "System", store: "Store", library: "Library", recent: "Recent"})
        return home[identity] || canonical[identity] || identity
    }
    function viewLabel(identity, fallback) {
        var views = labels.views || ({})
        var canonical = ({settings: "Settings", utilities: "Utilities",
                         library: "Library", installable: "Installable",
                         downloads: "Downloads"})
        return views[identity] || fallback || canonical[identity] || identity
    }
    function format(value, styleName) {
        var text = String(value === undefined || value === null ? "" : value)
        var style = styles[styleName] || ({})
        if (style.case === "upper") return text.toUpperCase()
        if (style.case === "lower") return text.toLowerCase()
        return text
    }
    function homeTitle(identity) {
        return format(homeLabel(identity), "homeTitle")
    }
    function homeTitleSpacing(uiScale) {
        return letterSpacing("homeTitle", uiScale)
    }
    function viewTitle(identity, fallback) {
        return format(viewLabel(identity, fallback), "viewTitle")
    }
    function viewTitleText(value) {
        return format(value, "viewTitle")
    }
    function letterSpacing(styleName, uiScale) {
        var style = styles[styleName] || ({})
        return Number(style.letterSpacing || 0) * uiScale
    }
}
