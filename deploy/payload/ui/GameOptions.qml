import QtQuick
import QtQuick.Effects

Item {
    id: options

    property var game: null
    property string view: "menu"
    property int selectedIndex: 0
    property string errorMessage: ""
    property var artworkCandidates: []
    property bool uninstallSupported: false
    property real uiScale: 1
    property var typography
    property var luluPalette
    signal activated()
    signal backed()
    signal uninstallRequested()

    function mixColor(from, to, progress) {
        return Qt.rgba(
            from.r + (to.r - from.r) * progress,
            from.g + (to.g - from.g) * progress,
            from.b + (to.b - from.b) * progress,
            from.a + (to.a - from.a) * progress)
    }

    readonly property var menuEntries: {
        var entries = ["Change Artwork"]
        if (game && game.artwork_override)
            entries.push("Restore Automatic Artwork")
        if (uninstallSupported)
            entries.push("Uninstall")
        return entries
    }

    anchors.fill: parent
    visible: game !== null
    z: 80

    Rectangle {
        anchors.fill: parent
        color: options.luluPalette.overlayBackdrop
    }

    Rectangle {
        id: panel
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.bottom: parent.bottom
        width: Math.min(parent.width * 0.48, 560 * options.uiScale)
        color: options.luluPalette.overlaySurface
        radius: 10 * options.uiScale
        border.color: options.luluPalette.glassBorder
        border.width: options.uiScale
        clip: true

        Column {
            anchors.fill: parent
            anchors.margins: 24 * options.uiScale
            spacing: 18 * options.uiScale

            Text {
                text: "GAME OPTIONS"
                color: options.luluPalette.headingAccent
                font.family: options.typography.majorHeadingFamily
                font.weight: options.typography.majorHeadingWeight
                font.pixelSize: options.typography.size("section", 30)
                font.letterSpacing: 5 * options.uiScale
                layer.enabled: true
                layer.effect: MultiEffect {
                    shadowEnabled: true
                    shadowColor: "#000000"
                    shadowOpacity: 0.35
                    shadowBlur: 0.2
                    shadowVerticalOffset: 1 * options.uiScale
                }
            }
            Text {
                text: options.game ? options.game.title : ""
                color: options.luluPalette.primaryText
                font.family: options.typography.displayFamily
                font.weight: options.typography.displayWeight
                font.pixelSize: options.typography.size("display", 34)
                width: parent.width
                elide: Text.ElideRight
            }

            Text {
                visible: options.view === "artwork" || options.view === "confirm"
                text: options.view === "confirm" ? "UNINSTALL?  This removes the local installed content." : "Choose cover artwork"
                color: options.luluPalette.secondaryText
                font.family: options.typography.interfaceFamily
                font.pixelSize: options.typography.size("body", 15)
            }

            Text {
                visible: options.view === "artwork"
                text: "SteamGridDB alternatives"
                color: options.luluPalette.secondaryText
                font.family: options.typography.interfaceFamily
                font.pixelSize: options.typography.size("body", 15)
            }
            Text {
                visible: options.errorMessage !== ""
                text: options.errorMessage
                color: options.luluPalette.warning
                font.family: options.typography.interfaceFamily
                font.pixelSize: options.typography.size("body", 15)
                width: parent.width
                wrapMode: Text.WordWrap
            }

            ListView {
                id: entryList
                visible: options.view === "menu"
                width: parent.width
                height: Math.min(contentHeight, 330 * options.uiScale)
                spacing: 8 * options.uiScale
                model: options.menuEntries
                delegate: Rectangle {
                    id: rowDelegate
                    required property int index
                    required property string modelData
                    width: entryList.width
                    height: 58 * options.uiScale
                    radius: 8 * options.uiScale
                    z: index === options.selectedIndex ? 1 : 0
                    property real selectionProgress: index === options.selectedIndex ? 1 : 0
                    scale: 1 + 0.01 * selectionProgress
                    transformOrigin: Item.Center
                    readonly property color surfaceColor: options.mixColor(
                        options.luluPalette.cardSurface, options.luluPalette.focusedCardSurface,
                        selectionProgress)
                    readonly property color rowBorderColor: options.mixColor(
                        options.luluPalette.glassBorder, options.luluPalette.focusIndicator,
                        selectionProgress)
                    readonly property color textColor: options.mixColor(
                        options.luluPalette.navigationText, options.luluPalette.primaryText,
                        selectionProgress)
                    Behavior on selectionProgress {
                        NumberAnimation {
                            duration: 180
                            easing.type: Easing.OutQuint
                        }
                    }
                    color: surfaceColor
                    border.color: rowBorderColor
                    border.width: options.uiScale
                    Text {
                        anchors.fill: parent
                        anchors.leftMargin: 18 * options.uiScale
                        text: rowDelegate.modelData
                        color: rowDelegate.textColor
                        font.family: options.typography.interfaceFamily
                        font.pixelSize: options.typography.size("body", 18)
                        verticalAlignment: Text.AlignVCenter
                        elide: Text.ElideRight
                        layer.enabled: true
                        layer.effect: MultiEffect {
                            shadowEnabled: true
                            shadowColor: "#000000"
                            shadowOpacity: 0.35
                            shadowBlur: 0.2
                            shadowVerticalOffset: 1 * options.uiScale
                        }
                    }
                }
            }

            ListView {
                id: artworkList
                visible: options.view === "artwork"
                width: parent.width
                height: Math.min(contentHeight, 390 * options.uiScale)
                spacing: 8 * options.uiScale
                model: options.artworkCandidates
                delegate: Rectangle {
                    id: artworkRow
                    required property int index
                    required property var modelData
                    width: artworkList.width
                    height: 58 * options.uiScale
                    radius: 8 * options.uiScale
                    color: index === options.selectedIndex ? options.luluPalette.focusedCardSurface : options.luluPalette.cardSurface
                    border.color: index === options.selectedIndex ? options.luluPalette.focusIndicator : options.luluPalette.glassBorder
                    Text {
                        anchors.fill: parent
                        anchors.leftMargin: 18 * options.uiScale
                        text: (artworkRow.modelData.current ? "[CURRENT] " : "") + "SGDB cover"
                        color: options.luluPalette.primaryText
                        font.family: options.typography.interfaceFamily
                        font.pixelSize: options.typography.size("body", 18)
                        verticalAlignment: Text.AlignVCenter
                        elide: Text.ElideRight
                    }
                    Image {
                        anchors.right: parent.right
                        anchors.rightMargin: 12 * options.uiScale
                        anchors.verticalCenter: parent.verticalCenter
                        width: 34 * options.uiScale
                        height: 48 * options.uiScale
                        source: artworkRow.modelData.thumbnail
                        fillMode: Image.PreserveAspectFit
                        asynchronous: true
                        cache: true
                    }
                }
            }


            Item { width: 1; height: 1 }
            Text {
                text: options.view === "artwork" ? "Select    Back" : options.view === "confirm" ? "Confirm    Back" : "Select    Back"
                color: options.luluPalette.secondaryText
                font.family: options.typography.interfaceFamily
                font.pixelSize: options.typography.size("hint", 14)
            }
        }
    }
}
