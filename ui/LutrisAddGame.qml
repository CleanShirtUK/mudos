import QtQuick

Item {
    id: root
    anchors.fill: parent
    visible: false
    z: 500
    property string apiUrl: ""
    property var games: []
    property int gameIndex: 0
    property int executableIndex: 0
    property int step: 0
    property string message: ""
    property bool busy: false
    property var selectedGame: gameIndex >= 0 && gameIndex < games.length ? games[gameIndex] : null
    property var executables: selectedGame ? selectedGame.executables : []
    signal closed()
    signal registered()

    function open() {
        visible = true
        step = 0
        message = "Scanning Mudos Lutris storage…"
        busy = true
        var xhr = new XMLHttpRequest()
        xhr.open("GET", root.apiUrl + "/lutris/local-candidates")
        xhr.onreadystatechange = function() {
            if (xhr.readyState !== XMLHttpRequest.DONE) return
            busy = false
            try {
                var data = JSON.parse(xhr.responseText || "{}")
                if (xhr.status !== 200) throw new Error(data.error || "Could not scan Lutris storage")
                games = data.games || []
                gameIndex = 0
                message = games.length ? "Choose an existing game folder" :
                    "No unregistered executable games found under ~/Games/Executables/lutris"
            } catch (error) { message = error.message }
        }
        xhr.onerror = function() {
            busy = false
            message = "Lutris storage scan failed"
        }
        xhr.send()
    }

    function move(delta) {
        if (busy) return
        var count = step === 0 ? games.length : executables.length
        if (count > 0) {
            if (step === 0) gameIndex = Math.max(0, Math.min(count - 1, gameIndex + delta))
            else executableIndex = Math.max(0, Math.min(count - 1, executableIndex + delta))
        }
    }

    function activate() {
        if (busy) return
        if (step === 0) {
            if (!selectedGame) return
            step = 1
            executableIndex = 0
            message = "Choose the game's Linux executable"
            return
        }
        if (!selectedGame || !executables.length) return
        busy = true
        message = "Registering with Lutris…"
        var payload = {title: selectedGame.name, directory: selectedGame.directory,
                       executable: executables[executableIndex], arguments: ""}
        var xhr = new XMLHttpRequest()
        xhr.open("POST", root.apiUrl + "/lutris/register-local")
        xhr.setRequestHeader("Content-Type", "application/json")
        xhr.onreadystatechange = function() {
            if (xhr.readyState !== XMLHttpRequest.DONE) return
            busy = false
            try {
                var data = JSON.parse(xhr.responseText || "{}")
                if (xhr.status !== 200) throw new Error(data.error || "Lutris registration failed")
                message = "Added " + (data.title || selectedGame.name) + " to Lutris and Mudos Library"
                registered()
            } catch (error) { message = error.message }
        }
        xhr.onerror = function() {
            busy = false
            message = "Lutris registration failed"
        }
        xhr.send(JSON.stringify(payload))
    }

    function back() {
        if (busy) return
        if (step === 1) { step = 0; message = "Choose an existing game folder" }
        else { visible = false; closed() }
    }

    Rectangle {
        anchors.fill: parent
        color: "#ee090d12"
    }
    Rectangle {
        anchors.centerIn: parent
        width: Math.min(parent.width * 0.78, 900)
        height: Math.min(parent.height * 0.78, 620)
        radius: 14
        color: "#f018202b"
        border.color: "#9bb9d9"
        border.width: 2
        Column {
            anchors.fill: parent
            anchors.margins: 30
            spacing: 18
            Text {
                width: parent.width
                text: "ADD A LOCAL LUTRIS GAME"
                color: "white"
                font.pixelSize: 28
                font.bold: true
                wrapMode: Text.Wrap
            }
            Text {
                width: parent.width
                text: root.message
                color: "#d9e3ef"
                font.pixelSize: 19
                wrapMode: Text.Wrap
            }
            ListView {
                id: choices
                width: parent.width
                height: Math.max(120, parent.height - 150)
                clip: true
                interactive: false
                model: root.step === 0 ? root.games : root.executables
                delegate: Rectangle {
                    required property var modelData
                    required property int index
                    width: choices.width
                    height: 52
                    radius: 6
                    color: index === (root.step === 0 ? root.gameIndex : root.executableIndex)
                           ? "#385e84" : "transparent"
                    Text {
                        anchors.fill: parent
                        anchors.leftMargin: 14
                        verticalAlignment: Text.AlignVCenter
                        elide: Text.ElideMiddle
                        text: root.step === 0 ? String(modelData.name || "") : String(modelData)
                        color: "white"
                        font.pixelSize: 17
                    }
                }
            }
            Text {
                width: parent.width
                text: "A: Select   B: Back   ↑/↓: Choose"
                color: "#aebdce"
                font.pixelSize: 15
            }
        }
    }
}
