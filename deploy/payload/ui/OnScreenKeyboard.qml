import QtQuick

Item {
    id: keyboard

    property string fieldLabel: "Text entry"
    property string value: ""
    property int maximumLength: 128
    property real uiScale: 1
    property var typography
    property var luluPalette
    property int selectedRow: 0
    property int selectedColumn: 0
    property bool editing: false
    readonly property var keyRows: [
        ["1", "2", "3", "4", "5", "6", "7", "8", "9", "0"],
        ["Q", "W", "E", "R", "T", "Y", "U", "I", "O", "P"],
        ["A", "S", "D", "F", "G", "H", "J", "K", "L"],
        ["Z", "X", "C", "V", "B", "N", "M", ".", "-", "_"] ,
        ["SPACE", "BACKSPACE", "ACCEPT", "CANCEL"]
    ]

    signal accepted(string text)
    signal cancelled()

    anchors.fill: parent
    visible: false
    z: 100

    function open(initialValue, label, limit) {
        value = initialValue || ""
        fieldLabel = label || "Text entry"
        maximumLength = limit || 128
        selectedRow = 1
        selectedColumn = 0
        editing = true
        visible = true
        editor.text = value
        editor.forceActiveFocus()
    }

    function close() {
        editing = false
        visible = false
        editor.focus = false
    }

    function move(rowDelta, columnDelta) {
        if (!editing)
            return
        if (rowDelta !== 0) {
            selectedRow = Math.max(0, Math.min(keyRows.length - 1, selectedRow + rowDelta))
            selectedColumn = Math.min(selectedColumn, keyRows[selectedRow].length - 1)
        } else {
            selectedColumn = Math.max(0, Math.min(keyRows[selectedRow].length - 1,
                                                   selectedColumn + columnDelta))
        }
    }

    function activate(row, column) {
        var key = keyRows[row][column]
        if (key === "ACCEPT") {
            var submitted = value
            close()
            accepted(submitted)
        } else if (key === "CANCEL") {
            close()
            cancelled()
        } else if (key === "BACKSPACE") {
            value = value.slice(0, -1)
            editor.text = value
        } else if (key === "SPACE") {
            append(" ")
        } else {
            append(key)
        }
    }

    function append(text) {
        if (value.length >= maximumLength)
            return
        value += text
        editor.text = value
    }

    Rectangle {
        anchors.fill: parent
        color: Qt.rgba(0.01, 0.02, 0.04, 0.88)
    }

    Rectangle {
        anchors.centerIn: parent
        width: Math.min(parent.width - 48 * keyboard.uiScale, 1120 * keyboard.uiScale)
        height: Math.min(parent.height - 48 * keyboard.uiScale, 590 * keyboard.uiScale)
        color: keyboard.luluPalette.cardSurface
        border.color: keyboard.luluPalette.focusIndicator
        border.width: keyboard.uiScale
        radius: 12 * keyboard.uiScale

        Column {
            anchors.fill: parent
            anchors.margins: 28 * keyboard.uiScale
            spacing: 16 * keyboard.uiScale

            Text {
                text: keyboard.fieldLabel.toUpperCase()
                color: keyboard.luluPalette.accent
                font.family: keyboard.typography.interfaceFamily
                font.pixelSize: keyboard.typography.size("hint", 14)
            }

            Rectangle {
                width: parent.width
                height: 58 * keyboard.uiScale
                color: keyboard.luluPalette.glassTint
                border.color: keyboard.luluPalette.accent
                border.width: keyboard.uiScale
                radius: 6 * keyboard.uiScale

                Text {
                    anchors.fill: parent
                    anchors.leftMargin: 16 * keyboard.uiScale
                    anchors.rightMargin: 16 * keyboard.uiScale
                    text: keyboard.value || " "
                    color: keyboard.luluPalette.primaryText
                    font.family: keyboard.typography.interfaceFamily
                    font.pixelSize: keyboard.typography.size("body", 24)
                    verticalAlignment: Text.AlignVCenter
                    elide: Text.ElideRight
                }
            }

            Column {
                width: parent.width
                spacing: 8 * keyboard.uiScale
                Repeater {
                    model: keyboard.keyRows.length
                    delegate: Row {
                        required property int index
                        width: parent.width
                        height: 64 * keyboard.uiScale
                        spacing: 8 * keyboard.uiScale
                        anchors.horizontalCenter: parent.horizontalCenter

                        Repeater {
                            model: keyboard.keyRows[index]
                            delegate: Rectangle {
                                required property int index
                                readonly property string key: modelData
                                width: (parent.width - (keyboard.keyRows[index].length - 1) * 8 * keyboard.uiScale)
                                    / keyboard.keyRows[index].length
                                height: 64 * keyboard.uiScale
                                radius: 7 * keyboard.uiScale
                                color: keyboard.selectedRow === parent.parent.index
                                    && keyboard.selectedColumn === index
                                    ? keyboard.luluPalette.focusIndicator : keyboard.luluPalette.glassTint
                                border.color: keyboard.selectedRow === parent.parent.index
                                    && keyboard.selectedColumn === index
                                    ? keyboard.luluPalette.accent : keyboard.luluPalette.glassBorder
                                border.width: keyboard.uiScale

                                Text {
                                    anchors.fill: parent
                                    text: parent.key
                                    color: keyboard.selectedRow === parent.parent.index
                                        && keyboard.selectedColumn === parent.index
                                        ? keyboard.luluPalette.selectedText : keyboard.luluPalette.primaryText
                                    font.family: keyboard.typography.interfaceFamily
                                    font.pixelSize: keyboard.typography.size("body", parent.key.length > 1 ? 14 : 20)
                                    horizontalAlignment: Text.AlignHCenter
                                    verticalAlignment: Text.AlignVCenter
                                }
                                MouseArea {
                                    anchors.fill: parent
                                    onClicked: keyboard.activate(parent.parent.index, parent.index)
                                }
                            }
                        }
                    }
                }
            }

            Text {
                text: "A  Select     B  Cancel"
                color: keyboard.luluPalette.secondaryText
                font.family: keyboard.typography.interfaceFamily
                font.pixelSize: keyboard.typography.size("hint", 14)
            }
        }
    }

    // Keep a real text editor focused so physical keyboard input remains useful.
    TextInput {
        id: editor
        opacity: 0
        width: 1
        height: 1
        text: keyboard.value
        maximumLength: keyboard.maximumLength
        onTextChanged: if (keyboard.editing && text !== keyboard.value) keyboard.value = text
        Keys.onPressed: function(event) {
            if (event.key === Qt.Key_Up)
                keyboard.move(-1, 0)
            else if (event.key === Qt.Key_Down)
                keyboard.move(1, 0)
            else if (event.key === Qt.Key_Left)
                keyboard.move(0, -1)
            else if (event.key === Qt.Key_Right)
                keyboard.move(0, 1)
            else if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter)
                keyboard.activate(keyboard.selectedRow, keyboard.selectedColumn)
            else if (event.key === Qt.Key_Escape) {
                keyboard.close()
                keyboard.cancelled()
            }
            else
                return
            event.accepted = true
        }
    }
}
