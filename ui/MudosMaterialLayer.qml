pragma ComponentBehavior: Bound
import QtQuick

// Static, bounded theme material renderer. This layer paints only inside its
// owner's geometry and never participates in input or implicit sizing.
Item {
    id: root
    property var luluPalette
    property string role: "panel"
    property real cornerRadius: 0
    property real uiScale: 1
    property real selectionProgress: 0
    property bool forceHidden: false
    readonly property var profile: luluPalette ? luluPalette.material(role) : ({})
    readonly property bool gradientActive: profile.style === "linearGradient"
    readonly property bool active: gradientActive
        || Object.keys(outerEdges).length > 0 || Object.keys(innerEdges).length > 0
    readonly property string resolvedStyle: profile.style || "flat"
    readonly property string resolvedOrientation: profile.orientation || "vertical"
    readonly property var stops: profile.stops || []
    readonly property var outerEdges: profile.edges || ({})
    readonly property var innerEdges: profile.innerEdges || ({})
    implicitWidth: 0
    implicitHeight: 0
    visible: active && !forceHidden
    enabled: false
    clip: true

    function stopPosition(index) {
        return stops.length > 0 ? Number(stops[Math.min(index, stops.length - 1)].position) : 0
    }
    function stopColor(index) {
        return stops.length > 0 ? String(stops[Math.min(index, stops.length - 1)].color) : "transparent"
    }
    function edgeValue(edges, side, key) {
        var edge = edges[side] || ({})
        return Number(edge[key] || 0)
    }
    function edgeColor(edges, side) {
        var edge = edges[side] || ({})
        return String(edge.color || "transparent")
    }
    function edgeNames(edges) { return Object.keys(edges || ({})) }

    Rectangle {
        id: materialFill
        anchors.fill: parent
        radius: root.cornerRadius
        antialiasing: true
        visible: root.gradientActive
        gradient: Gradient {
            orientation: root.profile.orientation === "horizontal"
                ? Gradient.Horizontal : Gradient.Vertical
            GradientStop { position: root.stopPosition(0); color: root.stopColor(0) }
            GradientStop { position: root.stopPosition(1); color: root.stopColor(1) }
            GradientStop { position: root.stopPosition(2); color: root.stopColor(2) }
            GradientStop { position: root.stopPosition(3); color: root.stopColor(3) }
            GradientStop { position: root.stopPosition(4); color: root.stopColor(4) }
            GradientStop { position: root.stopPosition(5); color: root.stopColor(5) }
            GradientStop { position: root.stopPosition(6); color: root.stopColor(6) }
            GradientStop { position: root.stopPosition(7); color: root.stopColor(7) }
        }
    }

    Repeater {
        model: root.edgeNames(root.outerEdges)
        delegate: Rectangle {
            required property string modelData
            readonly property string side: modelData
            readonly property real thickness: root.edgeValue(root.outerEdges, side, "width") * root.uiScale
            color: root.edgeColor(root.outerEdges, side)
            visible: thickness > 0
            x: side === "left" ? 0 : side === "right" ? root.width - thickness
                : root.cornerRadius
            y: side === "top" ? 0 : side === "bottom" ? root.height - thickness
                : root.cornerRadius
            width: side === "left" || side === "right" ? thickness
                : Math.max(0, root.width - 2 * root.cornerRadius)
            height: side === "top" || side === "bottom" ? thickness
                : Math.max(0, root.height - 2 * root.cornerRadius)
        }
    }

    Repeater {
        model: root.edgeNames(root.innerEdges)
        delegate: Rectangle {
            required property string modelData
            readonly property string side: modelData
            readonly property real thickness: root.edgeValue(root.innerEdges, side, "width") * root.uiScale
            readonly property real outerTop: root.edgeValue(root.outerEdges, "top", "width") * root.uiScale
            readonly property real outerBottom: root.edgeValue(root.outerEdges, "bottom", "width") * root.uiScale
            readonly property real outerLeft: root.edgeValue(root.outerEdges, "left", "width") * root.uiScale
            readonly property real outerRight: root.edgeValue(root.outerEdges, "right", "width") * root.uiScale
            color: root.edgeColor(root.innerEdges, side)
            visible: thickness > 0
            x: side === "left" ? outerLeft : side === "right"
                ? root.width - outerRight - thickness
                : root.cornerRadius + outerLeft
            y: side === "top" ? outerTop : side === "bottom"
                ? root.height - outerBottom - thickness
                : root.cornerRadius + outerTop
            width: side === "left" || side === "right" ? thickness
                : Math.max(0, root.width - 2 * root.cornerRadius - outerLeft - outerRight)
            height: side === "top" || side === "bottom" ? thickness
                : Math.max(0, root.height - 2 * root.cornerRadius - outerTop - outerBottom)
        }
    }

    Rectangle {
        anchors.fill: parent
        radius: root.cornerRadius
        color: root.luluPalette
            ? Qt.rgba(root.luluPalette.focusIndicator.r,
                      root.luluPalette.focusIndicator.g,
                      root.luluPalette.focusIndicator.b,
                      0.14 * root.selectionProgress)
            : "transparent"
        border.color: root.luluPalette
            ? Qt.rgba(root.luluPalette.focusIndicator.r,
                      root.luluPalette.focusIndicator.g,
                      root.luluPalette.focusIndicator.b,
                      root.selectionProgress)
            : "transparent"
        border.width: root.selectionProgress > 0 ? (1 + 2 * root.selectionProgress) * root.uiScale : 0
        visible: root.selectionProgress > 0
    }
}
