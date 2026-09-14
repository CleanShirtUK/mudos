import QtQuick

Item {
    id: librarySpace
    property var libraryGames: []
    property int selectedIndex: 0
    property int firstVisibleRow: 0
    property int collectionIndex: 0
    property var collections: [{"label": "All Games", "scope": "all"}, {"label": "PC Games", "scope": "pc"}]
    property bool collectionFocus: false
    property string transitionState: "RESTING"
    property string returnState: "RESTING"
    property real contentOpacity: 1
    property real uiScale: 1
    property var typography
    property var luluPalette
    property var canonicalTexture
    property var canonicalCoordinateRoot
    property size canonicalSize: Qt.size(1280, 720)
    property string headingText: "LIBRARY"
    property string sectionTitle: ""
    property string emptyText: "No installed games"
    property string specialCardId: ""
    property string actionLabel: "A  Play"
    readonly property string navigationObject: "library"
    readonly property real surfaceMargin: 44 * uiScale
    readonly property real gridGap: 14 * uiScale
    readonly property int gridColumns: 7
    readonly property real fullscreenPanelBevelWidth: 6 * uiScale
    readonly property real fullscreenPanelCardSelectionScale: 1.05
    readonly property real fullscreenPanelCardSafetyMargin: 4 * uiScale
    readonly property real fullscreenPanelBorderWidth: 0
    readonly property real fullscreenPanelTransmission: 1
    readonly property real morphTransmission: 1
    readonly property real morphBulgeStrength: 100
    readonly property real collectionSelectorBottomY: 164 * uiScale
    readonly property real currentHeaderToGridGap: 22 * uiScale
    readonly property real headerToGridGap: currentHeaderToGridGap / 2
    readonly property real usableGridWidth: parent.width - 2 * (76 * uiScale + surfaceMargin)
    readonly property real gridTop: collectionSelectorBottomY + headerToGridGap
    readonly property real gridBottom: parent.height - 64 * uiScale
    readonly property real gridRegionHeight: Math.max(0, gridBottom - gridTop)
    readonly property real horizontalCardWidth: (usableGridWidth - (gridColumns - 1) * gridGap
        - 2 * fullscreenPanelCardSafetyMargin) /
        (gridColumns + fullscreenPanelCardSelectionScale - 1.0)
    readonly property real verticalCardWidth: (gridRegionHeight - gridGap
        - 2 * fullscreenPanelCardSafetyMargin) /
        (1.55 * (2 + 2 * (fullscreenPanelCardSelectionScale - 1.0)))
    readonly property real libraryCardWidth: Math.min(horizontalCardWidth, verticalCardWidth)
    readonly property real libraryCardHeight: libraryCardWidth * 1.55
    readonly property real gridHorizontalGrowth:
        ((fullscreenPanelCardSelectionScale - 1.0) * libraryCardWidth) / 2
    readonly property real gridVerticalGrowth:
        ((fullscreenPanelCardSelectionScale - 1.0) * libraryCardHeight) / 2
    readonly property real gridLeftInset: gridHorizontalGrowth + fullscreenPanelCardSafetyMargin
    readonly property real gridRightInset: gridLeftInset
    readonly property real gridTopInset: gridVerticalGrowth + fullscreenPanelCardSafetyMargin
    readonly property real gridBottomInset: gridTopInset
    readonly property real gridRowStep: libraryCardHeight + gridGap
    property point surfaceSceneOrigin: Qt.point(0, 0)
    property real unfocusedBrightness: 0.6
    readonly property int gridRow: Math.floor(selectedIndex / gridColumns)
    readonly property real gridContentHeight: libraryGames.length
        ? Math.ceil(libraryGames.length / gridColumns) * gridRowStep - gridGap
        : 0
    signal collectionChanged(int index)
    signal launchRequested(var game)
    signal specialActivated(var game)

    // Keeps stacked-card shader coordinates aligned with the persistent shell surface.
    Item {
        id: librarySurface
        x: 76 * uiScale
        y: 64 * uiScale
        width: parent.width - 152 * uiScale
        height: parent.height - 128 * uiScale
        visible: false
    }

    Text {
        x: 76 * uiScale + surfaceMargin
        opacity: librarySpace.contentOpacity
        y: 96 * uiScale
        text: librarySpace.headingText
        color: luluPalette.headingAccent
        font.family: typography ? typography.displayFamily : "Zalando Sans Condensed Black"
        font.weight: typography ? typography.displayWeight : Font.Black
        font.pixelSize: typography ? typography.size("section", 30) : 30 * uiScale
        font.letterSpacing: 5 * uiScale
    }

    Row {
        x: 120 * uiScale
        opacity: librarySpace.contentOpacity
        y: 136 * uiScale
        width: parent.width - 240 * uiScale
        spacing: 46 * uiScale

        Repeater {
            model: librarySpace.collections
            delegate: Text {
                required property int index
                required property var modelData
                // required property string modelData (legacy string-model contract)
                text: modelData.label
                color: index === collectionIndex ? luluPalette.selectedText : luluPalette.navigationText
                font.family: typography ? typography.interfaceFamily : "JetBrains Mono"
                font.pixelSize: typography ? typography.size("secondary", 14) : 14 * uiScale
                font.bold: index === collectionIndex

                Rectangle {
                    visible: index === collectionIndex
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.top: parent.bottom
                    anchors.topMargin: 6 * uiScale
                    height: 2 * uiScale
                    color: collectionFocus ? luluPalette.focusIndicator : luluPalette.libraryHighlight
                }

                MouseArea {
                    anchors.fill: parent
                    onClicked: collectionChanged(index)
                }
            }
        }
    }

    Text {
        x: 120 * uiScale
        opacity: librarySpace.contentOpacity
        y: 154 * uiScale
        visible: librarySpace.sectionTitle !== ""
        text: librarySpace.sectionTitle
        color: luluPalette.primaryText
        font.family: typography ? typography.displayFamily : "Zalando Sans Condensed Black"
        font.weight: typography ? typography.displayWeight : Font.Black
        font.pixelSize: typography ? typography.size("heading", 26) : 26 * uiScale
    }

    Text {
        x: 120 * uiScale
        opacity: librarySpace.contentOpacity
        y: 206 * uiScale
        visible: libraryGames.length === 0
        text: librarySpace.emptyText
        color: luluPalette.mutedText
        font.family: typography ? typography.interfaceFamily : "JetBrains Mono"
        font.pixelSize: typography ? typography.size("secondary", 24) : 24 * uiScale
    }

    Item {
        id: gridViewport
        opacity: librarySpace.contentOpacity
        x: 76 * uiScale + surfaceMargin - gridLeftInset
        y: gridTop - gridTopInset
        width: usableGridWidth + gridLeftInset + gridRightInset
        height: gridRegionHeight + gridTopInset + gridBottomInset
        clip: true

        Grid {
            id: gameGrid
            x: gridLeftInset
            y: gridTopInset - firstVisibleRow * gridRowStep
            width: usableGridWidth - gridLeftInset - gridRightInset
            columns: gridColumns
            rowSpacing: gridGap
            columnSpacing: gridGap
            visible: libraryGames.length > 0

            Repeater {
                model: libraryGames
                delegate: Item {
                    required property int index
                    required property var modelData
                    readonly property var gameData: modelData
                    width: libraryCardWidth
                    height: libraryCardHeight

                    GameCard {
                        anchors.fill: parent
                        visible: !librarySpace.specialCardId
                            || String(gameData.game_id) !== librarySpace.specialCardId
                        game: gameData
                        focused: index === selectedIndex && !collectionFocus
                        compact: true
                        uiScale: librarySpace.uiScale
                        typography: librarySpace.typography
                        luluPalette: librarySpace.luluPalette
                        canonicalTexture: librarySpace.canonicalTexture
                        canonicalCoordinateRoot: librarySpace.canonicalCoordinateRoot
                        canonicalSize: librarySpace.canonicalSize
                        showAction: false
                        actionLabel: librarySpace.actionLabel
                        stackedGlass: true
                        stackedCardBevelWidth: 3 * librarySpace.uiScale
                        stackedPlayBevelWidth: 3 * librarySpace.uiScale
                        stackedPlayEdgeLightStrength: 0.18
                        stackedCardBulgeStrength: 0
                        stackedCardRefractionPixels: 0
                        stackedCardDispersionIor: 0
                        stackedPlayRefractionPixels: 8 * librarySpace.uiScale
                        stackedPlayDispersionIor: 0
                        stackedPlayBulgeStrength: 0
                        focusBrightness: focused ? 1 : librarySpace.unfocusedBrightness
                        stackedCoordinateRoot: librarySurface
                        stackedCardOrigin: Qt.vector2d(librarySpace.surfaceSceneOrigin.x,
                                                       librarySpace.surfaceSceneOrigin.y)
                        stackedCardSize: Qt.vector2d(librarySurface.width,
                                                    librarySurface.height)
                        scale: focused ? librarySpace.fullscreenPanelCardSelectionScale : 1
                        z: focused ? 2 : 1

                        MouseArea {
                            anchors.fill: parent
                            onClicked: launchRequested(gameData)
                        }
                    }

                    NavigationCard {
                        anchors.fill: parent
                        visible: librarySpace.specialCardId !== ""
                            && String(gameData.game_id) === librarySpace.specialCardId
                        displayTitle: gameData.title
                        symbolicArtwork: ""
                        artworkRole: "raster"
                        artworkSource: gameData.artwork_url || Qt.resolvedUrl("artwork/store.png")
                        focused: index === selectedIndex && !collectionFocus
                        uiScale: librarySpace.uiScale
                        typography: librarySpace.typography
                        luluPalette: librarySpace.luluPalette
                        canonicalTexture: librarySpace.canonicalTexture
                        canonicalCoordinateRoot: librarySpace.canonicalCoordinateRoot
                        canonicalSize: librarySpace.canonicalSize
                        onActivated: specialActivated(gameData)
                    }
                }
            }
        }

    }

}
