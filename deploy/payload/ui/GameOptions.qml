import QtQuick
import QtQuick.Effects

Item {
    id: options

    property var game: null
    property string view: "menu"
    property int selectedIndex: 0
    property var results: []
    property string query: ""
    property string titleDraft: ""
    property string errorMessage: ""
    property bool busy: false
    property real uiScale: 1
    property var typography
    property var luluPalette
    signal activated()
    signal backed()
    signal queryEdited(string value)
    signal titleEdited(string value)

    function mixColor(from, to, progress) {
        return Qt.rgba(
            from.r + (to.r - from.r) * progress,
            from.g + (to.g - from.g) * progress,
            from.b + (to.b - from.b) * progress,
            from.a + (to.a - from.a) * progress)
    }

    readonly property var menuEntries: ["Change Match", "Edit Metadata"]
    readonly property var editEntries: ["Edit Title", "Clear Title Override",
        game && game.artwork_suppressed ? "Restore Image" : "Remove Image"]

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
                visible: options.view === "search"
                text: "Change Match  /  Search SGDB"
                color: options.luluPalette.secondaryText
                font.family: options.typography.interfaceFamily
                font.pixelSize: options.typography.size("body", 15)
            }

            TextInput {
                id: queryEditor
                visible: options.view === "search"
                text: options.query
                color: options.luluPalette.primaryText
                selectionColor: options.luluPalette.accent
                font.family: options.typography.interfaceFamily
                font.pixelSize: options.typography.size("body", 18)
                width: parent.width
                focus: options.view === "search"
                onTextChanged: options.queryEdited(text)
                onAccepted: options.activated()
                Keys.onPressed: function(event) {
                    if (event.key === Qt.Key_Escape || event.key === Qt.Key_Backspace) {
                        options.backed()
                        event.accepted = true
                    }
                }
            }

            Text {
                visible: options.view === "title"
                text: "Edit Title"
                color: options.luluPalette.secondaryText
                font.family: options.typography.interfaceFamily
                font.pixelSize: options.typography.size("body", 15)
            }
            TextInput {
                id: titleEditor
                visible: options.view === "title"
                text: options.titleDraft
                color: options.luluPalette.primaryText
                selectionColor: options.luluPalette.accent
                font.family: options.typography.interfaceFamily
                font.pixelSize: options.typography.size("body", 20)
                width: parent.width
                focus: options.view === "title"
                onTextChanged: options.titleEdited(text)
                onAccepted: options.activated()
                Keys.onPressed: function(event) {
                    if (event.key === Qt.Key_Escape || event.key === Qt.Key_Backspace) {
                        options.backed()
                        event.accepted = true
                    }
                }
            }

            Text {
                visible: options.busy || options.errorMessage !== ""
                text: options.busy ? "Searching..." : options.errorMessage
                color: options.busy ? options.luluPalette.secondaryText : options.luluPalette.warning
                font.family: options.typography.interfaceFamily
                font.pixelSize: options.typography.size("body", 15)
                width: parent.width
                wrapMode: Text.WordWrap
            }

            ListView {
                id: entryList
                visible: options.view === "menu" || options.view === "edit"
                width: parent.width
                height: Math.min(contentHeight, 330 * options.uiScale)
                spacing: 8 * options.uiScale
                model: options.view === "menu" ? options.menuEntries : options.editEntries
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
                id: resultList
                visible: options.view === "search"
                width: parent.width
                height: Math.min(contentHeight, 390 * options.uiScale)
                spacing: 8 * options.uiScale
                model: options.results
                delegate: Rectangle {
                    id: resultRow
                    required property int index
                    required property var modelData
                    width: resultList.width
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
                    Column {
                        anchors.fill: parent
                        anchors.margins: 10 * options.uiScale
                        spacing: 3 * options.uiScale
                        Text {
                            text: resultRow.modelData.title + "  [" + resultRow.modelData.id + "]"
                            color: resultRow.textColor
                            font.family: options.typography.interfaceFamily
                            font.pixelSize: options.typography.size("body", 18)
                            elide: Text.ElideRight
                            width: parent.width
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
                            text: resultRow.modelData.platforms && resultRow.modelData.platforms.length
                                ? resultRow.modelData.platforms.join(", ") : "Platform metadata unavailable"
                            color: resultRow.textColor
                            font.family: options.typography.interfaceFamily
                            font.pixelSize: options.typography.size("hint", 12)
                            elide: Text.ElideRight
                            width: parent.width
                        }
                    }
                }
            }

            Item { width: 1; height: 1 }
            Text {
                        text: options.view === "search" ? "Choose    Back" : "Select    Back"
                color: options.luluPalette.secondaryText
                font.family: options.typography.interfaceFamily
                font.pixelSize: options.typography.size("hint", 14)
            }
        }
    }
}
