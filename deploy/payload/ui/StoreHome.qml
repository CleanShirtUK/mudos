import QtQuick

Item {
    id: root
    property real cardHeight: 0
    property real cardWidth: 0
    property var availableGames: []
    property var categories: [{"label": "All Available", "scope": "all"}]
    property string errorMessage: ""
    property int categoryIndex: 0
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
    signal steamStoreRequested()
    signal installGameRequested(var game)

    function filteredGames() {
        var scope = categories.length > categoryIndex ? categories[categoryIndex].scope : "all"
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
        if (root.cardWidth === 0)
            result.push({game_id: "steam-store", title: "Steam Store",
                         artwork_url: Qt.resolvedUrl("artwork/store.png"),
                         artwork_suppressed: false, provider: "steam-store"})
        return result
    }

    // Keep the binding dependent on the async model/category assignments;
    // dependencies hidden inside filteredGames() are not reliably tracked by
    // the QML binding compiler.
    readonly property var displayGames: availableGames.length + categories.length + categoryIndex >= 0
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
        var column = selectedIndex % 7
        var row = Math.floor(selectedIndex / 7) + delta
        if (row < 0 || row * 7 >= displayGames.length)
            return
        selectedIndex = Math.min(row * 7 + column, displayGames.length - 1)
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
        else if (game.provider === "steam" && String(game.provider_id).match(/^[1-9][0-9]*$/))
            installGameRequested(game)
    }

    onAvailableGamesChanged: selectedIndex = Math.min(selectedIndex, Math.max(0, displayGames.length - 1))
    onCategoriesChanged: categoryIndex = Math.min(categoryIndex, Math.max(0, categories.length - 1))

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
        sectionTitle: "Available to Download"
        emptyText: root.errorMessage !== "" ? root.errorMessage : "No games available"
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
    }

    NavigationCard {
        visible: root.cardWidth > 0
        width: root.cardWidth
        height: root.cardHeight
        displayTitle: "Store"
        symbolicArtwork: ""
        artworkRole: "raster"
        artworkSource: Qt.resolvedUrl("artwork/store.png")
        uiScale: root.uiScale
        typography: root.typography
        luluPalette: root.luluPalette
        canonicalTexture: root.canonicalTexture
        canonicalCoordinateRoot: root.canonicalCoordinateRoot
        canonicalSize: root.canonicalSize
        onActivated: root.steamStoreRequested()
    }
}
