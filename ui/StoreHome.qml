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
    signal availableGameSelected(var game)

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

    readonly property var displayGames: filteredGames()

    function moveCategory(delta) {
        categoryIndex = Math.max(0, Math.min(categories.length - 1, categoryIndex + delta))
        selectedIndex = 0
    }

    function moveGame(delta) {
        if (!displayGames.length)
            return
        selectedIndex = Math.max(0, Math.min(displayGames.length - 1, selectedIndex + delta))
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
        else
            availableGameSelected(game)
    }

    onAvailableGamesChanged: selectedIndex = Math.min(selectedIndex, Math.max(0, displayGames.length - 1))
    onCategoriesChanged: categoryIndex = Math.min(categoryIndex, Math.max(0, categories.length - 1))

    Text {
        x: 76 * root.uiScale
        y: 72 * root.uiScale
        text: "STORE"
        visible: root.cardWidth === 0
        color: root.luluPalette.headingAccent
        font.family: root.typography.displayFamily
        font.weight: root.typography.displayWeight
        font.pixelSize: root.typography.size("section", 30)
        font.letterSpacing: 5 * root.uiScale
    }

    Row {
        x: 120 * root.uiScale
        y: 112 * root.uiScale
        spacing: 38 * root.uiScale
        visible: root.cardWidth === 0
        Repeater {
            model: root.categories
            delegate: Text {
                required property int index
                required property var modelData
                text: modelData.label
                color: index === root.categoryIndex ? root.luluPalette.selectedText
                                                    : root.luluPalette.navigationText
                font.family: root.typography.interfaceFamily
                font.pixelSize: root.typography.size("secondary", 14)
                font.bold: index === root.categoryIndex
                Rectangle {
                    visible: index === root.categoryIndex
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.top: parent.bottom
                    anchors.topMargin: 6 * root.uiScale
                    height: 2 * root.uiScale
                    color: root.luluPalette.libraryHighlight
                }
            }
        }
    }

    Text {
        x: 120 * root.uiScale
        y: 154 * root.uiScale
        visible: root.cardWidth === 0
        text: "Available to Download"
        color: root.luluPalette.primaryText
        font.family: root.typography.displayFamily
        font.weight: root.typography.displayWeight
        font.pixelSize: root.typography.size("heading", 26)
    }

    Text {
        x: 120 * root.uiScale
        y: 204 * root.uiScale
        visible: root.availableGames.length === 0
            && root.cardWidth === 0
        text: root.errorMessage !== "" ? root.errorMessage : "No games available"
        color: root.luluPalette.mutedText
        font.family: root.typography.interfaceFamily
        font.pixelSize: root.typography.size("body", 24)
    }

    RecentHome {
        x: 120 * root.uiScale
        y: 184 * root.uiScale
        width: parent.width - 160 * root.uiScale
        height: root.focalCardHeight
        visible: root.displayGames.length > 0 && root.cardWidth === 0
        // The landing card remains the delegated Steam commerce entry point.
        recentGames: root.displayGames
        selectedIndex: root.selectedIndex
        focalCardWidth: root.focalCardWidth
        focalCardHeight: root.focalCardHeight
        compactCardWidth: root.compactCardWidth
        railGap: 18 * root.uiScale
        focalScale: 0.67
        uiScale: root.uiScale
        typography: root.typography
        luluPalette: root.luluPalette
        canonicalTexture: root.canonicalTexture
        canonicalCoordinateRoot: root.canonicalCoordinateRoot
        canonicalSize: root.canonicalSize
        onLaunchRequested: root.activateGame(game)
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
