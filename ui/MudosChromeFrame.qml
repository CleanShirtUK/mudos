import QtQuick

// Generic themeable edge treatment. It is presentation chrome only: it never
// changes the geometry or interaction ownership of the framed surface.
Item {
    id: root
    property var luluPalette
    property real uiScale: 1
    property real cornerRadius: 0
    property bool raised: true
    readonly property real edge: luluPalette && luluPalette.bevelChrome
        ? luluPalette.chromeWidth * uiScale : 0
    visible: edge > 0
    z: 100

    readonly property color outerTopLeft: root.raised
        ? (root.luluPalette ? root.luluPalette.chromeHighlight : "white")
        : (root.luluPalette ? root.luluPalette.chromeShadow : "#808080")
    readonly property color outerBottomRight: root.raised
        ? (root.luluPalette ? root.luluPalette.chromeDarkShadow : "black")
        : (root.luluPalette ? root.luluPalette.chromeLight : "#dfdfdf")
    readonly property color innerTopLeft: root.raised
        ? (root.luluPalette ? root.luluPalette.chromeLight : "#dfdfdf")
        : (root.luluPalette ? root.luluPalette.chromeDarkShadow : "black")
    readonly property color innerBottomRight: root.raised
        ? (root.luluPalette ? root.luluPalette.chromeShadow : "#808080")
        : (root.luluPalette ? root.luluPalette.chromeHighlight : "white")
    Rectangle { x: 0; y: 0; width: parent.width; height: root.edge; color: root.outerTopLeft }
    Rectangle { x: 0; y: 0; width: root.edge; height: parent.height; color: root.outerTopLeft }
    Rectangle { x: 0; y: parent.height - root.edge; width: parent.width; height: root.edge; color: root.outerBottomRight }
    Rectangle { x: parent.width - root.edge; y: 0; width: root.edge; height: parent.height; color: root.outerBottomRight }
    Rectangle { x: root.edge; y: root.edge; width: Math.max(0, parent.width - 2 * root.edge); height: root.edge; color: root.innerTopLeft }
    Rectangle { x: root.edge; y: root.edge; width: root.edge; height: Math.max(0, parent.height - 2 * root.edge); color: root.innerTopLeft }
    Rectangle { x: root.edge; y: parent.height - 2 * root.edge; width: Math.max(0, parent.width - 2 * root.edge); height: root.edge; color: root.innerBottomRight }
    Rectangle { x: parent.width - 2 * root.edge; y: root.edge; width: root.edge; height: Math.max(0, parent.height - 2 * root.edge); color: root.innerBottomRight }
}
