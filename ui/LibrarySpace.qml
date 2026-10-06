import QtQuick
import "LibraryProjection.js" as LibraryProjection
import "GameArtwork.js" as GameArtwork
import "GameMetadata.js" as GameMetadata
import "DescriptionFit.js" as DescriptionFit
import "MudosAssetCatalog.js" as MudosAssetCatalog

Item {
    id: root
    y: !transitionExpanding ? (1 - transitionProgress) * height : 0
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
    property real transitionProgress: 1
    property bool transitionExpanding: true
    property real contentOpacity: 1
    property real gameContentOpacity: 1
    property bool gameContentVisible: true
    property real uiScale: 1
    property var typography
    property var luluPalette
    property var canonicalTexture
    property var canonicalCoordinateRoot
    property size canonicalSize: Qt.size(1280, 720)
    // Shell-space outer substrate bounds. This item normally spans the screen,
    // so the frame remains expressed in root coordinates for both Library and
    // StoreHome's Installable projection.
    property rect surfaceBounds: Qt.rect(0, 0, width, height)
    property rect contentBounds: surfaceBounds
    property real innerInset: 20 * uiScale
    property real contentBottom: parent ? parent.height : 0
    property real contentSideMargin: 72 * uiScale
    property string headingText: "LIBRARY"
    property string sectionTitle: ""
    property string emptyText: "No installed games"
    property real titleX: 0
    property real titleY: 0
    property string actionLabel: "Play"
    readonly property string navigationObject: "library"
    readonly property real rowHeight: 54 * uiScale
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
    property string previewSource: ""
    property int previewGeneration: 0
    property string previewAnimationSource: ""
    property string previewAnimationGameId: ""
    property string failedAnimationPath: ""
    property string failedAnimationGameId: ""
    property bool previewAnimationReady: false
    // Video previews use the Qt image plugin only. Retain the explicit false
    // switch as a guard against reintroducing in-process Qt Multimedia playback.
    readonly property bool videoPreviewsEnabled: false
    property real internalSurfaceOpacity: 0.34
    readonly property string libraryFontFamily: typography ? typography.displayFamily : "sans-serif"
    readonly property rect contentFrameRect: Qt.rect(
        contentBounds.x + innerInset, contentBounds.y + innerInset,
        Math.max(0, contentBounds.width - 2 * innerInset),
        Math.max(0, contentBounds.height - 2 * innerInset))
    readonly property real panelGap: 22 * uiScale
    readonly property real categoryRailHeight: 28 * uiScale
    readonly property real categoryRailGap: 14 * uiScale
    readonly property real panelTop: categoryRailHeight + categoryRailGap
    readonly property real panelBottomMargin: 0
    readonly property real detailInset: 18 * uiScale
    readonly property real detailGutter: 16 * uiScale
    readonly property real detailRightColumnRatio: 0.46
    readonly property real detailArtworkHeightRatio: 0.46
    readonly property real metadataRowSpacing: 8 * uiScale
    readonly property var detailMetadataRows: GameMetadata.rows(selectedGame, function(timestamp) {
        return Qt.formatDateTime(new Date(timestamp * 1000), "d MMM yyyy")
    })
    property string displayedDescription: ""
    property bool descriptionNeedsElide: false
    readonly property real listWidth: Math.max(250 * uiScale,
        (contentFrameRect.width - panelGap) * 0.40)
    readonly property real internalFrameRight: contentFrameRect.x + contentFrameRect.width
    readonly property real internalFrameBottom: contentFrameRect.y + contentFrameRect.height
    signal launchRequested(var game, var acquisitionJob)
    signal specialActivated(var game)
    signal browseCategoryRequested(int index)
    signal browseGameRequested(int index)

    function acquisitionJobFor(game) {
        if (!game) return null
        return acquisitionJobs[String(game.game_id)] || null
    }

    function recomputeDescription() {
        var source = selectedGame ? String(selectedGame.summary || "No description available.") : emptyText
        var result = DescriptionFit.select(source, function(candidate) {
            descriptionMeasure.text = candidate
            return descriptionMeasure.contentHeight <= descriptionRegion.height
        })
        displayedDescription = result.text
        descriptionNeedsElide = result.elide
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
        ++previewGeneration
        previewAnimationSource = ""
        previewAnimationGameId = ""
        previewAnimationReady = false
        previewSource = selectedGame && (selectedGame.preview_video_url || selectedGame.preview_video)
                ? (selectedGame.preview_video_url || selectedGame.preview_video) : ""
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

    onCanonicalGamesChanged: {
        if (projectionInitialized)
            commitProjection(dimensionKey, "", "")
        Qt.callLater(recomputeDescription)
    }
    onDimensionKeyChanged: if (projectionInitialized) commitProjection(dimensionKey, "", "")
    onBrowseCategoriesChanged: if (projectionInitialized && browsingExternalCategories) commitProjection(dimensionKey, "", "")
    onBrowseCategoryIndexChanged: if (projectionInitialized && browsingExternalCategories) commitProjection(dimensionKey, "", "")
    onVisibleChanged: {
        if (visible) {
            Qt.callLater(preparePreview)
        } else {
            previewAnimationSource = ""
            previewAnimationGameId = ""
            previewAnimationReady = false
        }
    }
    onSelectedIndexChanged: if (!committingProjection) {
        if (!browsingExternalCategories)
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
            if (!root.visible || !root.selectedGame)
                return
            var gameId = String(root.selectedGame.game_id || "")
            if (gameId === "")
                return
            var localAnimation = String(root.selectedGame.preview_animation_url || "")
            if (root.failedAnimationGameId === gameId
                    && root.failedAnimationPath === localAnimation)
                return
            root.previewAnimationSource = localAnimation.indexOf("file:") === 0
                ? localAnimation : ""
            root.previewAnimationGameId = root.previewAnimationSource ? gameId : ""
        }
    }

    Text {
        id: libraryTitle
        objectName: "libraryTitle"
        x: root.titleX
        y: root.titleY
        width: Math.max(0, root.width - x)
        height: 42 * root.uiScale
        opacity: root.contentOpacity
        text: root.browsingExternalCategories ? root.headingText
            : root.headingText + ": " + String(root.categoryMode).replace(/_/g, " ").toUpperCase()
        color: root.luluPalette.headingAccent
        font.family: root.libraryFontFamily
        font.pixelSize: root.typography ? root.typography.size("section", 27) : 27 * root.uiScale
        font.bold: true
        font.letterSpacing: 2 * root.uiScale
        elide: Text.ElideRight
        verticalAlignment: Text.AlignVCenter
    }

    Item {
        id: contentFrame
        objectName: "libraryInternalFrame"
        x: root.contentFrameRect.x
        y: root.contentFrameRect.y
        width: root.contentFrameRect.width
        height: root.contentFrameRect.height
        clip: true
        opacity: root.contentOpacity

        ListView {
            id: categoryTape
            objectName: "libraryCategoryTape"
            x: 0; y: 0
            width: parent.width
            height: root.categoryRailHeight
            orientation: ListView.Horizontal
            spacing: 26 * root.uiScale
            clip: true; interactive: false
            model: root.categoryTapeValues
            currentIndex: root.categoryTapeIndex
            delegate: Item {
                required property string modelData
                required property int index
                width: categoryText.implicitWidth + 8 * root.uiScale
                height: categoryTape.height
                Text {
                    id: categoryText
                    anchors.horizontalCenter: parent.horizontalCenter
                    anchors.top: parent.top
                    text: modelData
                    color: index === root.categoryTapeIndex
                        ? root.luluPalette.selectedText : root.luluPalette.secondaryText
                    font.family: root.libraryFontFamily
                    font.pixelSize: root.typography ? root.typography.size("body", 16) : 16 * root.uiScale
                    font.bold: index === root.categoryTapeIndex
                }
                Rectangle {
                    visible: index === root.categoryTapeIndex
                    anchors.horizontalCenter: parent.horizontalCenter
                    anchors.bottom: parent.bottom
                    width: categoryText.implicitWidth
                    height: 2 * root.uiScale
                    color: root.luluPalette.focusIndicator
                }
                MouseArea {
                    anchors.fill: parent
                    onClicked: root.moveCategory(index - root.categoryTapeIndex)
                }
            }
            onCurrentIndexChanged: if (currentIndex >= 0)
                positionViewAtIndex(currentIndex, ListView.Contain)
            onModelChanged: if (root.categoryTapeIndex >= 0)
                positionViewAtIndex(root.categoryTapeIndex, ListView.Contain)
            Component.onCompleted: if (root.categoryTapeIndex >= 0)
                positionViewAtIndex(root.categoryTapeIndex, ListView.Contain)
        }

        Rectangle {
            id: listSurface
            x: 0; y: root.panelTop
            width: Math.min(root.listWidth, parent.width * 0.42)
            height: Math.max(0, parent.height - y - root.panelBottomMargin)
            radius: root.luluPalette.radius("panel", 10 * root.uiScale)
            color: Qt.rgba(root.luluPalette.librarySurface.r,
                           root.luluPalette.librarySurface.g,
                           root.luluPalette.librarySurface.b,
                           root.internalSurfaceOpacity)
            border.color: root.luluPalette.libraryBorder
            border.width: root.uiScale
            ListView {
                id: gameRows
                objectName: "libraryGameRows"
                x: 10 * root.uiScale
                y: 10 * root.uiScale
                width: Math.max(0, parent.width - 20 * root.uiScale)
                height: Math.min(8, Math.max(0, Math.floor(
                    (parent.height - 20 * root.uiScale) / root.rowHeight))) * root.rowHeight
                clip: true
                interactive: false
                model: root.filteredGames
                delegate: Item {
                    id: gameRow
                    required property var modelData
                    required property int index
                    property bool iconFailed: false
                    width: gameRows.width
                    height: root.rowHeight
                    Rectangle {
                        anchors.fill: parent
                        anchors.leftMargin: 2 * root.uiScale
                        anchors.rightMargin: 2 * root.uiScale
                        radius: root.luluPalette.radius("row", 6 * root.uiScale)
                        color: root.selectedIndex === gameRow.index
                            ? Qt.rgba(root.luluPalette.focusIndicator.r,
                                      root.luluPalette.focusIndicator.g,
                                      root.luluPalette.focusIndicator.b, 0.18)
                            : "transparent"
                    }
                    Rectangle {
                        x: 10 * root.uiScale
                        width: 34 * root.uiScale; height: width
                        anchors.verticalCenter: parent.verticalCenter
                        radius: root.luluPalette.radius("media", 4 * root.uiScale)
                        color: Qt.rgba(root.luluPalette.primaryText.r,
                                       root.luluPalette.primaryText.g,
                                       root.luluPalette.primaryText.b, 0.08)
                        clip: true
                        Image {
                            id: gameIcon
                            anchors.fill: parent
                            source: GameArtwork.portraitIcon(gameRow.modelData)
                            sourceSize: Qt.size(96, 96)
                            fillMode: Image.PreserveAspectFit
                            asynchronous: true
                            onStatusChanged: if (status === Image.Error) gameRow.iconFailed = true
                            onSourceChanged: gameRow.iconFailed = false
                        }
                        MudosIcon {
                            anchors.centerIn: parent
                            visible: !gameIcon.source || gameRow.iconFailed
                            name: "fallback"
                            iconSize: 21 * root.uiScale
                            typography: root.typography
                            semanticColor: root.luluPalette.secondaryText
                        }
                    }
                    Text {
                        anchors.left: parent.left
                        anchors.leftMargin: 54 * root.uiScale
                        anchors.right: parent.right
                        anchors.rightMargin: 12 * root.uiScale
                        anchors.verticalCenter: parent.verticalCenter
                        text: String(gameRow.modelData.display_title_override
                            || gameRow.modelData.canonical_title || gameRow.modelData.title || "")
                        color: root.selectedIndex === gameRow.index
                            ? root.luluPalette.selectedText : root.luluPalette.primaryText
                        font.family: root.libraryFontFamily
                        font.pixelSize: root.typography ? root.typography.size("body", 16) : 16 * root.uiScale
                        font.bold: root.selectedIndex === gameRow.index
                        elide: Text.ElideRight
                    }
                    MouseArea {
                        anchors.fill: parent
                        onClicked: {
                            if (root.browsingExternalCategories)
                                root.browseGameRequested(gameRow.index)
                            else root.selectedIndex = gameRow.index
                        }
                    }
                }
                onCurrentIndexChanged: if (currentIndex >= 0)
                    positionViewAtIndex(currentIndex, ListView.Contain)
                onCountChanged: if (count > 0) positionViewAtIndex(root.selectedIndex, ListView.Contain)
            }
            Text {
                anchors.centerIn: parent
                visible: root.filteredGames.length === 0
                text: root.emptyText
                color: root.luluPalette.mutedText
                font.family: root.libraryFontFamily
                font.pixelSize: root.typography ? root.typography.size("body", 16) : 16 * root.uiScale
                wrapMode: Text.WordWrap
                horizontalAlignment: Text.AlignHCenter
                width: parent.width - 32 * root.uiScale
            }
        }

        Rectangle {
            id: detailSurface
            x: listSurface.width + root.panelGap
            y: root.panelTop
            width: Math.max(0, parent.width - x)
            height: Math.max(0, parent.height - y - root.panelBottomMargin)
            radius: root.luluPalette.radius("panel", 10 * root.uiScale)
            color: Qt.rgba(root.luluPalette.librarySurface.r,
                           root.luluPalette.librarySurface.g,
                           root.luluPalette.librarySurface.b,
                           root.internalSurfaceOpacity)
            border.color: root.luluPalette.libraryBorder
            border.width: root.uiScale
            clip: true

            readonly property real inset: root.detailInset
            readonly property real gutter: root.detailGutter
            readonly property real innerWidth: Math.max(0, width - 2 * inset)
            readonly property real innerHeight: Math.max(0, height - 2 * inset)
            readonly property real leftWidth: (innerWidth - gutter) * (1 - root.detailRightColumnRatio)
            readonly property real rightWidth: (innerWidth - gutter) * root.detailRightColumnRatio
            readonly property real rightArtworkHeight: Math.max(0,
                (innerHeight - gutter) * root.detailArtworkHeightRatio)
            readonly property real rightMetadataY: inset + rightArtworkHeight + gutter
            readonly property real rightMetadataHeight: Math.max(0,
                height - rightMetadataY - inset)

            Item {
                id: detailTitleRegion
                x: detailSurface.inset
                y: detailSurface.inset
                width: detailSurface.leftWidth
                height: titleText.implicitHeight
                clip: true
                Text {
                    id: titleText
                    x: 0
                    y: 0
                    width: parent.width
                    height: implicitHeight
                    text: root.selectedGame
                        ? String(root.selectedGame.display_title_override
                            || root.selectedGame.canonical_title || root.selectedGame.title || "") : ""
                    color: root.luluPalette.primaryText
                    font.family: root.libraryFontFamily
                    font.pixelSize: root.typography ? root.typography.size("display", 32) : 32 * root.uiScale
                    font.bold: true
                    wrapMode: Text.WordWrap
                    maximumLineCount: 4
                    elide: Text.ElideRight
                    horizontalAlignment: Text.AlignLeft
                    verticalAlignment: Text.AlignTop
                }
            }

            Item {
                id: descriptionRegion
                x: detailSurface.inset
                y: detailTitleRegion.y + detailTitleRegion.height + detailSurface.gutter
                width: detailSurface.leftWidth
                height: Math.max(0, detailSurface.height - y - detailSurface.inset)
                clip: true
                Text {
                    id: descriptionText
                    anchors.fill: parent
                    text: root.displayedDescription
                    color: root.luluPalette.secondaryText
                    font.family: root.libraryFontFamily
                    font.pixelSize: root.typography ? root.typography.size("body", 14) : 14 * root.uiScale
                    fontSizeMode: Text.Fit
                    minimumPixelSize: 10 * root.uiScale
                    wrapMode: Text.WordWrap
                    maximumLineCount: Math.max(1, Math.floor(descriptionRegion.height / (10 * root.uiScale * 1.2)))
                    elide: root.descriptionNeedsElide ? Text.ElideRight : Text.ElideNone
                    horizontalAlignment: Text.AlignLeft
                    verticalAlignment: Text.AlignTop
                }
                Text {
                    id: descriptionMeasure
                    x: -100000
                    y: 0
                    width: descriptionRegion.width
                    height: 100000
                    visible: false
                    text: ""
                    font.family: root.libraryFontFamily
                    font.pixelSize: 10 * root.uiScale
                    wrapMode: Text.WordWrap
                    elide: Text.ElideNone
                }
                Component.onCompleted: Qt.callLater(root.recomputeDescription)
                onWidthChanged: Qt.callLater(root.recomputeDescription)
                onHeightChanged: Qt.callLater(root.recomputeDescription)
            }

            Item {
                id: landscapeArea
                x: detailSurface.inset + detailSurface.leftWidth + detailSurface.gutter
                y: detailSurface.inset
                width: detailSurface.rightWidth
                height: detailSurface.rightArtworkHeight
                clip: true
                Item {
                    id: landscapeMediaRect
                    anchors.centerIn: parent
                    width: Math.min(parent.width, parent.height * 16 / 9)
                    height: Math.min(parent.height, parent.width * 9 / 16)
                    clip: true
                    Rectangle {
                        anchors.fill: parent
                        color: "black"
                        MudosIcon {
                            anchors.centerIn: parent
                            visible: !root.previewAnimationReady
                                && root.previewAnimationSource === ""
                                && (!landscapeImage.source || landscapeImage.status === Image.Error)
                            name: "fallback"
                            iconSize: 52 * root.uiScale
                            typography: root.typography
                            semanticColor: root.luluPalette.secondaryText
                        }
                    }
                    Image {
                        id: landscapeImage
                        anchors.fill: parent
                        source: GameArtwork.previewStill(root.selectedGame)
                        sourceSize: Qt.size(1600, 720)
                        fillMode: Image.PreserveAspectFit
                        asynchronous: true
                        cache: false
                        opacity: root.previewAnimationReady ? 0 : 1
                        Behavior on opacity { NumberAnimation { duration: 260 } }
                    }
                    Loader {
                        id: animationLoader
                        anchors.fill: parent
                        active: root.previewAnimationSource !== "" && root.selectedGame !== null
                            && root.previewAnimationGameId === String(root.selectedGame.game_id)
                        visible: root.previewAnimationReady
                        sourceComponent: animationComponent
                    }
                }
            }

            Item {
                id: detailMetadata
                y: detailSurface.rightMetadataY
                x: landscapeArea.x
                width: detailSurface.rightWidth
                height: detailSurface.rightMetadataHeight
                clip: true
                Column {
                    id: detailMetadataColumn
                    anchors.left: parent.left
                    anchors.top: parent.top
                    width: parent.width
                    height: implicitHeight
                    spacing: root.metadataRowSpacing
                    Repeater {
                        model: root.detailMetadataRows
                        delegate: FocalMetadataRow {
                            required property var modelData
                            width: detailMetadataColumn.width
                            height: implicitHeight
                            iconName: modelData.iconName
                            text: modelData.text
                            fontFamily: root.libraryFontFamily
                            iconFamily: root.typography ? root.typography.iconFamily : root.libraryFontFamily
                            textColor: root.luluPalette.secondaryText
                            uiScale: root.uiScale
                            glyphSize: Math.min(16 * root.uiScale, height * 0.7)
                            textSize: root.typography ? root.typography.size("hint", 12) : 12 * root.uiScale
                            glyphColumnWidth: 20 * root.uiScale
                            wrapText: true
                            trailingGlyph: true
                            maximumLineCount: 0
                        }
                    }
                }
            }
        }
    }

    onSelectedGameChanged: Qt.callLater(recomputeDescription)

    Component {
        id: animationComponent
        AnimatedImage {
            anchors.fill: parent
            source: root.previewAnimationSource
            fillMode: Image.PreserveAspectFit
            asynchronous: true
            cache: false
            playing: true
            onStatusChanged: {
                if (status === Image.Ready && root.selectedGame
                        && root.previewAnimationGameId === String(root.selectedGame.game_id)) {
                    root.previewAnimationReady = true
                } else if (status === Image.Error) {
                    root.previewAnimationReady = false
                    if (root.selectedGame
                            && root.previewAnimationGameId === String(root.selectedGame.game_id)) {
                        root.failedAnimationGameId = String(root.selectedGame.game_id)
                        root.failedAnimationPath = root.previewAnimationSource
                        root.previewAnimationSource = ""
                        root.previewAnimationGameId = ""
                    }
                }
            }
        }
    }

}
