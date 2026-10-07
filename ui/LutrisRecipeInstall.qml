import QtQuick

Item {
    id: root
    visible: false
    z: 510
    property int flowStage: 0 // search results, recipes, requirements, file picker
    property string apiUrl: ""
    property var luluPalette
    property var typography
    property var canonicalTexture
    property var canonicalCoordinateRoot
    property size canonicalSize: Qt.size(1280, 720)
    property real uiScale: 1
    property real expandedContentX: 0
    property real expandedContentY: 0
    property real expandedContentWidth: width
    property real expandedContentBottom: height
    property var rows: []
    property var requirements: []
    property var files: ({})
    property int selectedIndex: 0
    property string title: ""
    property string gameSlug: ""
    property string installerSlug: ""
    property string message: ""
    property bool busy: false
    property var selectedRow: flowStage === 0
        ? (selectedIndex > 0 && selectedIndex - 1 < rows.length ? rows[selectedIndex - 1] : null)
        : (selectedIndex >= 0 && selectedIndex < rows.length ? rows[selectedIndex] : null)
    property string requirementId: ""
    readonly property real panelWidth: Math.min(expandedContentWidth, 780 * uiScale)
    readonly property real panelHeight: Math.min(Math.max(1, expandedContentBottom - expandedContentY), 610 * uiScale)
    readonly property real panelX: expandedContentX + (expandedContentWidth - panelWidth) / 2
    readonly property real panelY: expandedContentY + (expandedContentBottom - expandedContentY - panelHeight) / 2
    signal closed()
    signal submitted(string jobId)
    signal searchEditRequested()

    function openSearch() {
        visible = true
        flowStage = 0
        selectedIndex = 0
        title = ""
        rows = []
        busy = false
        message = "Enter a game title to search Lutris"
    }

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
        selectedIndex = 1
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
        if (busy || (!rows.length && flowStage !== 0)) return
        var lastIndex = flowStage === 2 ? requirements.length : rows.length - 1
        if (flowStage === 0)
            lastIndex = rows.length
        selectedIndex = Math.max(0, Math.min(lastIndex, selectedIndex + delta))
    }

    function activate() {
        if (flowStage === 3) { genericFilePicker.activate(); return }
        if (busy) return
        if (flowStage === 0) {
            if (selectedIndex === 0) searchEditRequested()
            else if (selectedRow) showRecipes(selectedRow)
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

    Rectangle { anchors.fill: parent; color: root.luluPalette.overlayBackdrop }
    MudosPanelSurface {
        id: panel
        objectName: "lutrisPopupPanel"
        x: root.panelX
        y: root.panelY
        width: root.panelWidth
        height: root.panelHeight
        cornerRadius: root.luluPalette.radius("panel", 18) * root.uiScale
        uiScale: root.uiScale
        luluPalette: root.luluPalette
        canonicalTexture: root.canonicalTexture
        canonicalCoordinateRoot: root.canonicalCoordinateRoot
        canonicalSize: root.canonicalSize
        mappingItem: panel
        materialRole: "overlay"
        decorationRole: "overlay"
        clip: true
        Column {
            anchors.fill: parent
            anchors.leftMargin: 24 * root.uiScale
            anchors.rightMargin: 24 * root.uiScale
            anchors.topMargin: 12 * root.uiScale
            anchors.bottomMargin: 14 * root.uiScale
            spacing: 8 * root.uiScale
            Text {
                width: parent.width
                text: root.flowStage === 0 ? "LUTRIS" : root.title
                color: root.luluPalette.headingAccent
                font.family: root.typography.majorHeadingFamily
                font.weight: root.typography.majorHeadingWeight
                font.pixelSize: root.typography.size("section", 30)
                elide: Text.ElideRight
            }
            Rectangle {
                id: searchRow
                objectName: "lutrisSearchRow"
                visible: root.flowStage === 0
                width: parent.width
                height: 58 * root.uiScale
                radius: root.luluPalette.radius("row", 8 * root.uiScale, root.uiScale)
                color: root.selectedIndex === 0 ? root.luluPalette.focusedCardSurface : root.luluPalette.cardSurface
                border.color: root.selectedIndex === 0 ? root.luluPalette.focusIndicator : root.luluPalette.glassBorder
                border.width: root.uiScale
                MudosMaterialLayer { anchors.fill: parent; luluPalette: root.luluPalette; role: "row"; cornerRadius: parent.radius; uiScale: root.uiScale }
                MudosChromeFrame { anchors.fill: parent; luluPalette: root.luluPalette; uiScale: root.uiScale; cornerRadius: parent.radius; raised: root.selectedIndex !== 0 }
                Text {
                    anchors.fill: parent
                    anchors.leftMargin: 16 * root.uiScale
                    anchors.rightMargin: 16 * root.uiScale
                    text: root.title.length ? root.title : "Search game title…"
                    color: root.title.length ? root.luluPalette.primaryText : root.luluPalette.secondaryText
                    font.family: root.typography.interfaceFamily
                    font.pixelSize: root.typography.size("body", 17)
                    verticalAlignment: Text.AlignVCenter
                    elide: Text.ElideRight
                }
            }
            Text {
                visible: root.message.length > 0
                width: parent.width
                height: implicitHeight
                text: root.message
                color: root.luluPalette.secondaryText
                font.family: root.typography.interfaceFamily
                font.pixelSize: root.typography.size("body", 15)
                wrapMode: Text.Wrap
                elide: Text.ElideMiddle
            }
            ListView {
                 id: recipeRows
                 objectName: "lutrisResultRows"
                 width: parent.width - 8 * root.uiScale
                 anchors.horizontalCenter: parent.horizontalCenter
                 height: Math.max(0, parent.height - (root.flowStage === 2 ? 230 : 190) * root.uiScale)
                 clip: true
                 interactive: false
                 model: root.rows
                 spacing: 8 * root.uiScale
                 delegate: Rectangle {
                     required property var modelData
                     required property int index
                     width: recipeRows.width
                     height: 64 * root.uiScale
                     radius: root.luluPalette.radius("row", 8 * root.uiScale, root.uiScale)
                     color: index + (root.flowStage === 0 ? 1 : 0) === root.selectedIndex ? root.luluPalette.focusedCardSurface : root.luluPalette.cardSurface
                     border.color: index + (root.flowStage === 0 ? 1 : 0) === root.selectedIndex ? root.luluPalette.focusIndicator : root.luluPalette.glassBorder
                     border.width: root.uiScale
                     MudosMaterialLayer { anchors.fill: parent; luluPalette: root.luluPalette; role: "row"; cornerRadius: parent.radius; uiScale: root.uiScale }
                     MudosChromeFrame { anchors.fill: parent; luluPalette: root.luluPalette; uiScale: root.uiScale; cornerRadius: parent.radius; raised: index + (root.flowStage === 0 ? 1 : 0) !== root.selectedIndex }
                     Text {
                         anchors.fill: parent; anchors.leftMargin: 16 * root.uiScale; anchors.rightMargin: 12 * root.uiScale
                         verticalAlignment: Text.AlignVCenter
                         color: root.luluPalette.primaryText; font.family: root.typography.interfaceFamily; font.pixelSize: root.typography.size("body", 17); elide: Text.ElideMiddle
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
                 height: 58 * root.uiScale
                 radius: root.luluPalette.radius("row", 8 * root.uiScale, root.uiScale)
                visible: root.flowStage === 2
                 color: root.selectedIndex === root.requirements.length && root.luluPalette ? root.luluPalette.focusedCardSurface : root.luluPalette ? root.luluPalette.cardSurface : "#202b38"
                border.color: root.luluPalette ? root.luluPalette.glassBorder : "#9bb9d9"
                 border.width: root.uiScale
                 MudosMaterialLayer { anchors.fill: parent; luluPalette: root.luluPalette; role: "row"; cornerRadius: parent.radius; uiScale: root.uiScale }
                MudosChromeFrame { anchors.fill: parent; luluPalette: root.luluPalette; cornerRadius: parent.radius; raised: root.selectedIndex !== root.requirements.length }
                Text {
                    anchors.fill: parent
                     anchors.leftMargin: 16 * root.uiScale
                    verticalAlignment: Text.AlignVCenter
                     color: root.luluPalette ? root.luluPalette.primaryText : "white"
                    font.family: root.typography ? root.typography.interfaceFamily : "sans-serif"
                     font.pixelSize: root.typography.size("body", 17)
                    font.bold: true
                    text: "Install"
                }
            }
            Text {
                width: parent.width
                 text: root.flowStage === 2 ? "A: Select file / Start install   B: Back   ↑/↓: Choose" : "A: Select   B: Back   ↑/↓: Choose"
                 color: root.luluPalette.secondaryText; font.family: root.typography.interfaceFamily; font.pixelSize: root.typography.size("hint", 14)
            }
        }
    }
    MudosFilePicker {
        id: genericFilePicker
        apiUrl: root.apiUrl
        luluPalette: root.luluPalette
        typography: root.typography
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
