import QtQuick
import "MudosAssetCatalog.js" as MudosAssetCatalog
import "InstallableProjection.js" as InstallableProjection
Item {
    id: root
    ThemeMotion { id: themeMotion }
    property real cardHeight: 0
    property real cardWidth: 0
    property var availableGames: []
    property var acquisitionJobs: ({})
    property var categories: InstallableProjection.categories([])
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
    property rect surfaceBounds: Qt.rect(0, 0, width, height)
    property rect contentBounds: surfaceBounds
    property real innerInset: 20 * uiScale
    property real titleX: 0
    property real titleY: 0
    property var presentationCoordinator
    property real categoryProgress: 1
    property bool categoryTransitioning: false
    property int categoryFrom: -1
    property int categoryTarget: -1
    property int categoryDirection: 1
    property real categoryMotionVelocity: 0
    // Keep the filtered catalogue as plain stable records. Expensive card
    // state belongs to the virtualized LibrarySpace delegates, not to every
    // item in the provider catalogue.
    property var displayCards: []
    property var stores: []
    property var pluginStores: []
    property int homeSelectedIndex: 0
    property var homeSelectionStart: []
    property var homePresentationStartX: []
    property real homeSelectionProgress: 1
    property bool suppressHomeSelectionCompletion: false
    readonly property bool homeSelectionMotionActive: homeSelectionAnimation.running
    signal steamStoreRequested()
    signal storeRequested(string url)
    signal addStoreRequested()
    signal removeStoreRequested(string id)
    signal homeDownloadRequested()
    signal homeStoreRequested(string id, string displayName, string url)
    signal homeAddStoreRequested()
    signal homeStoreOptionsRequested(var store)
    signal installGameRequested(var game)
    signal downloadsRequested()

    function filteredGames() {
        var category = categories.length > displayCategoryIndex
            ? categories[displayCategoryIndex] : null
        var result = []
        var seen = ({})
        for (var index = 0; index < availableGames.length; index++) {
            var game = availableGames[index]
            if (!InstallableProjection.matches(game, category))
                continue
            var gameId = String(game.game_id)
            if (seen[gameId])
                continue
            seen[gameId] = true
            result.push(game)
        }
        return result
    }

    function jobForGame(game) {
        if (!game)
            return null
        var job = acquisitionJobs[String(game.game_id)]
            || acquisitionJobs[String(game.content_identity || game.game_id)] || null
        if (!job && (game.provider === "steam" || game.provider === "steam-aurelia"))
            job = acquisitionJobs[(game.provider === "steam-aurelia" ? "steam-aurelia:" : "steam:")
                                  + String(game.provider_id)] || null
        return job
    }

    function rebuildDisplayCards() {
        var previous = displayCards
        var selectedIdentity = previous.length > selectedIndex && previous[selectedIndex]
            ? String(previous[selectedIndex].game_id) : ""
        var previousFirstVisibleRow = firstVisibleRow
        var started = Date.now()
        var next = []
        var games = filteredGames()
        for (var index = 0; index < games.length; index++)
            next.push(games[index])
        displayCards = next
        var preservedIndex = -1
        if (selectedIdentity) {
            for (var preserved = 0; preserved < next.length; preserved++) {
                if (String(next[preserved].game_id) === selectedIdentity) {
                    preservedIndex = preserved
                    break
                }
            }
        }
        selectedIndex = preservedIndex >= 0 ? preservedIndex
            : Math.min(selectedIndex, Math.max(0, displayCards.length - 1))
        firstVisibleRow = Math.min(previousFirstVisibleRow,
            Math.max(0, Math.floor(Math.max(0, displayCards.length - 1) / 6) - 1))
        if (typeof mudosPerfDiagnostics !== "undefined" && mudosPerfDiagnostics)
            console.log("STORE_FILTER", games.length, "ms", Date.now() - started,
                "cardStates", 0)
    }

    function applyAcquisitionJobs() {
        // Acquisition state is resolved by the visible LibrarySpace delegate.
    }

    // Catalogue/category changes rebuild this list. Acquisition state is
    // resolved only by visible delegates, so the catalogue stays lightweight.
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
        moveGame(delta)
    }

    function activateSelected() {
        console.log("INSTALLABLE_ACTIVATE_SELECTED", "index", selectedIndex,
                    "count", displayGames.length,
                    "game", displayGames.length > selectedIndex
                        ? JSON.stringify(displayGames[selectedIndex]) : "null")
        if (!displayGames.length)
            return
        activateGame(displayGames[selectedIndex])
    }

    function activateGame(game, acquisitionJob) {
        if (!game)
            return
        var selectedGame = game.game || game
        var provider = String(selectedGame.provider || "")
        var providerId = String(selectedGame.provider_id || "")
        var acquisitionState = acquisitionJob && acquisitionJob.state
            ? String(acquisitionJob.state) : (game.acquisition_state !== undefined
                ? String(game.acquisition_state) : "")
        console.log("INSTALLABLE_CARD_ACTIVATE", "game", String(selectedGame.game_id),
                    "provider", provider, "action", "install",
                    "actionEnabled", String(selectedGame.install_state === "available"
                        && selectedGame.availability_state === "available"),
                    "provider_id", providerId,
                    "acquisitionState", acquisitionState)
        // game.provider === "romm" remains part of the combined catalogue.
        if ((provider === "steam" || provider === "steam-aurelia" || provider === "romm" || provider === "lutris"
                  || provider === "gog" || provider === "epic")
                 && ["queued", "starting", "transferring", "finalizing", "paused", "cancelling"].indexOf(acquisitionState) >= 0)
            downloadsRequested()
        else if ((provider === "steam" || provider === "steam-aurelia" || provider === "romm" || provider === "lutris"
                  || provider === "gog" || provider === "epic")
                 && ["queued", "starting", "transferring", "finalizing", "paused", "cancelling"].indexOf(acquisitionState) < 0
                  && (provider === "lutris" ? providerId.length > 0
                      : provider === "epic" ? providerId.length > 0
                      : providerId.match(/^[1-9][0-9]*$/))) {
            // installGameRequested(game) preserves the existing generic Store signal boundary.
            console.log("INSTALLABLE_INSTALL_SIGNAL", "game", String(selectedGame.game_id),
                        "provider", provider, "provider_id", providerId)
            installGameRequested(selectedGame)
        } else {
            console.warn("INSTALLABLE_INSTALL_NOT_DISPATCHED", "game", String(selectedGame.game_id),
                         "provider", provider, "provider_id", providerId,
                         "acquisitionState", acquisitionState)
        }
    }

    onAvailableGamesChanged: rebuildDisplayCards()
    onStoresChanged: {
        rebuildDisplayCards()
        var cards = homeCards()
        homeSelectedIndex = Math.min(homeSelectedIndex, Math.max(0, cards.length - 1))
        captureHomeSelection()
    }
    onAcquisitionJobsChanged: applyAcquisitionJobs()
    onCategoryIndexChanged: {
        selectedIndex = 0
        firstVisibleRow = 0
        displayCategoryIndex = categoryIndex
    }
    onCategoriesChanged: {
        categoryIndex = Math.min(categoryIndex, Math.max(0, categories.length - 1))
        displayCategoryIndex = Math.min(displayCategoryIndex, Math.max(0, categories.length - 1))
        rebuildDisplayCards()
    }
    onDisplayCategoryIndexChanged: rebuildDisplayCards()
    Component.onCompleted: {
        rebuildDisplayCards()
        captureHomeSelection()
    }

    function homeCards() {
        var cards = [{id: "available", title: "Installable", kind: "catalogue"}]
        for (var pluginIndex = 0; pluginIndex < pluginStores.length; pluginIndex++) {
            var pluginStore = pluginStores[pluginIndex]
            cards.push({id: String(pluginStore.id), title: String(pluginStore.label), kind: "store",
                url: String(pluginStore.url), removable: false, glyph: pluginStore.glyph || ""})
        }
        for (var index = 0; index < stores.length; index++) {
            var store = stores[index]
            cards.push({id: String(store.id), title: String(store.display_name), kind: "store",
                url: String(store.url), removable: true})
        }
        cards.push({id: "add", title: "Add New Store", kind: "add"})
        return cards
    }
    function homeRailX(relativeIndex) {
        return relativeIndex * (cardWidth + 24 * uiScale)
    }
    function captureHomeSelection() {
        var starts = [], startsX = [], cards = homeCards()
        for (var index = 0; index < cards.length; index++) {
            var card = homeCardRepeater.itemAt(index)
            starts[index] = card ? card.selectionProgress : (index === homeSelectedIndex ? 1 : 0)
            startsX[index] = card ? card.x : homeRailX(index - homeSelectedIndex)
        }
        homeSelectionStart = starts
        homePresentationStartX = startsX
    }
    function moveHome(delta) {
        var cards = homeCards()
        var next = Math.max(0, Math.min(cards.length - 1, homeSelectedIndex + delta))
        if (next === homeSelectedIndex)
            return
        captureHomeSelection()
        homeSelectedIndex = next
        suppressHomeSelectionCompletion = true
        homeSelectionAnimation.stop()
        suppressHomeSelectionCompletion = false
        homeSelectionProgress = 0
        if (themeMotion.enabled("navigation")) homeSelectionAnimation.start()
        else { homeSelectionProgress = 1; captureHomeSelection() }
    }
    function finishHomeSelectionMotion() {
        suppressHomeSelectionCompletion = true
        homeSelectionAnimation.stop()
        suppressHomeSelectionCompletion = false
        homeSelectionProgress = 1
        captureHomeSelection()
    }
    Connections {
        target: typeof mudosTheme !== "undefined"
            && typeof mudosTheme.themeChanged !== "undefined" ? mudosTheme : null
        function onThemeChanged() {
            if (!themeMotion.enabled("navigation")) root.finishHomeSelectionMotion()
        }
    }
    function activateHome() {
        var card = homeCards()[homeSelectedIndex]
        if (!card) return
        if (card.kind === "catalogue") homeDownloadRequested()
        else if (card.kind === "add") homeAddStoreRequested()
        else homeStoreRequested(card.id, card.title, card.url)
    }

    function optionsSelected() {
        var card = homeCards()[homeSelectedIndex]
        if (card && card.kind === "store" && card.removable !== false)
            homeStoreOptionsRequested(card)
    }

    NumberAnimation {
        id: homeSelectionAnimation
        target: root
        property: "homeSelectionProgress"
        to: 1
        duration: themeMotion.duration("navigation", 500)
        easing.type: themeMotion.easing("navigation", "outQuint")
        onStopped: {
            if (root.suppressHomeSelectionCompletion)
                return
            root.homeSelectionProgress = 1
            root.captureHomeSelection()
        }
    }

    LibrarySpace {
        anchors.fill: parent
        visible: root.cardWidth === 0
        surfaceBounds: root.surfaceBounds
        contentBounds: root.contentBounds
        canonicalGames: root.displayGames
        acquisitionJobs: root.acquisitionJobs
        selectedIndex: root.selectedIndex
        browseCategories: root.categories
        browseCategoryIndex: root.categoryIndex
        contentBottom: root.contentBottom
        innerInset: root.innerInset
        titleX: root.titleX
        titleY: root.titleY
        contentSideMargin: root.contentSideMargin
        headingText: "INSTALLABLE"
        emptyText: root.errorMessage !== "" ? root.errorMessage : "No games ready to install"
        contentOpacity: root.contentOpacity
        actionLabel: "Install"
        uiScale: root.uiScale
        typography: root.typography
        luluPalette: root.luluPalette
        canonicalTexture: root.canonicalTexture
        canonicalCoordinateRoot: root.canonicalCoordinateRoot
        canonicalSize: root.canonicalSize
        onBrowseCategoryRequested: root.categoryIndex = index
        onBrowseGameRequested: root.selectedIndex = index
        onLaunchRequested: root.activateGame(game, acquisitionJob)
    }

    // NavigationCard { artworkRole: "icon" } remains the shared Home card contract.
    // displayTitle: "Installable"
    Repeater {
        id: homeCardRepeater
        visible: root.cardWidth > 0
        model: root.cardWidth > 0 ? root.homeCards() : []
        delegate: NavigationCard {
            required property int index
            required property var modelData
            readonly property real startX: root.homePresentationStartX[index] || 0
            // Match SystemHome's left-focal rail: the selected card settles at
            // the row origin, while the surrounding rail remains relative to it.
            readonly property real targetX: root.homeRailX(index - root.homeSelectedIndex)
            x: startX + (targetX - startX) * root.homeSelectionProgress
            y: 0
            width: root.cardWidth
            height: root.cardHeight
            displayTitle: modelData.title
            symbolicArtwork: MudosAssetCatalog.storeIcon(modelData.id, modelData.kind)
            artworkRole: "glyph"
            artworkSource: ""
            focused: index === root.homeSelectedIndex
            selectionProgress: (root.homeSelectionStart[index] || 0)
                + ((index === root.homeSelectedIndex ? 1 : 0)
                   - (root.homeSelectionStart[index] || 0)) * root.homeSelectionProgress
            selectedOpacityOwner: focused
            uiScale: root.uiScale
            typography: root.typography
            luluPalette: root.luluPalette
            canonicalTexture: root.canonicalTexture
            canonicalCoordinateRoot: root.canonicalCoordinateRoot
            canonicalSize: root.canonicalSize
            categoryProgress: root.categoryProgress
            categoryTransitioning: root.categoryTransitioning
            categoryFrom: root.categoryFrom
            categoryTarget: root.categoryTarget
            categoryDirection: root.categoryDirection
            presentationAncestorY: root.parent ? root.parent.y : 0
            presentationAncestorScale: root.parent ? root.parent.scale : 1
            motionBlurActive: root.categoryTransitioning
                || root.homeSelectionMotionActive
            motionBlurVector: root.presentationCoordinator
                ? root.presentationCoordinator.signedMotionBlurVectorFromVelocity(
                    (targetX - startX) * 5 * Math.pow(1 - root.homeSelectionProgress, 4)
                        / 500, root.categoryMotionVelocity) : Qt.vector2d(0, 0)
            motionStartX: startX
            motionTargetX: targetX
            motionProgress: root.homeSelectionProgress
            canonicalMappingDependency: ({
                ownerX: root.x, ownerY: root.y, ownerScale: root.scale,
                delegateX: x, delegateY: y, width: width, height: height,
                selectionProgress: root.homeSelectionProgress
            })
            onActivated: root.activateHome()
        }
    }
}
