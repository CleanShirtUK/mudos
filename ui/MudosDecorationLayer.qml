pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Effects

// Four engine-owned corner slots. Theme data can select safe SVG assets and
// Bounded tint/opacity/scale only; it cannot place artwork over content.
Item {
    id: root
    property var luluPalette
    property string role: "panel"
    property real uiScale: 1
    property real cornerRadius: 0
    readonly property var slots: luluPalette ? luluPalette.decorations(role) : ({})
    readonly property var slotNames: ["topLeft", "topRight", "bottomLeft", "bottomRight"]
    readonly property real baseSlotSize: 12 * uiScale
    readonly property real edgeInset: Math.max(4 * uiScale, cornerRadius + 2 * uiScale)
    implicitWidth: 0
    implicitHeight: 0
    enabled: false
    visible: Object.keys(slots).length > 0

    function tint(slot) {
        var tintRole = slot.tint || "secondaryText"
        return luluPalette ? luluPalette.role(tintRole, luluPalette.secondaryText) : "white"
    }

    Repeater {
        model: root.slotNames
        delegate: Item {
            objectName: "decoration-slot-" + modelData
            required property string modelData
            readonly property string slotName: modelData
            readonly property var config: root.slots[slotName] || null
            readonly property real scaleFactor: config ? Number(config.scale || 1) : 1
            readonly property real slotSize: root.baseSlotSize * scaleFactor
            width: slotSize
            height: slotSize
            visible: !!config && !!config.asset
            x: slotName === "topLeft" || slotName === "bottomLeft"
                ? root.edgeInset : root.width - root.edgeInset - width
            y: slotName === "topLeft" || slotName === "topRight"
                ? root.edgeInset : root.height - root.edgeInset - height
            rotation: slotName === "bottomLeft" || slotName === "bottomRight" ? 180 : 0

            Image {
                id: ornament
                anchors.fill: parent
                source: parent.config ? parent.config.asset : ""
                sourceSize: Qt.size(width * 2, height * 2)
                fillMode: Image.PreserveAspectFit
                asynchronous: true
                cache: true
                mirror: parent.slotName === "topRight" || parent.slotName === "bottomRight"
                opacity: parent.config ? Number(parent.config.opacity === undefined ? 1 : parent.config.opacity) : 0
                visible: false
            }
            MultiEffect {
                anchors.fill: ornament
                source: ornament
                colorization: 1
                colorizationColor: root.tint(parent.config || ({}))
                visible: ornament.status === Image.Ready
            }
        }
    }
}
