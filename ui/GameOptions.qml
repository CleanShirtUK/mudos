import QtQuick

Item {
    id: options

    property var game: null
    property string view: "menu"
    property int selectedIndex: 0
    property string selectedCandidateId: ""
    property string errorMessage: ""
    property var artworkCandidates: []
    property var mappingResults: []
    property string mappingQuery: ""
    property string artworkRole: "icon_square"
    property string titleDraft: ""
    property bool titleOverride: false
    property bool uninstallSupported: false
    property bool uninstallInProgress: false
    property bool mappingOverride: false
    property string uninstallDescription: "Remove installed content"
    property bool textEditing: false
    property real uiScale: 1
    property var typography
    property var luluPalette
    signal activated()
    signal backed()
    signal textEntryRequested()
    signal textEntryCancelled()
    signal textEntrySubmitted()
    signal mappingQueryEdited(string query)
    signal mappingSearchRequested(string query)
    signal mappingSelected(var candidate)
    signal artworkSelected(var candidate, string role)
    signal titleSaved(string title)
    signal titleReset()

    readonly property var menuEntries: {
        var entries = ["Change Mapping"]
        if (mappingOverride)
            entries.push("Revert Mapping")
        entries.push("Change Artwork", "Change Title")
        if (uninstallSupported)
            entries.push(uninstallInProgress ? "Uninstalling…" : "Uninstall")
        return entries
    }
    readonly property var artworkRoles: [
        {label: "Recents / Card Artwork", role: "cover"},
        {label: "Square Icon", role: "icon_square"},
        {label: "Preview Artwork", role: "preview_still"}
    ]
    readonly property var titleEntries: titleOverride
        ? ["Save Title", "Restore Canonical Title"] : ["Save Title", "Cancel"]
    readonly property int titleActionCount: titleEntries.length

    anchors.fill: parent
    visible: game !== null
    z: 80

    function cancelTextEntry() {
        textEditing = false
        if (view === "title")
            titleDraft = String(game && game.display_title_override
                                || game && game.canonical_title || game && game.title || "")
        mappingInput.focus = false
        titleInput.focus = false
    }

    function keyboardDismissed() {
        textEditing = false
        if (view === "title") {
            titleInput.forceActiveFocus()
        } else if (view === "mapping") {
            mappingInput.forceActiveFocus()
        }
    }

    function beginTextEntry(field) {
        textEditing = true
        if (field === "mapping")
            mappingInput.forceActiveFocus()
        else
            titleInput.forceActiveFocus()
        textEntryRequested()
    }

    function candidateSubtitle(candidate) {
        if (!candidate)
            return ""
        if (candidate.subtitle)
            return String(candidate.subtitle)
        var parts = []
        if (candidate.year !== undefined && candidate.year !== null && String(candidate.year) !== "")
            parts.push(String(candidate.year))
        var platforms = candidate.platforms
        if (platforms && typeof platforms.join === "function" && platforms.length)
            parts.push(platforms.join(", "))
        else if (typeof platforms === "string" && platforms.length)
            parts.push(platforms)
        return parts.join(" · ")
    }

    function ensureCandidateVisible() {
        if (view === "mapping") {
            var mappingIndex = selectedIndex - 2
            if (mappingIndex >= 0 && mappingIndex < mappingResults.length)
                mappingList.positionViewAtIndex(mappingIndex, ListView.Contain)
        } else if (view === "artwork" && selectedIndex >= 0
                   && selectedIndex < artworkCandidates.length) {
            artworkList.positionViewAtIndex(selectedIndex, ListView.Contain)
        }
    }

    function updateSelectedCandidateIdentity() {
        var candidate = null
        if (view === "mapping" && selectedIndex >= 2)
            candidate = mappingResults[selectedIndex - 2]
        else if (view === "artwork" && selectedIndex >= 0)
            candidate = artworkCandidates[selectedIndex]
        selectedCandidateId = candidate && candidate.id !== undefined
            ? String(candidate.id) : ""
    }

    function preserveCandidateIdentity() {
        if (!selectedCandidateId)
            return
        var candidates = view === "mapping" ? mappingResults
            : view === "artwork" ? artworkCandidates : []
        var offset = view === "mapping" ? 2 : 0
        for (var index = 0; index < candidates.length; index++) {
            if (String(candidates[index].id || "") === selectedCandidateId) {
                selectedIndex = index + offset
                return
            }
        }
        updateSelectedCandidateIdentity()
    }

    function selectedCandidate() {
        var candidates = view === "mapping" ? mappingResults
            : view === "artwork" ? artworkCandidates : []
        for (var index = 0; index < candidates.length; index++) {
            if (String(candidates[index].id || "") === selectedCandidateId)
                return candidates[index]
        }
        return null
    }

    onSelectedIndexChanged: Qt.callLater(function() {
        updateSelectedCandidateIdentity()
        ensureCandidateVisible()
    })
    onMappingResultsChanged: Qt.callLater(function() {
        preserveCandidateIdentity()
        updateSelectedCandidateIdentity()
        ensureCandidateVisible()
    })
    onArtworkCandidatesChanged: Qt.callLater(function() {
        preserveCandidateIdentity()
        updateSelectedCandidateIdentity()
        ensureCandidateVisible()
    })
    onViewChanged: Qt.callLater(updateSelectedCandidateIdentity)

    Rectangle {
        anchors.fill: parent
        color: options.luluPalette.overlayBackdrop
    }

    Rectangle {
        id: panel
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.bottom: parent.bottom
        width: Math.min(parent.width * 0.50, 600 * options.uiScale)
        color: options.luluPalette.overlaySurface
        radius: options.luluPalette.radius("overlay", 10 * options.uiScale)
        border.color: options.luluPalette.glassBorder
        border.width: options.uiScale
        clip: true
        MudosChromeFrame { anchors.fill: parent; luluPalette: options.luluPalette; uiScale: options.uiScale; cornerRadius: panel.radius }

        Column {
            anchors.fill: parent
            anchors.margins: 24 * options.uiScale
            spacing: 15 * options.uiScale

            Text {
                text: "GAME OPTIONS"
                color: options.luluPalette.headingAccent
                font.family: options.typography.majorHeadingFamily
                font.weight: options.typography.majorHeadingWeight
                font.pixelSize: options.typography.size("section", 28)
                font.letterSpacing: 4 * options.uiScale
            }
            Text {
                text: options.game ? String(options.game.display_title_override
                    || options.game.canonical_title || options.game.title || "") : ""
                color: options.luluPalette.primaryText
                font.family: options.typography.displayFamily
                font.weight: options.typography.displayWeight
                font.pixelSize: options.typography.size("display", 30)
                width: parent.width
                elide: Text.ElideRight
            }
            Text {
                visible: options.view !== "menu"
                text: options.view === "mapping" ? "Search IGDB and choose the correct game"
                    : options.view === "artworkRole" ? "Choose what to change"
                    : options.view === "artwork" ? (options.artworkRole === "cover"
                        ? "Recents / Card Artwork candidates"
                        : options.artworkRole === "icon_square" ? "Square Icon candidates"
                        : "Preview Artwork candidates")
                    : options.view === "title" ? "Change the displayed title"
                    : options.view === "confirm" ? "Uninstall this game? " + options.uninstallDescription + "."
                    : ""
                color: options.luluPalette.secondaryText
                font.family: options.typography.interfaceFamily
                font.pixelSize: options.typography.size("body", 15)
                wrapMode: Text.WordWrap
                width: parent.width
            }
            Text {
                visible: options.errorMessage !== ""
                text: options.errorMessage
                color: options.luluPalette.warning
                font.family: options.typography.interfaceFamily
                font.pixelSize: options.typography.size("body", 15)
                wrapMode: Text.WordWrap
                width: parent.width
            }

            ListView {
                id: menuList
                visible: options.view === "menu"
                width: parent.width
                height: Math.min(contentHeight, 420 * options.uiScale)
                spacing: 8 * options.uiScale
                model: options.menuEntries
                delegate: menuRow
            }

            Column {
                visible: options.view === "mapping"
                width: parent.width
                spacing: 8 * options.uiScale
                Rectangle {
                    width: parent.width
                    height: 58 * options.uiScale
                    radius: options.luluPalette.radius("row", 8 * options.uiScale)
                    color: options.selectedIndex === 0
                        ? options.luluPalette.focusedCardSurface : options.luluPalette.cardSurface
                    border.color: options.selectedIndex === 0
                        ? options.luluPalette.focusIndicator : options.luluPalette.glassBorder
                    TextInput {
                        id: mappingInput
                        anchors.fill: parent
                        anchors.margins: 12 * options.uiScale
                        text: options.mappingQuery
                        color: options.luluPalette.primaryText
                        font.family: options.typography.interfaceFamily
                        font.pixelSize: options.typography.size("body", 17)
                        verticalAlignment: TextInput.AlignVCenter
                        selectByMouse: false
                        onTextChanged: options.mappingQueryEdited(text)
                        onAccepted: {
                            options.textEditing = false
                            options.textEntrySubmitted()
                            options.mappingSearchRequested(text)
                        }
                        Keys.onPressed: function(event) {
                            if (event.key === Qt.Key_Escape) {
                                event.accepted = true
                                options.textEditing = false
                                options.textEntryCancelled()
                            }
                        }
                    }
                }
                Rectangle {
                    width: parent.width
                    height: 52 * options.uiScale
                    radius: options.luluPalette.radius("row", 8 * options.uiScale)
                    color: options.selectedIndex === 1
                        ? options.luluPalette.focusedCardSurface : options.luluPalette.cardSurface
                    border.color: options.selectedIndex === 1
                        ? options.luluPalette.focusIndicator : options.luluPalette.glassBorder
                    Text {
                        anchors.fill: parent
                        anchors.leftMargin: 16 * options.uiScale
                        text: "Search IGDB"
                        color: options.luluPalette.primaryText
                        font.family: options.typography.interfaceFamily
                        font.pixelSize: options.typography.size("body", 17)
                        verticalAlignment: Text.AlignVCenter
                    }
                }
                ListView {
                    id: mappingList
                    objectName: "mappingCandidateList"
                    width: parent.width
                    height: Math.min(contentHeight, 300 * options.uiScale)
                    spacing: 6 * options.uiScale
                    model: options.mappingResults
                    delegate: resultRow
                    clip: true
                }
                Text {
                    visible: options.mappingResults.length === 0
                    text: options.mappingQuery.length > 0 ? "Press A to search. Results will appear here." : "Enter a title to search."
                    color: options.luluPalette.secondaryText
                    font.family: options.typography.interfaceFamily
                    font.pixelSize: options.typography.size("body", 14)
                }
            }

            ListView {
                id: roleList
                visible: options.view === "artworkRole"
                width: parent.width
                height: contentHeight
                spacing: 8 * options.uiScale
                model: options.artworkRoles
                delegate: roleRow
            }

            ListView {
                id: artworkList
                objectName: "artworkCandidateList"
                visible: options.view === "artwork"
                width: parent.width
                height: Math.min(contentHeight, 420 * options.uiScale)
                spacing: 8 * options.uiScale
                model: options.artworkCandidates
                delegate: artworkRow
                clip: true
            }

            Column {
                visible: options.view === "title"
                width: parent.width
                spacing: 8 * options.uiScale
                Rectangle {
                    width: parent.width
                    height: 58 * options.uiScale
                    radius: options.luluPalette.radius("row", 8 * options.uiScale)
                    color: options.selectedIndex === 0
                        ? options.luluPalette.focusedCardSurface : options.luluPalette.cardSurface
                    border.color: options.selectedIndex === 0
                        ? options.luluPalette.focusIndicator : options.luluPalette.glassBorder
                    TextInput {
                        id: titleInput
                        objectName: "gameOptionsTitleInput"
                        anchors.fill: parent
                        anchors.margins: 12 * options.uiScale
                        text: options.titleDraft
                        color: options.luluPalette.primaryText
                        font.family: options.typography.interfaceFamily
                        font.pixelSize: options.typography.size("body", 17)
                        verticalAlignment: TextInput.AlignVCenter
                        selectByMouse: false
                        onTextChanged: options.titleDraft = text
                        onAccepted: {
                            options.textEditing = false
                            options.textEntrySubmitted()
                        }
                        Keys.onPressed: function(event) {
                            if (event.key === Qt.Key_Escape) {
                                event.accepted = true
                                options.textEditing = false
                                options.textEntryCancelled()
                            }
                        }
                    }
                }
                ListView {
                    id: titleActions
                    width: parent.width
                    height: contentHeight
                    spacing: 8 * options.uiScale
                    model: options.titleEntries
                    delegate: menuRow
                }
            }

            ListView {
                id: confirmList
                visible: options.view === "confirm"
                width: parent.width
                height: contentHeight
                spacing: 8 * options.uiScale
                model: ["Uninstall", "Cancel"]
                delegate: menuRow
            }

            Item { width: 1; height: 1 }
            Text {
                text: options.view === "mapping" ? "A: Search / Select   B: Back"
                    : options.view === "title" ? "A: Edit / Apply   B: Cancel"
                    : options.view === "confirm" ? "A: Confirm   B: Cancel"
                    : "A: Select   B: Back"
                color: options.luluPalette.secondaryText
                font.family: options.typography.interfaceFamily
                font.pixelSize: options.typography.size("hint", 14)
            }
        }
    }

    Component {
        id: menuRow
        Rectangle {
            required property int index
            required property var modelData
            width: ListView.view.width
            height: 58 * options.uiScale
            radius: options.luluPalette.radius("row", 8 * options.uiScale)
            color: index === options.selectedIndex
                ? options.luluPalette.focusedCardSurface : options.luluPalette.cardSurface
            border.color: index === options.selectedIndex
                ? options.luluPalette.focusIndicator : options.luluPalette.glassBorder
            MudosChromeFrame { anchors.fill: parent; luluPalette: options.luluPalette; uiScale: options.uiScale; cornerRadius: parent.radius; raised: index !== options.selectedIndex }
            Text {
                anchors.fill: parent
                anchors.leftMargin: 16 * options.uiScale
                text: typeof modelData === "string" ? modelData : String(modelData.label || "")
                color: options.luluPalette.primaryText
                font.family: options.typography.interfaceFamily
                font.pixelSize: options.typography.size("body", 18)
                verticalAlignment: Text.AlignVCenter
            }
        }
    }
    Component {
        id: roleRow
        Rectangle {
            required property int index
            required property var modelData
            width: roleList.width
            height: 58 * options.uiScale
            radius: options.luluPalette.radius("row", 8 * options.uiScale)
            color: index === options.selectedIndex
                ? options.luluPalette.focusedCardSurface : options.luluPalette.cardSurface
            border.color: index === options.selectedIndex
                ? options.luluPalette.focusIndicator : options.luluPalette.glassBorder
            MudosChromeFrame { anchors.fill: parent; luluPalette: options.luluPalette; uiScale: options.uiScale; cornerRadius: parent.radius; raised: index !== options.selectedIndex }
            Text {
                anchors.fill: parent
                anchors.leftMargin: 16 * options.uiScale
                text: modelData.label
                color: options.luluPalette.primaryText
                font.family: options.typography.interfaceFamily
                font.pixelSize: options.typography.size("body", 18)
                verticalAlignment: Text.AlignVCenter
            }
        }
    }
    Component {
        id: artworkRow
        Rectangle {
            id: candidateDelegate
            required property int index
            required property var modelData
            width: artworkList.width
            height: 74 * options.uiScale
            radius: options.luluPalette.radius("row", 8 * options.uiScale)
            color: index === options.selectedIndex
                ? options.luluPalette.focusedCardSurface : options.luluPalette.cardSurface
            border.color: index === options.selectedIndex
                ? options.luluPalette.focusIndicator : options.luluPalette.glassBorder
            MudosChromeFrame { anchors.fill: parent; luluPalette: options.luluPalette; uiScale: options.uiScale; cornerRadius: parent.radius; raised: index !== options.selectedIndex }
            Rectangle {
                anchors.left: parent.left
                anchors.leftMargin: 8 * options.uiScale
                anchors.verticalCenter: parent.verticalCenter
                width: 74 * options.uiScale
                height: 58 * options.uiScale
                radius: options.luluPalette.radius("media", 4 * options.uiScale)
                color: options.luluPalette.cardSurface
                clip: true
                Image {
                    anchors.fill: parent
                    visible: status === Image.Ready
                    source: candidateDelegate.modelData
                        ? String(candidateDelegate.modelData.thumbnail || "") : ""
                    fillMode: Image.PreserveAspectFit
                    asynchronous: true
                    cache: true
                }
            }
                Text {
                    objectName: "artworkCandidateText"
                    anchors.left: parent.left
                anchors.leftMargin: 92 * options.uiScale
                anchors.right: parent.right
                anchors.rightMargin: 8 * options.uiScale
                anchors.verticalCenter: parent.verticalCenter
                text: (candidateDelegate.modelData
                       && candidateDelegate.modelData.current ? "CURRENT · " : "")
                    + String(candidateDelegate.modelData
                             ? candidateDelegate.modelData.title || candidateDelegate.modelData.source || "Artwork"
                             : "Artwork")
                    + (candidateDelegate.modelData && candidateDelegate.modelData.subtitle
                       ? "  " + String(candidateDelegate.modelData.subtitle) : "")
                color: options.luluPalette.primaryText
                font.family: options.typography.interfaceFamily
                font.pixelSize: options.typography.size("body", 14)
                elide: Text.ElideRight
            }
        }
    }
    Component {
        id: resultRow
        Rectangle {
            id: candidateDelegate
            required property int index
            required property var modelData
            width: mappingList.width
            height: 72 * options.uiScale
            radius: options.luluPalette.radius("row", 8 * options.uiScale)
            color: index + 2 === options.selectedIndex
                ? options.luluPalette.focusedCardSurface : options.luluPalette.cardSurface
            border.color: index + 2 === options.selectedIndex
                ? options.luluPalette.focusIndicator : options.luluPalette.glassBorder
            MudosChromeFrame { anchors.fill: parent; luluPalette: options.luluPalette; uiScale: options.uiScale; cornerRadius: parent.radius; raised: index + 2 !== options.selectedIndex }
            Rectangle {
                anchors.left: parent.left
                anchors.leftMargin: 8 * options.uiScale
                anchors.verticalCenter: parent.verticalCenter
                width: 56 * options.uiScale
                height: 56 * options.uiScale
                radius: options.luluPalette.radius("media", 4 * options.uiScale)
                color: options.luluPalette.cardSurface
                clip: true
                Image {
                    anchors.fill: parent
                    visible: status === Image.Ready
                    source: candidateDelegate.modelData
                        ? String(candidateDelegate.modelData.thumbnail || "") : ""
                    fillMode: Image.PreserveAspectFit
                    asynchronous: true
                }
            }
            Column {
                anchors.left: parent.left
                anchors.leftMargin: 74 * options.uiScale
                anchors.right: parent.right
                anchors.verticalCenter: parent.verticalCenter
                Text {
                    objectName: "mappingCandidateTitle"
                    width: parent.width
                    text: candidateDelegate.modelData
                        ? String(candidateDelegate.modelData.title || candidateDelegate.modelData.canonical_title || "Untitled game")
                        : "Untitled game"
                    color: options.luluPalette.primaryText
                    font.family: options.typography.interfaceFamily
                    font.pixelSize: options.typography.size("body", 16)
                    elide: Text.ElideRight
                }
                Text {
                    objectName: "mappingCandidateSubtitle"
                    width: parent.width
                    text: options.candidateSubtitle(candidateDelegate.modelData)
                    color: options.luluPalette.secondaryText
                    font.family: options.typography.interfaceFamily
                    font.pixelSize: options.typography.size("hint", 12)
                    elide: Text.ElideRight
                }
            }
        }
    }

    Timer {
        interval: 250
        repeat: true
        running: options.textEditing && options.visible
        onTriggered: {
            if (options.view === "mapping")
                mappingInput.forceActiveFocus()
            else if (options.view === "title")
                titleInput.forceActiveFocus()
        }
    }
}
