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
    property var presentationCoordinator
    property real categoryProgress: 1
    property bool categoryTransitioning: false
    property int categoryFrom: -1
    property int categoryTarget: -1
    property int categoryDirection: 1
    property real categoryMotionVelocity: 0
    signal steamStoreRequested()
    signal installGameRequested(var game)

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
            var decorated = ({})
            for (var key in game)
                decorated[key] = game[key]
            var job = acquisitionJobs[String(game.game_id)]
            if (!job && game.provider === "steam")
                job = acquisitionJobs["steam:" + String(game.provider_id)]
            if (job) {
                decorated.acquisition_state = String(job.state || "")
                decorated.acquisition_progress = job.progress === null || job.progress === undefined
                    ? null : Number(job.progress)
                decorated.acquisition_stage = String(job.stage || "")
                decorated.acquisition_error = job.error || null
            }
            result.push(decorated)
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

    // Keep the binding dependent on the async model/category assignments;
    // dependencies hidden inside filteredGames() are not reliably tracked by
    // the QML binding compiler.
    // availableGames.length + categories.length + displayCategoryIndex >= 0
    readonly property var displayGames: availableGames.length + categories.length + displayCategoryIndex
        + Object.keys(acquisitionJobs).length >= 0
        ? filteredGames() : []

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

    function activateGame(game) {
        if (!game)
            return
        if (String(game.game_id) === "steam-store")
            steamStoreRequested()
        else if ((game.provider === "steam" || game.provider === "romm")
                 && ["queued", "starting", "transferring", "finalizing", "paused", "cancelling"].indexOf(String(game.acquisition_state)) < 0
                 && String(game.provider_id).match(/^[1-9][0-9]*$/))
            installGameRequested(game)
    }

    onAvailableGamesChanged: selectedIndex = Math.min(selectedIndex, Math.max(0, displayGames.length - 1))
    onCategoriesChanged: {
        categoryIndex = Math.min(categoryIndex, Math.max(0, categories.length - 1))
        displayCategoryIndex = Math.min(displayCategoryIndex, Math.max(0, categories.length - 1))
    }
    LibrarySpace {
        anchors.fill: parent
        visible: root.cardWidth === 0
        libraryGames: root.displayGames
        selectedIndex: root.selectedIndex
        firstVisibleRow: root.firstVisibleRow
        collectionIndex: root.categoryIndex
        collections: root.categories
        collectionFocus: false
        headingText: "STORE"
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
        onLaunchRequested: root.activateGame(game)
        onSpecialActivated: root.steamStoreRequested()
        onCategoryContentHidden: root.displayCategoryIndex = root.categoryIndex
    }

    NavigationCard {
        visible: root.cardWidth > 0
        width: root.cardWidth
        height: root.cardHeight
        displayTitle: "Store"
        symbolicArtwork: ""
        artworkRole: "raster"
        artworkSource: Qt.resolvedUrl(MudosAssetCatalog.suppliedArtwork("store"))
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
