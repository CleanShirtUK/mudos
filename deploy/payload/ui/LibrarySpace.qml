import QtQuick
import QtMultimedia
import "LibraryProjection.js" as LibraryProjection

Item {
    // Legacy geometry names remain documented for catalogue-browser consumers:
    // readonly property int gridColumns: 6; gridLeftInset; gridTop - gridTopInset;
    // gridRegionHeight + gridTopInset; (usableGridWidth - (gridColumns - 1) * gridGap) / gridColumns;
    // fullscreenPanelBevelWidth: 6 * uiScale; gridHorizontalGrowth; gridVerticalGrowth;
    // (fullscreenPanelCardSelectionScale - 1.0) * libraryCardHeight;
    // fullscreenPanelBorderWidth: 0; fullscreenPanelTransmission: 1;
    // scale: focused ? librarySpace.fullscreenPanelCardSelectionScale : 1;
    // z: focused ? 2 : 1; unfocusedBrightness: 0.8; librarySpace.unfocusedBrightness;
    // headerToGridGap: currentHeaderToGridGap / 2; catalogueCard: true;
    // required property string modelData; categoryRowWidth; categoryGlyphAdvance;
    // categoryFadeWidth; categoryViewport; categoryRail; selectedCategoryDelegate;
    // readonly property real headerToGridGap: currentHeaderToGridGap / 2;
    // gridTop: contentBottom - gridContentFootprintHeight;
    // horizontalCardWidth; libraryCardHeight: libraryCardWidth * 1.55;
    // expandedCardScale: 0.92; * expandedCardScale;
    // headingBottom: pageHeading.y + pageHeading.height;
    // firstRowTop: gridTop - selectedGrowth;
    // categoryRailHeight: categoryGlyphMetrics.height + 8 * uiScale;
    // requiredTwoRowHeight; id: gridViewport; GridView {
    // cacheBuffer: 2 * gridRowStep; contentY: librarySpace.firstVisibleRow * librarySpace.gridRowStep;
    // highlightRangeMode: GridView.NoHighlightRange; highlightFollowsCurrentItem: false;
    // parent.height - 16 * uiScale - gridBottomInset; gridRegionHeight: requiredTwoRowHeight;
    // property real gridContentFootprintHeight; property real gridTop;
    // libraryCardHeight + gridGap + libraryCardHeight + selectedGrowth;
    // parent.width - 2 * contentSideMargin; gridVisualWidth: gridSlotWidth + 2 * gridHorizontalGrowth;
    // contentOriginX: (parent.width - gridVisualWidth) / 2;
    // gridSlotLeft: contentOriginX + gridHorizontalGrowth; y: 81 * uiScale;
    // id: categoryViewport; x: contentOriginX;
    // categoryFadeWidth: categoryGlyphAdvance * 10;
    // categoryGlyphAdvance: categoryGlyphMetrics.advanceWidth;
    // readonly property real glyphCenterX;
    // categoryViewport.x + categoryRail.x + parent.x;
    // opacity: categoryStateOpacity * edgeFadeOpacity;
    // model: categoryLabel.length; TextMetrics {
    // y: 32 * uiScale; height: parent.height - 48 * uiScale;
    // opacity: librarySpace.contentOpacity * librarySpace.gameContentOpacity;
    // duration: librarySpace.gameContentOpacity === 0 ? 100 : 200;
    // Library catalogue rail geometry: id: categoryViewport; id: categoryRail;
    // selectedCategoryDelegate; x: selectedCategoryDelegate ? -selectedCategoryDelegate.x : 0;
    // width: categoryRowWidth; spacing: librarySpace.categoryGap;
    // Behavior on x; Easing.OutQuint; horizontalAlignment: Text.AlignHCenter;
    id: root
    property var canonicalGames: []
    property var acquisitionJobs: ({})
    property string dimensionKey: "platform"
    property string dimensionLabel: "Platform"
    property var rememberedSelections: ({})
    property var browseCategories: []
    property int browseCategoryIndex: 0
    property var projectionState: ({
        dimensionKey: "platform", categories: [], categoryKey: "",
        categoryIndex: 0, games: []
    })
    property bool committingProjection: false
    property bool projectionInitialized: false
    property int selectedIndex: 0
    property string transitionState: "RESTING"
    property string returnState: "RESTING"
    property real contentOpacity: 1
    property real gameContentOpacity: 1
    property bool gameContentVisible: true
    property real uiScale: 1
    property var typography
    property var luluPalette
    property var canonicalTexture
    property var canonicalCoordinateRoot
    property size canonicalSize: Qt.size(1280, 720)
    property real contentBottom: parent ? parent.height : 0
    property real contentSideMargin: 72 * uiScale
    property string headingText: "LIBRARY"
    property string sectionTitle: ""
    property string emptyText: "No installed games"
    property string actionLabel: "Play"
    readonly property string navigationObject: "library"
    readonly property real rowHeight: 54 * uiScale
    readonly property real leftWidth: Math.max(320 * uiScale, parent.width * 0.34)
    readonly property string categoryMode: projectionState.dimensionKey
    readonly property bool browsingExternalCategories: browseCategories.length > 0
    readonly property var categoryTapeValues: browsingExternalCategories
        ? browseCategories.map(function(item) {
            return item && item.label !== undefined ? String(item.label) : String(item)
        }) : projectionState.categories.map(function(item) { return item.label })
    readonly property int categoryTapeIndex: browsingExternalCategories
        ? browseCategoryIndex : projectionState.categoryIndex
    readonly property var categoryValues: categoryTapeValues
    readonly property int categoryIndex: categoryTapeIndex
    readonly property var filteredGames: projectionState.games
    property var browserRows: []
    readonly property var selectedCategoryLabel: categoryTapeValues.length > categoryTapeIndex
        ? String(categoryTapeValues[categoryTapeIndex]) : ""
    readonly property var selectedGame: selectedIndex >= 0 && selectedIndex < filteredGames.length
        ? filteredGames[selectedIndex] : null
    property bool previewReady: false
    property string previewSource: ""
    signal launchRequested(var game, var acquisitionJob)
    signal specialActivated(var game)
    signal browseCategoryRequested(int index)

    function acquisitionJobFor(game) {
        if (!game) return null
        return acquisitionJobs[String(game.game_id)] || null
    }

    function labelForDimension(mode) {
        if (mode === "provider") return "Provider"
        if (mode === "game_mode") return "Game Mode"
        if (mode === "genre") return "Genre"
        return "Platform"
    }

    function rememberSelection(mode, categoryKey, gameId) {
        if (!mode || !categoryKey) return
        var saved = Object.assign({}, rememberedSelections)
        var dimensionState = Object.assign({}, saved[mode] || {})
        var games = Object.assign({}, dimensionState.games || {})
        games[categoryKey] = String(gameId || "")
        dimensionState.games = games
        dimensionState.categoryKey = categoryKey
        saved[mode] = dimensionState
        rememberedSelections = saved
    }

    function commitProjection(mode, requestedCategoryKey, requestedGameId) {
        committingProjection = true
        var previous = projectionState
        var previousGame = selectedGame
        if (!browsingExternalCategories && previous.categories.length && previous.categoryKey)
            rememberSelection(previous.dimensionKey, previous.categoryKey,
                previousGame ? String(previousGame.game_id) : "")

        if (browsingExternalCategories) {
            var externalCategories = browseCategories.map(function(item, index) {
                var label = item && item.label !== undefined ? String(item.label) : String(item)
                var key = item && item.scope !== undefined ? String(item.scope) : label.toLowerCase()
                return {key: key + "#" + index, label: label, games: canonicalGames}
            })
            var externalIndex = Math.max(0, Math.min(externalCategories.length - 1, browseCategoryIndex))
            projectionState = {dimensionKey: mode, categories: externalCategories,
                categoryKey: externalCategories.length ? externalCategories[externalIndex].key : "",
                categoryIndex: externalIndex, games: canonicalGames.slice(0)}
            browserRows = projectionState.games.map(function(game) { return {header: false, game: game} })
            committingProjection = false
            preparePreview()
            rowSync.restart()
            return
        }

        var saved = rememberedSelections[mode] || ({})
        var previousKey = previous.dimensionKey === mode ? previous.categoryKey : ""
        var previousId = previous.dimensionKey === mode && previousGame
            ? String(previousGame.game_id) : ""
        var wantedKey = requestedCategoryKey || previousKey || String(saved.categoryKey || "")
        var wantedGameId = requestedGameId || previousId
        var built = LibraryProjection.build(canonicalGames, mode, wantedKey,
            wantedGameId, String(saved.categoryKey || ""), saved.games || ({}))
        var nextCategories = built.categories
        var nextGames = built.games
        selectedIndex = built.selectedIndex
        var nextState = {dimensionKey: mode, categories: nextCategories,
            categoryKey: built.categoryKey,
            categoryIndex: built.categoryIndex, games: nextGames}
        projectionState = nextState
        browserRows = nextState.games.map(function(game) { return {header: false, game: game} })
        rememberSelection(mode, nextState.categoryKey,
            nextGames.length > selectedIndex ? String(nextGames[selectedIndex].game_id) : "")
        committingProjection = false
        preparePreview()
        rowSync.restart()
    }

    function moveCategory(delta) {
        if (browsingExternalCategories) {
            var externalIndex = Math.max(0, Math.min(
                browseCategories.length - 1, browseCategoryIndex + delta))
            if (externalIndex !== browseCategoryIndex)
                browseCategoryRequested(externalIndex)
            return
        }
        var next = Math.max(0, Math.min(projectionState.categories.length - 1,
            projectionState.categoryIndex + delta))
        if (next === projectionState.categoryIndex) return
        commitProjection(projectionState.dimensionKey, projectionState.categories[next].key, "")
    }

    function moveGame(delta) {
        if (!filteredGames.length) return
        selectedIndex = Math.max(0, Math.min(filteredGames.length - 1, selectedIndex + delta))
    }

    function preparePreview() {
        if (previewLoader.item) {
            previewLoader.item.player.stop()
            previewLoader.item.player.source = ""
        }
        previewReady = false
        previewSource = selectedGame && selectedGame.preview_video ? selectedGame.preview_video : ""
        previewSettle.restart()
    }

    function selectedRowIndex() {
        if (!selectedGame) return -1
        for (var i = 0; i < browserRows.length; ++i)
            if (!browserRows[i].header && browserRows[i].game
                    && String(browserRows[i].game.game_id) === String(selectedGame.game_id))
                return i
        return -1
    }

    onCanonicalGamesChanged: if (projectionInitialized) commitProjection(dimensionKey, "", "")
    onDimensionKeyChanged: if (projectionInitialized) commitProjection(dimensionKey, "", "")
    onBrowseCategoriesChanged: if (projectionInitialized && browsingExternalCategories) commitProjection(dimensionKey, "", "")
    onBrowseCategoryIndexChanged: if (projectionInitialized && browsingExternalCategories) commitProjection(dimensionKey, "", "")
    onSelectedIndexChanged: if (!committingProjection && !browsingExternalCategories) {
        rememberSelection(categoryMode, projectionState.categoryKey,
            selectedGame ? String(selectedGame.game_id) : "")
        preparePreview()
        rowSync.restart()
    }
    Component.onCompleted: {
        projectionInitialized = true
        commitProjection(dimensionKey, "", "")
    }

    Timer {
        id: rowSync
        interval: 0
        repeat: false
        onTriggered: {
            var row = root.selectedRowIndex()
            if (row >= 0) {
                gameRows.currentIndex = row
                gameRows.positionViewAtIndex(row, ListView.Contain)
            }
        }
    }

    Timer {
        id: previewSettle
        interval: 220
        repeat: false
        onTriggered: {
            if (root.previewSource !== "" && previewLoader.item) {
                previewLoader.item.player.source = root.previewSource
                previewLoader.item.player.play()
            }
        }
    }

    Loader {
        id: previewLoader
        anchors.left: parent.left
        anchors.top: parent.top
        anchors.bottom: parent.bottom
        width: parent.width * 0.43
        active: root.previewSource !== ""
        sourceComponent: previewComponent
        visible: root.previewReady
    }
    Component {
        id: previewComponent
        Item {
            anchors.fill: parent
            property alias player: previewPlayer
            MediaPlayer {
                id: previewPlayer
                videoOutput: previewOutput
                audioOutput: AudioOutput { muted: true }
                loops: MediaPlayer.Infinite
                onHasVideoChanged: if (hasVideo) root.previewReady = true
                onErrorOccurred: root.previewReady = false
            }
            VideoOutput {
                id: previewOutput
                anchors.fill: parent
                fillMode: VideoOutput.PreserveAspectCrop
            }
        }
    }

    Rectangle {
        anchors.fill: parent
        color: "transparent"
        opacity: root.contentOpacity
    }
    Text {
        x: root.contentSideMargin; y: 60 * root.uiScale
        text: root.headingText
        color: luluPalette.headingAccent
        font.family: typography ? typography.majorHeadingFamily : "JetBrains Mono"
        font.pixelSize: typography ? typography.size("section", 30) : 30 * root.uiScale
        font.bold: true
        font.letterSpacing: 5 * root.uiScale
    }
    Text {
        x: root.contentSideMargin; y: 112 * root.uiScale
        text: "CATEGORIZE BY  " + root.labelForDimension(root.categoryMode).toUpperCase()
        color: luluPalette.secondaryText
        font.family: typography ? typography.interfaceFamily : "JetBrains Mono"
        font.pixelSize: typography ? typography.size("hint", 13) : 13 * root.uiScale
    }

    ListView {
        id: categoryTape
        x: root.contentSideMargin
        y: 136 * root.uiScale
        width: parent.width - 2 * root.contentSideMargin
        height: 34 * root.uiScale
        orientation: ListView.Horizontal
        spacing: 28 * root.uiScale
        clip: true
        interactive: false
        model: root.categoryTapeValues
        currentIndex: root.categoryTapeIndex
        delegate: Text {
            required property string modelData
            required property int index
            text: modelData
            color: index === root.categoryTapeIndex ? luluPalette.selectedText : luluPalette.secondaryText
            font.family: typography ? typography.interfaceFamily : "JetBrains Mono"
            font.pixelSize: typography ? typography.size("body", 16) : 16 * root.uiScale
            font.bold: index === root.categoryTapeIndex
            MouseArea {
                anchors.fill: parent
                onClicked: root.moveCategory(index - root.categoryTapeIndex)
            }
        }
        onCurrentIndexChanged: if (currentIndex >= 0) positionViewAtIndex(currentIndex, ListView.Contain)
        onModelChanged: positionViewAtIndex(root.categoryTapeIndex, ListView.Contain)
    }

    Rectangle {
        x: root.contentSideMargin; y: 184 * root.uiScale
        width: root.leftWidth; height: parent.height - y - 34 * root.uiScale
        color: luluPalette.librarySurface
        radius: 14 * root.uiScale
        border.color: luluPalette.glassBorder
        ListView {
            id: gameRows
            anchors.fill: parent; anchors.margins: 10 * root.uiScale
            clip: true; interactive: false
            model: root.browserRows
            delegate: Item {
                required property var modelData
                required property int index
                readonly property var gameData: modelData.game
                width: gameRows.width; height: modelData.header ? 34 * root.uiScale : root.rowHeight
                Text {
                    anchors.left: parent.left; anchors.leftMargin: 12 * root.uiScale
                    anchors.verticalCenter: parent.verticalCenter
                    text: modelData.header ? String(modelData.label).toUpperCase() : String(modelData.game.title || "")
                    color: modelData.header ? luluPalette.headingAccent
                        : (root.selectedGame && modelData.game.game_id === root.selectedGame.game_id ? luluPalette.selectedText : luluPalette.primaryText)
                    font.family: typography ? typography.interfaceFamily : "JetBrains Mono"
                    font.pixelSize: modelData.header ? typography.size("hint", 12) : typography.size("body", 16)
                    font.bold: modelData.header || (root.selectedGame && modelData.game.game_id === root.selectedGame.game_id)
                    elide: Text.ElideRight; width: parent.width - 40 * root.uiScale
                }
                Text {
                    visible: !modelData.header && modelData.game.platform_label !== ""
                    anchors.right: parent.right; anchors.rightMargin: 12 * root.uiScale
                    anchors.verticalCenter: parent.verticalCenter
                    text: "◆"; color: luluPalette.secondaryText
                }
                Rectangle {
                    visible: !modelData.header && root.selectedGame && modelData.game.game_id === root.selectedGame.game_id
                    anchors.fill: parent; anchors.margins: 1 * root.uiScale
                    color: "transparent"; border.color: luluPalette.focusIndicator
                    radius: 8 * root.uiScale; z: -1
                }
                MouseArea {
                    anchors.fill: parent; enabled: !modelData.header
                    onClicked: {
                        var id = String(gameData.game_id)
                        for (var n = 0; n < root.filteredGames.length; ++n)
                            if (String(root.filteredGames[n].game_id) === id) root.selectedIndex = n
                    }
                }
            }
            onCurrentIndexChanged: if (currentIndex >= 0) positionViewAtIndex(currentIndex, ListView.Contain)
        }
    }

    Rectangle {
        x: root.contentSideMargin + root.leftWidth + 28 * root.uiScale
        y: 184 * root.uiScale
        width: parent.width - x - root.contentSideMargin
        height: parent.height - y - 34 * root.uiScale
        color: luluPalette.librarySurface; radius: 14 * root.uiScale
        border.color: luluPalette.glassBorder
        opacity: root.gameContentOpacity
        Image {
            id: artwork
            anchors.left: parent.left; anchors.top: parent.top; anchors.bottom: parent.bottom
            width: parent.width * 0.43; fillMode: Image.PreserveAspectCrop
            source: root.selectedGame ? (root.selectedGame.artwork_url || root.selectedGame.canonical_cover_url) : ""
            opacity: root.previewReady ? 0 : 1
            Behavior on opacity { NumberAnimation { duration: 260 } }
        }
        Column {
            x: parent.width * 0.47; y: 34 * root.uiScale
            width: parent.width * 0.48; spacing: 14 * root.uiScale
            Text { text: root.selectedGame ? root.selectedGame.title : ""; color: luluPalette.primaryText; font.bold: true; font.pixelSize: typography.size("heading", 25); wrapMode: Text.WordWrap; width: parent.width }
            Text { text: root.selectedGame ? (root.selectedGame.summary || "No description available.") : root.emptyText; color: luluPalette.secondaryText; font.pixelSize: typography.size("body", 15); wrapMode: Text.WordWrap; width: parent.width; maximumLineCount: 5; elide: Text.ElideRight }
            Text { text: root.selectedGame ? [root.selectedGame.platform_label || root.selectedGame.platform, root.selectedGame.provider, root.selectedGame.game_mode || ""].filter(function(x) { return x }).join("  •  ") : ""; color: luluPalette.headingAccent; font.pixelSize: typography.size("hint", 13); wrapMode: Text.WordWrap; width: parent.width }
            Text { text: root.selectedGame && root.selectedGame.protondb_rating ? "ProtonDB  " + root.selectedGame.protondb_rating : ""; color: luluPalette.secondaryText; font.pixelSize: typography.size("hint", 13) }
            ControllerHint { visible: !!root.selectedGame; action: "confirm"; label: root.actionLabel; uiScale: root.uiScale; typography: root.typography; luluPalette: root.luluPalette }
        }
    }
}
