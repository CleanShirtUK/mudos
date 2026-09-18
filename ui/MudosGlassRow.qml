import QtQuick
import QtQuick.Effects
import Mudos.Poc 1.0

Item {
    id: root

    property string label: ""
    property string value: ""
    property string glyph: ""
    property bool selected: false
    property bool rowEnabled: true
    property bool interactive: true
    property real uiScale: 1
    property var typography
    property var luluPalette
    property var canonicalTexture
    property var canonicalCoordinateRoot
    property size canonicalSize: Qt.size(1280, 720)
    property rect canonicalRect: Qt.rect(0, 0, width, height)
    signal activated()

    readonly property real rowRadius: 20 * uiScale

    Rectangle {
        anchors.fill: parent
        radius: root.rowRadius
        color: luluPalette ? luluPalette.transparent : "transparent"
        clip: true

        MudosGlassItem {
            anchors.fill: parent
            backdrop: root.canonicalTexture
            canonicalSize: root.canonicalSize
            canonicalRect: root.canonicalRect
            cornerRadius: root.rowRadius
            ior: 1.08
            glassDepth: 0.18
            refractionPixels: 40 * root.uiScale
            dispersionIor: 0
            diffusionPixels: 5 * root.uiScale
            transmission: 0.82
            bevelWidthPx: 0
            bulgeStrength: 20
            edgeLightStrength: 0
            transparentOutsideMask: true
            opacity: root.rowEnabled ? (root.selected ? 1 : 0.72) : 0.42
        }

        Row {
            anchors.fill: parent
            anchors.leftMargin: 22 * root.uiScale
            anchors.rightMargin: 22 * root.uiScale
            spacing: 12 * root.uiScale

            MudosIcon {
                visible: root.glyph !== ""
                width: 24 * root.uiScale
                height: parent.height
                glyph: root.glyph
                typography: root.typography
                iconSize: root.typography
                    ? root.typography.size("body", 20) : 20 * root.uiScale
                semanticColor: root.luluPalette
                    ? root.luluPalette.primaryText : "white"
            }

            Text {
                LayoutMirroring.enabled: false
                width: Math.max(0, parent.width - (root.value !== ""
                    ? valueText.implicitWidth + 18 * root.uiScale : 0)
                    - (root.glyph !== "" ? 36 * root.uiScale : 0))
                height: parent.height
                text: root.label
                color: root.luluPalette ? root.luluPalette.primaryText : "white"
                font.family: root.typography ? root.typography.interfaceFamily : "JetBrains Mono"
                font.weight: Font.Bold
                font.pixelSize: root.typography
                    ? root.typography.size("body", 18) : 18 * root.uiScale
                elide: Text.ElideRight
                verticalAlignment: Text.AlignVCenter
                layer.enabled: true
                layer.effect: MultiEffect {
                    shadowEnabled: true
                    shadowColor: "#000000"
                    shadowOpacity: 0.35
                    shadowBlur: 0.2
                    shadowVerticalOffset: 1 * root.uiScale
                }
            }

            Text {
                id: valueText
                visible: root.value !== ""
                width: implicitWidth
                height: parent.height
                text: root.value
                color: root.luluPalette ? root.luluPalette.secondaryText : "#c9c0dc"
                font.family: root.typography ? root.typography.interfaceFamily : "JetBrains Mono"
                font.pixelSize: root.typography
                    ? root.typography.size("body", 16) : 16 * root.uiScale
                elide: Text.ElideRight
                horizontalAlignment: Text.AlignRight
                verticalAlignment: Text.AlignVCenter
            }
        }

        MouseArea {
            anchors.fill: parent
            enabled: root.rowEnabled && root.interactive
            onClicked: root.activated()
        }
    }
}
