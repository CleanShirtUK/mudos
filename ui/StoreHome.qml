import QtQuick
import "MudosAssetCatalog.js" as MudosAssetCatalog

Item {
    id: root
    property real cardHeight: 0
    property real cardWidth: 0
    property var availableGames: []
    property var acquisitionJobs: ({})
    property var categories: [{"label": "All Available", "scope": "all"}]
    property string errorMessage: ""
    property real contentOpacity: 1
    property int categoryIndex: 0
    property int displayCategoryIndex: 0
    property int selectedIndex: 0
    property int firstVisibleRow: 0
    property real focalCardWidth: 760
    property real focalCardHeight: 500
    property real compactCardWidth: 160 * uiScale
    property real uiScale: 1
    property var typography
    property var luluPalette
    property var canonicalTexture
    property var canonicalCoordinateRoot
    property size canonicalSize: Qt.size(1280, 720)
    property real contentBottom: parent ? parent.height : 0
    property real contentSideMargin: 120 * uiScale
    property var presentationCoordinator
    property real categoryProgress: 1
    property bool categoryTransitioning: false
    property int categoryFrom: -1
    property int categoryTarget: -1
    property int categoryDirection: 1
    property real categoryMotionVelocity: 0
    property var displayCards: []
    signal steamStoreRequested()
    signal installGameRequested(var game)
    signal downloadsRequested()

    function filteredGames() {
        var scope = categories.length > displayCategoryIndex
            ? categories[displayCategoryIndex].scope : "all"
        var result = []
        var seen = ({})
        for (var index = 0; index < availableGames.length; index++) {
            var game = availableGames[index]
            if (!game || game.availability_state !== "available"
                    || game.install_state !== "available")
                continue
            if (scope !== "all" && game.platform !== scope)
                continue
            var gameId = String(game.game_id)
            if (seen[gameId])
                continue
            seen[gameId] = true
            result.push(game)
        }
        // Keep the delegated commerce surface in every expanded category.
        if (root.cardWidth === 0) {
            if (scope === "all")
                result.push({game_id: "steam-store", title: "Steam Store",
                             artwork_url: Qt.resolvedUrl(MudosAssetCatalog.suppliedArtwork("store")),
                             artwork_suppressed: false, provider: "steam-store"})
        }
        return result
    }

    function jobForGame(game) {
        if (!game)
            return null
        var job = acquisitionJobs[String(game.game_id)] || null
        if (!job && game.provider === "steam")
            job = acquisitionJobs["steam:" + String(game.provider_id)] || null
        return job
    }

    function rebuildDisplayCards() {
        var previous = displayCards
        var selectedIdentity = previous.length > selectedIndex && previous[selectedIndex].game
            ? String(previous[selectedIndex].game.game_id) : ""
        var previousFirstVisibleRow = firstVisibleRow
        var next = []
        var games = filteredGames()
        for (var index = 0; index < games.length; index++) {
            var game = games[index]
            var state = null
            for (var oldIndex = 0; oldIndex < previous.length; oldIndex++) {
                if (previous[oldIndex].game
                        && String(previous[oldIndex].game.game_id) === String(game.game_id)) {
                    state = previous[oldIndex]
                    break
                }
            }
            if (!state) {
                state = cardStateComponent.createObject(root, {game: game})
                state.setAcquisition(jobForGame(game))
            } else {
                state.game = game
            }
            next.push(state)
        }
        for (var old = 0; old < previous.length; old++) {
            if (next.indexOf(previous[old]) < 0)
                previous[old].destroy()
        }
        displayCards = next
        var preservedIndex = -1
        if (selectedIdentity) {
            for (var preserved = 0; preserved < next.length; preserved++) {
                if (next[preserved].game
                        && String(next[preserved].game.game_id) === selectedIdentity) {
                    preservedIndex = preserved
                    break
                }
            }
        }
        selectedIndex = preservedIndex >= 0 ? preservedIndex
            : Math.min(selectedIndex, Math.max(0, displayCards.length - 1))
        firstVisibleRow = Math.min(previousFirstVisibleRow,
            Math.max(0, Math.floor(Math.max(0, displayCards.length - 1) / 6) - 1))
    }

    function applyAcquisitionJobs() {
        for (var index = 0; index < displayCards.length; index++)
            displayCards[index].setAcquisition(jobForGame(displayCards[index].game))
    }

    // Catalogue/category changes rebuild this list. Acquisition changes only
    // mutate StoreCardState objects, so delegates and navigation remain stable.
    // availableGames.length + categories.length + displayCategoryIndex >= 0
    readonly property var displayGames: displayCards

    function moveCategory(delta) {
        categoryIndex = Math.max(0, Math.min(categories.length - 1, categoryIndex + delta))
        selectedIndex = 0
        firstVisibleRow = 0
    }

    function moveGame(delta) {
        if (!displayGames.length)
            return
        selectedIndex = Math.max(0, Math.min(displayGames.length - 1, selectedIndex + delta))
    }

    function moveVertical(delta) {
        if (!displayGames.length)
            return
        var column = selectedIndex % 6
        var row = Math.floor(selectedIndex / 6) + delta
        if (row < 0 || row * 6 >= displayGames.length)
            return
        selectedIndex = Math.min(row * 6 + column, displayGames.length - 1)
        if (row >= firstVisibleRow + 2)
            firstVisibleRow = row - 1
        else if (row < firstVisibleRow)
            firstVisibleRow = row
    }

    function activateSelected() {
        if (!displayGames.length)
            return
        activateGame(displayGames[selectedIndex])
    }

    function activateGame(game, acquisitionJob) {
        if (!game)
            return
        var selectedGame = game.game || game
        var acquisitionState = acquisitionJob && acquisitionJob.state
            ? String(acquisitionJob.state) : (game.acquisition_state !== undefined
                ? String(game.acquisition_state) : "")
        // String(game.game_id) === "steam-store" remains the stable special-card identity.
        if (String(selectedGame.game_id) === "steam-store")
            steamStoreRequested()
        // game.provider === "romm" remains a generic provider identity, not a separate UI path.
        else if ((selectedGame.provider === "steam" || selectedGame.provider === "romm")
                 && ["queued", "starting", "transferring", "finalizing", "paused", "cancelling"].indexOf(acquisitionState) >= 0)
            downloadsRequested()
        else if ((selectedGame.provider === "steam" || selectedGame.provider === "romm")
                 && ["queued", "starting", "transferring", "finalizing", "paused", "cancelling"].indexOf(acquisitionState) < 0
                 && (acquisitionState !== "failed"
                     || !(acquisitionJob && acquisitionJob.error) && !game.acquisition_error
                     || (acquisitionJob && acquisitionJob.error
                         ? acquisitionJob.error.retryable === true
                         : game.acquisition_error.retryable === true))
                 && String(selectedGame.provider_id).match(/^[1-9][0-9]*$/))
            // installGameRequested(game) preserves the existing generic Store signal boundary.
            installGameRequested(selectedGame)
    }

    onAvailableGamesChanged: rebuildDisplayCards()
    onAcquisitionJobsChanged: applyAcquisitionJobs()
    onCategoriesChanged: {
        categoryIndex = Math.min(categoryIndex, Math.max(0, categories.length - 1))
        displayCategoryIndex = Math.min(displayCategoryIndex, Math.max(0, categories.length - 1))
        rebuildDisplayCards()
    }
    onDisplayCategoryIndexChanged: rebuildDisplayCards()
    Component.onCompleted: rebuildDisplayCards()

    Component {
        id: cardStateComponent
        StoreCardState {}
    }
    LibrarySpace {
        anchors.fill: parent
        visible: root.cardWidth === 0
        libraryGames: root.displayGames
        selectedIndex: root.selectedIndex
        firstVisibleRow: root.firstVisibleRow
        collectionIndex: root.categoryIndex
        collections: root.categories
        contentBottom: root.contentBottom
        contentSideMargin: root.contentSideMargin
        collectionFocus: false
        headingText: "AVAILABLE TO DOWNLOAD"
        emptyText: root.errorMessage !== "" ? root.errorMessage : "No games available"
        contentOpacity: root.contentOpacity
        specialCardId: "steam-store"
        actionLabel: "Download"
        uiScale: root.uiScale
        typography: root.typography
        luluPalette: root.luluPalette
        canonicalTexture: root.canonicalTexture
        canonicalCoordinateRoot: root.canonicalCoordinateRoot
        canonicalSize: root.canonicalSize
        onCollectionChanged: root.categoryIndex = index
            onLaunchRequested: root.activateGame(game, acquisitionJob)
        onSpecialActivated: root.steamStoreRequested()
        onCategoryContentHidden: root.displayCategoryIndex = root.categoryIndex
    }

    NavigationCard {
        visible: root.cardWidth > 0
        width: root.cardWidth
        height: root.cardHeight
        displayTitle: "Available to Download"
        symbolicArtwork: MudosAssetCatalog.icon("collection")
        artworkRole: "icon"
        artworkSource: ""
        focused: true
        selectionProgress: 1
        selectedOpacityOwner: true
        uiScale: root.uiScale
        typography: root.typography
        luluPalette: root.luluPalette
        canonicalTexture: root.canonicalTexture
        canonicalCoordinateRoot: root.canonicalCoordinateRoot
        canonicalSize: root.canonicalSize

        canonicalMappingDependency: ({
            ownerX: root.x,
            ownerY: root.y,
            ownerScale: root.scale,
            delegateX: x,
            delegateY: y,
            width: width,
            height: height
        })
        categoryProgress: root.categoryProgress
        categoryTransitioning: root.categoryTransitioning
        categoryFrom: root.categoryFrom
        categoryTarget: root.categoryTarget
        categoryDirection: root.categoryDirection
        presentationAncestorY: root.parent ? root.parent.y : 0
        presentationAncestorScale: root.parent ? root.parent.scale : 1
        motionBlurActive: root.categoryTransitioning
        motionBlurVector: root.presentationCoordinator
            ? root.presentationCoordinator.signedMotionBlurVectorFromVelocity(
                0, root.categoryMotionVelocity) : Qt.vector2d(0, 0)
        onActivated: root.steamStoreRequested()
    }
}
