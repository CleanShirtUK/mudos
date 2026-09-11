import QtQuick

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

    readonly property var menuEntries: ["Change Match", "Edit Metadata"]
    readonly property var editEntries: ["Edit Title", "Clear Title Override",
        game && game.artwork_suppressed ? "Restore Image" : "Remove Image"]

    anchors.fill: parent
    visible: game !== null
    z: 80

    Rectangle {
        anchors.fill: parent
        color: Qt.rgba(0.01, 0.02, 0.04, 0.72)
    }

    Rectangle {
        id: panel
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.bottom: parent.bottom
        width: Math.min(parent.width * 0.48, 560 * options.uiScale)
        color: Qt.rgba(0.035, 0.05, 0.09, 0.98)
        border.color: options.luluPalette.focusIndicator
        border.width: options.uiScale
        clip: true

        Column {
            anchors.fill: parent
            anchors.margins: 32 * options.uiScale
            spacing: 18 * options.uiScale

            Text {
                text: "GAME OPTIONS"
                color: options.luluPalette.accent
                font.family: options.typography.interfaceFamily
                font.pixelSize: options.typography.size("hint", 14)
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
                    required property int index
                    required property string modelData
                    width: entryList.width
                    height: 54 * options.uiScale
                    radius: 8 * options.uiScale
                    color: index === options.selectedIndex ? options.luluPalette.focusIndicator : options.luluPalette.cardSurface
                    border.color: index === options.selectedIndex ? options.luluPalette.accent : options.luluPalette.glassBorder
                    border.width: options.uiScale
                    Text {
                        anchors.fill: parent
                        anchors.leftMargin: 18 * options.uiScale
                        text: parent.modelData
                        color: index === options.selectedIndex ? options.luluPalette.selectedText : options.luluPalette.primaryText
                        font.family: options.typography.interfaceFamily
                        font.pixelSize: options.typography.size("body", 18)
                        verticalAlignment: Text.AlignVCenter
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
                    required property int index
                    required property var modelData
                    width: resultList.width
                    height: 62 * options.uiScale
                    radius: 8 * options.uiScale
                    color: index === options.selectedIndex ? options.luluPalette.focusIndicator : options.luluPalette.cardSurface
                    border.color: index === options.selectedIndex ? options.luluPalette.accent : options.luluPalette.glassBorder
                    border.width: options.uiScale
                    Column {
                        anchors.fill: parent
                        anchors.margins: 10 * options.uiScale
                        spacing: 3 * options.uiScale
                        Text {
                            text: modelData.title + "  [" + modelData.id + "]"
                            color: options.luluPalette.primaryText
                            font.family: options.typography.interfaceFamily
                            font.pixelSize: options.typography.size("body", 16)
                            elide: Text.ElideRight
                            width: parent.width
                        }
                        Text {
                            text: modelData.platforms && modelData.platforms.length
                                ? modelData.platforms.join(", ") : "Platform metadata unavailable"
                            color: options.luluPalette.secondaryText
                            font.family: options.typography.interfaceFamily
                            font.pixelSize: options.typography.size("hint", 12)
                        }
                    }
                }
            }

            Item { width: 1; height: 1 }
            Text {
                text: options.view === "search" ? "A  Choose    B  Back" : "A  Select    B  Back"
                color: options.luluPalette.secondaryText
                font.family: options.typography.interfaceFamily
                font.pixelSize: options.typography.size("hint", 14)
            }
        }
    }
}
