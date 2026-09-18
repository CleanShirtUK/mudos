import QtQuick
import Mudos.Poc 1.0

Item {
    id: root
    property string category: "System"
    property var settings: []
    property int selectedIndex: 0
    property real uiScale: 1
    property var typography
    property var luluPalette
    property var canonicalTexture
    property var canonicalCoordinateRoot
    property size canonicalSize: Qt.size(1280, 720)
    property bool active: false
    signal actionRequested(string key)
    property int visibleRows: 7

    property real pageProgress: 0
    onActiveChanged: {
        if (active) {
            pageProgress = 0
            pageAnimation.restart()
        } else {
            pageAnimation.stop()
            pageProgress = 0
        }
    }

    opacity: pageProgress
    transform: Translate { y: (1 - root.pageProgress) * 32 * root.uiScale }

    MudosGlassItem {
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.bottom: parent.bottom
        anchors.leftMargin: 48 * root.uiScale
        anchors.rightMargin: 48 * root.uiScale
        anchors.topMargin: 48 * root.uiScale
        anchors.bottomMargin: 58 * root.uiScale
        backdrop: root.canonicalTexture
        canonicalSize: root.canonicalSize
        cornerRadius: 28 * root.uiScale
        refractionPixels: 80 * root.uiScale
        dispersionIor: 0.0175
        diffusionPixels: 5 * root.uiScale
        transmission: 1
        bevelWidthPx: 3 * root.uiScale
        bulgeStrength: 100
        edgeLightStrength: 0.10
        transparentOutsideMask: true
        opacity: 0.8
    }

    NumberAnimation {
        id: pageAnimation
        target: root
        property: "pageProgress"
        to: 1
        duration: 500
        easing.type: Easing.OutQuint
    }

    Text {
        x: 76 * root.uiScale
        y: 76 * root.uiScale
        text: root.category.toUpperCase()
        color: luluPalette.headingAccent
        font.family: typography.majorHeadingFamily
        font.weight: typography.majorHeadingWeight
        font.pixelSize: typography.size("section", 30)
        font.letterSpacing: 5 * root.uiScale
    }

    Flickable {
        x: 76 * root.uiScale
        y: 142 * root.uiScale
        width: parent.width - 152 * root.uiScale
        height: 7 * 58 * root.uiScale + 6 * 10 * root.uiScale
        clip: true
        contentWidth: width
        contentHeight: rowColumn.height
        contentY: Math.max(0, Math.min(contentHeight - height,
            root.selectedIndex * (58 * root.uiScale + 10 * root.uiScale)))
        boundsBehavior: Flickable.StopAtBounds

        Column {
            id: rowColumn
            width: parent.width
            spacing: 10 * root.uiScale

             Repeater {
                model: root.settings
                delegate: MudosGlassRow {
                required property int index
                required property var modelData
                width: parent.width
                height: 58 * root.uiScale
                label: modelData.label
                value: String(modelData.value || "")
                selected: index === root.selectedIndex
                rowEnabled: true
                interactive: modelData.writable === true && modelData.kind === "action"
                uiScale: root.uiScale
                typography: root.typography
                luluPalette: root.luluPalette
                canonicalTexture: root.canonicalTexture
                canonicalCoordinateRoot: root.canonicalCoordinateRoot
                canonicalSize: root.canonicalSize
                onActivated: root.actionRequested(modelData.key)
                }
            }
        }
    }
}
