import QtQuick

QtObject {
    readonly property var config: typeof mudosTheme !== "undefined" ? mudosTheme.motion : ({})
    readonly property var roles: config.roles || ({})
    function enabled(role) {
        var item = roles[role] || ({})
        return config.enabled !== false && item.enabled !== false
    }
    function duration(role, fallback) {
        var item = roles[role] || ({})
        var defaults = ({navigation: 250, focus: 180, surface: 500, fade: 180,
                         overlay: 180, status: 220, intro: 360})
        var baseline = defaults[role] || fallback
        var configured = item.duration === undefined ? baseline : Number(item.duration)
        return fallback * configured / baseline
            * (config.durationScale === undefined ? 1 : Number(config.durationScale))
    }
    function easing(role, fallback) {
        var item = roles[role] || ({})
        var curve = item.easing || fallback || "linear"
        switch (curve) {
        case "inCubic": return Easing.InCubic
        case "outCubic": return Easing.OutCubic
        case "inOutCubic": return Easing.InOutCubic
        case "inQuint": return Easing.InQuint
        case "outQuint": return Easing.OutQuint
        case "inOutQuint": return Easing.InOutQuint
        case "inQuad": return Easing.InQuad
        case "outQuad": return Easing.OutQuad
        case "inOutQuad": return Easing.InOutQuad
        default: return Easing.Linear
        }
    }
    function speed(role, fallback) {
        var item = roles[role] || ({})
        var configured = item.speed === undefined ? fallback : Number(item.speed)
        return isFinite(configured) ? Math.max(0, Math.min(10, configured)) : fallback
    }
}
