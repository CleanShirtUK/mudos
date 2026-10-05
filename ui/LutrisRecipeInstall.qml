import QtQuick

Item {
    id: root
    visible: false
    z: 510
    property int flowStage: 0 // search results, recipes, requirements, file picker
    property string apiUrl: ""
    property var rows: []
    property var requirements: []
    property var files: ({})
    property int selectedIndex: 0
    property string title: ""
    property string gameSlug: ""
    property string installerSlug: ""
    property string message: ""
    property bool busy: false
    property var selectedRow: selectedIndex >= 0 && selectedIndex < rows.length ? rows[selectedIndex] : null
    property string requirementId: ""
    signal closed()
    signal submitted(string jobId)

    function get(path, callback) {
        var xhr = new XMLHttpRequest()
        xhr.open("GET", root.apiUrl + path)
        xhr.onreadystatechange = function() {
            if (xhr.readyState !== XMLHttpRequest.DONE) return
            busy = false
            try {
                var data = JSON.parse(xhr.responseText || "{}")
                if (xhr.status !== 200) throw new Error(data.error || "Request failed")
                callback(data)
            } catch (error) { message = error.message }
        }
        xhr.onerror = function() {
            busy = false
            message = "Lutris search is unavailable"
        }
        xhr.send()
    }

    function openForQuery(query) {
        visible = true
        flowStage = 0
        selectedIndex = 0
        title = query
        message = "Searching Lutris installers…"
        busy = true
        get("/lutris/search?query=" + encodeURIComponent(query), function(data) {
            rows = data.games || []
            message = rows.length ? "Choose a game" : "No Lutris games found for that search"
        })
    }

    function showRecipes(game) {
        title = String(game.name || gameSlug)
        gameSlug = String(game.slug || "")
        flowStage = 1
        selectedIndex = 0
        rows = []
        message = "Loading Lutris installer recipes…"
        busy = true
        get("/lutris/recipes?slug=" + encodeURIComponent(gameSlug), function(data) {
            rows = data.recipes || []
            message = rows.length ? "Choose an installer recipe" : "No installer recipes are available"
        })
    }

    function showRequirements(recipe) {
        installerSlug = String(recipe.installer_slug || "")
        requirements = (recipe.requirements || []).filter(function(item) {
            return item.required && item.local
        })
        files = ({})
        selectedIndex = 0
        if (!requirements.length) {
            submitInstall()
            return
        }
        flowStage = 2
        rows = requirements.slice(0)
        message = "Select each file required by this installation"
    }

    function browseFor(requirement) {
        requirementId = String(requirement.file_id)
        flowStage = 3
        genericFilePicker.open("Required file: " + String(requirement.label || requirement.filename))
    }

    function move(delta) {
        if (flowStage === 3) { genericFilePicker.move(delta); return }
        if (busy || !rows.length) return
        var lastIndex = flowStage === 2 ? requirements.length : rows.length - 1
        selectedIndex = Math.max(0, Math.min(lastIndex, selectedIndex + delta))
    }

    function activate() {
        if (flowStage === 3) { genericFilePicker.activate(); return }
        if (busy) return
        if (flowStage === 0) {
            if (selectedRow) showRecipes(selectedRow)
        } else if (flowStage === 1) {
            if (selectedRow) showRequirements(selectedRow)
        } else if (flowStage === 2) {
            if (selectedIndex === requirements.length) submitInstall()
            else if (selectedRow) browseFor(selectedRow)
        }
    }

    function submitInstall() {
        for (var index = 0; index < requirements.length; index++) {
            if (!files[String(requirements[index].file_id)]) {
                message = "Select: " + String(requirements[index].label || requirements[index].filename)
                selectedIndex = index
                return
            }
        }
        busy = true
        message = "Submitting Lutris installation…"
        var xhr = new XMLHttpRequest()
        xhr.open("POST", root.apiUrl + "/lutris/install-recipe")
        xhr.setRequestHeader("Content-Type", "application/json")
        xhr.onreadystatechange = function() {
            if (xhr.readyState !== XMLHttpRequest.DONE) return
            busy = false
            try {
                var data = JSON.parse(xhr.responseText || "{}")
                if (xhr.status !== 200) throw new Error(data.error || "Installation could not be submitted")
                message = "Installation added to Downloads"
                visible = false
                submitted(String(data.token || ""))
            } catch (error) { message = error.message }
        }
        xhr.onerror = function() {
            busy = false
            message = "Lutris installation could not be submitted"
        }
        xhr.send(JSON.stringify({title: title, game_slug: gameSlug,
                                 installer_slug: installerSlug, files: files}))
    }

    function back() {
        if (busy) return
        if (flowStage === 3) {
            genericFilePicker.back()
        } else if (flowStage === 2) {
            flowStage = 1
            message = "Choose an installer recipe"
        } else if (flowStage === 1) {
            visible = false
            closed()
        } else {
            visible = false
            closed()
        }
    }

    Rectangle { anchors.fill: parent; color: "#ee090d12" }
    Rectangle {
        anchors.centerIn: parent
        width: Math.min(parent.width * 0.82, 980)
        height: Math.min(parent.height * 0.82, 660)
        radius: 14
        color: "#f018202b"
        border.color: "#9bb9d9"
        border.width: 2
        Column {
            anchors.fill: parent
            anchors.margins: 28
            spacing: 14
            Text {
                width: parent.width
                text: root.flowStage === 0 ? "LUTRIS GAME SEARCH" : root.title
                color: "white"; font.pixelSize: 27; font.bold: true; elide: Text.ElideRight
            }
            Text {
                width: parent.width
                text: root.message
                color: "#d9e3ef"; font.pixelSize: 17; wrapMode: Text.Wrap; elide: Text.ElideMiddle
            }
             ListView {
                id: recipeRows
                width: parent.width
                height: Math.max(80, parent.height - (root.flowStage === 2 ? 190 : 130))
                clip: true
                interactive: false
                model: root.rows
                delegate: Rectangle {
                    required property var modelData
                    required property int index
                    width: recipeRows.width
                    height: 50
                    radius: 5
                    color: index === root.selectedIndex ? "#385e84" : "transparent"
                    Text {
                        anchors.fill: parent; anchors.leftMargin: 12
                        verticalAlignment: Text.AlignVCenter
                        color: "white"; font.pixelSize: 16; elide: Text.ElideMiddle
                        text: root.flowStage === 0
                              ? String(modelData.name || "") + (modelData.year ? " (" + modelData.year + ")" : "")
                              : root.flowStage === 1
                                ? String(modelData.title || modelData.installer_slug || "") + " — " + String(modelData.runner || "")
                                : root.flowStage === 2
                                   ? String(modelData.label || modelData.filename)
                                     + (root.files[String(modelData.file_id)] ? "  ✓" : "  — select file")
                                   : ""
                    }
                }
            }
            Rectangle {
                width: recipeRows.width
                height: 50
                radius: 5
                visible: root.flowStage === 2
                color: root.selectedIndex === root.requirements.length ? "#385e84" : "#202b38"
                border.color: "#9bb9d9"
                border.width: 1
                Text {
                    anchors.fill: parent
                    anchors.leftMargin: 12
                    verticalAlignment: Text.AlignVCenter
                    color: "white"
                    font.pixelSize: 17
                    font.bold: true
                    text: "Install"
                }
            }
            Text {
                width: parent.width
                text: root.flowStage === 2
                      ? "A: Select file / Start install   B: Back   ↑/↓: Choose"
                      : "A: Select   B: Back   ↑/↓: Choose"
                color: "#aebdce"; font.pixelSize: 15
            }
        }
    }
    MudosFilePicker {
        id: genericFilePicker
        apiUrl: root.apiUrl
        anchors.fill: parent
        visible: root.visible && root.flowStage === 3
        onFileSelected: function(path) {
            root.files[root.requirementId] = path
            root.files = Object.assign({}, root.files)
            root.flowStage = 2
            root.message = "File selected. Choose any remaining required files."
        }
        onCanceled: {
            root.flowStage = 2
            root.message = "Select each file required by this installation"
        }
    }
}
