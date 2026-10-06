import QtQuick

Item {
    id: root
    visible: false
    z: 20
    property string apiUrl: ""
    property var luluPalette
    property var typography
    property string prompt: "Select a file"
    property string folder: ""
    property string parentFolder: ""
    property string message: ""
    property var entries: []
    property int selectedIndex: 0
    property bool busy: false
    property var selectedEntry: selectedIndex >= 0 && selectedIndex < entries.length
        ? entries[selectedIndex] : null
    signal fileSelected(string path)
    signal canceled()

    function open(requestedPrompt) {
        prompt = requestedPrompt || "Select a file"
        visible = true
        message = "Choose a folder or file"
        load("")
    }

    function load(path) {
        busy = true
        var xhr = new XMLHttpRequest()
        xhr.open("GET", root.apiUrl + "/files?path=" + encodeURIComponent(path || ""))
        xhr.onreadystatechange = function() {
            if (xhr.readyState !== XMLHttpRequest.DONE) return
            busy = false
            try {
                var data = JSON.parse(xhr.responseText || "{}")
                if (xhr.status !== 200) throw new Error(data.error || "Folder could not be opened")
                folder = String(data.path || "")
                parentFolder = String(data.parent || "")
                entries = data.entries || []
                selectedIndex = 0
            } catch (error) { message = error.message }
        }
        xhr.onerror = function() {
            busy = false
            message = "Folder could not be opened"
        }
        xhr.send()
    }

    function move(delta) {
        if (!busy && entries.length)
            selectedIndex = Math.max(0, Math.min(entries.length - 1, selectedIndex + delta))
    }

    function activate() {
        if (busy || !selectedEntry) return
        if (selectedEntry.directory) load(selectedEntry.path)
        else {
            visible = false
            fileSelected(String(selectedEntry.path))
        }
    }

    function back() {
        if (busy) return
        if (parentFolder) load(parentFolder)
        else {
            visible = false
            canceled()
        }
    }

    Rectangle { anchors.fill: parent; color: root.luluPalette ? root.luluPalette.overlayBackdrop : "#ee090d12" }
    Rectangle {
        anchors.centerIn: parent
        width: Math.min(parent.width * 0.82, 980)
        height: Math.min(parent.height * 0.82, 660)
        radius: root.luluPalette ? root.luluPalette.radius("overlay", 14) : 14
        color: root.luluPalette ? root.luluPalette.overlaySurface : "#f018202b"
        border.color: root.luluPalette ? root.luluPalette.glassBorder : "#9bb9d9"
        border.width: 2
        MudosChromeFrame { anchors.fill: parent; luluPalette: root.luluPalette; cornerRadius: parent.radius }
        Column {
            anchors.fill: parent
            anchors.margins: 28
            spacing: 14
            Text {
                width: parent.width
                text: root.prompt
                color: root.luluPalette ? root.luluPalette.headingAccent : "white"; font.family: root.typography ? root.typography.majorHeadingFamily : "sans-serif"; font.pixelSize: 27; font.bold: true; elide: Text.ElideRight
            }
            Text {
                width: parent.width
                text: root.folder + (root.folder ? "\n" : "") + root.message
                color: root.luluPalette ? root.luluPalette.secondaryText : "#d9e3ef"; font.family: root.typography ? root.typography.interfaceFamily : "sans-serif"; font.pixelSize: 16; wrapMode: Text.Wrap; elide: Text.ElideMiddle
            }
            ListView {
                id: fileRows
                width: parent.width
                height: Math.max(100, parent.height - 130)
                clip: true
                interactive: false
                model: root.entries
                delegate: Rectangle {
                    required property var modelData
                    required property int index
                    width: fileRows.width
                    height: 48
                    radius: root.luluPalette ? root.luluPalette.radius("row", 5) : 5
                    color: index === root.selectedIndex && root.luluPalette ? root.luluPalette.selectionSurface : "transparent"
                    Text {
                        anchors.fill: parent; anchors.leftMargin: 12
                        verticalAlignment: Text.AlignVCenter
                        color: index === root.selectedIndex && root.luluPalette ? root.luluPalette.selectedText : root.luluPalette ? root.luluPalette.primaryText : "white"; font.family: root.typography ? root.typography.interfaceFamily : "sans-serif"; font.pixelSize: 16; elide: Text.ElideMiddle
                        text: (modelData.directory ? "Folder  " : "File  ") + String(modelData.name || "")
                    }
                }
            }
            Text {
                width: parent.width
                text: "A: Open/select   B: Back   ↑/↓: Choose"
                color: root.luluPalette ? root.luluPalette.secondaryText : "#aebdce"; font.family: root.typography ? root.typography.interfaceFamily : "sans-serif"; font.pixelSize: 15
            }
        }
    }
}
