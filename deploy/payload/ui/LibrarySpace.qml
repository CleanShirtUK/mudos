import QtQuick
import "MudosAssetCatalog.js" as MudosAssetCatalog

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
    property real gameContentOpacity: 1
    property bool gameContentVisible: true
    property real uiScale: 1
    property var typography
    property var luluPalette
    property var canonicalTexture
    property var canonicalCoordinateRoot
    property size canonicalSize: Qt.size(1280, 720)
    property real contentBottom: parent ? parent.height : 0
    property real contentSideMargin: 120 * uiScale
    property string headingText: "LIBRARY"
    property string sectionTitle: ""
    property string emptyText: "No installed games"
    property string specialCardId: ""
    property string actionLabel: "Play"
    readonly property string navigationObject: "library"
    readonly property real surfaceMargin: 44 * uiScale
    readonly property real gridGap: 14 * uiScale
    readonly property int gridColumns: 6
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
    // A shared, restrained presentation reduction creates header breathing
    // room while preserving the card aspect ratio and six-column grid.
    readonly property real expandedCardScale: 0.92
    readonly property real usableGridWidth: parent.width - 2 * contentSideMargin
    readonly property real headingBottom: pageHeading.y + pageHeading.height
    readonly property real firstRowTop: gridTop - selectedGrowth
    readonly property real categoryRailHeight: categoryRow.implicitHeight + 8 * uiScale
    readonly property real gridSlotWidth:
        gridColumns * libraryCardWidth + (gridColumns - 1) * gridGap
    readonly property real gridVisualWidth: gridSlotWidth + 2 * gridHorizontalGrowth
    readonly property real contentOriginX: (parent.width - gridVisualWidth) / 2
    readonly property real gridSlotLeft: contentOriginX + gridHorizontalGrowth
    readonly property real gridContentFootprintHeight:
        libraryCardHeight + gridGap + libraryCardHeight + selectedGrowth
    readonly property real gridTop: contentBottom - gridContentFootprintHeight
    // Keep the catalogue backing boundary separate from the two-row card clip.
    readonly property real gridBottom:
        parent.height - 16 * uiScale - gridBottomInset
    readonly property real gridRegionHeight: requiredTwoRowHeight
    readonly property real horizontalCardWidth:
        ((usableGridWidth - (gridColumns - 1) * gridGap) / gridColumns)
            * expandedCardScale
    readonly property real libraryCardWidth: horizontalCardWidth
    readonly property real libraryCardHeight: libraryCardWidth * 1.55
    readonly property real gridHorizontalGrowth:
        ((fullscreenPanelCardSelectionScale - 1.0) * libraryCardWidth) / 2
    readonly property real gridVerticalGrowth:
        ((fullscreenPanelCardSelectionScale - 1.0) * libraryCardHeight) / 2
    readonly property real selectedGrowth: gridVerticalGrowth
    readonly property real requiredTwoRowHeight:
        libraryCardHeight + gridGap + libraryCardHeight
        + selectedGrowth + fullscreenPanelCardSafetyMargin
    readonly property real gridLeftInset: gridHorizontalGrowth + fullscreenPanelCardSafetyMargin
    // GridView cells include the gap after each card, including the final one.
    // Reserve that trailing cell space so six width-derived cards fit exactly.
    readonly property real gridRightInset: gridLeftInset + gridGap
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
    signal launchRequested(var game, var acquisitionJob)
    signal specialActivated(var game)
    signal categoryContentHidden()

    Behavior on gameContentOpacity {
        NumberAnimation {
            duration: librarySpace.gameContentOpacity === 0 ? 100 : 200
            easing.type: Easing.OutQuint
        }
    }

    Timer {
        id: categoryContentFadeTimer
        interval: 100
        repeat: false
        onTriggered: {
            librarySpace.gameContentVisible = false
            categoryContentHidden()
            categoryContentRevealTimer.restart()
        }
    }

    Timer {
        id: categoryContentRevealTimer
        interval: 50
        repeat: false
        onTriggered: {
            librarySpace.gameContentVisible = true
            librarySpace.gameContentOpacity = 1
        }
    }

    onCollectionIndexChanged: {
        librarySpace.gameContentOpacity = 0
        categoryContentFadeTimer.restart()
    }

    // Keeps stacked-card shader coordinates aligned with the persistent shell surface.
    Item {
        id: librarySurface
        x: contentOriginX
        y: 32 * uiScale
        width: parent.width - 152 * uiScale
        height: parent.height - 48 * uiScale
        visible: false
    }

    Text {
        id: pageHeading
        x: contentOriginX
        opacity: librarySpace.contentOpacity
        y: 81 * uiScale
        text: librarySpace.headingText
        color: luluPalette.headingAccent
        font.family: typography ? typography.majorHeadingFamily : "JetBrains Mono"
        font.weight: typography ? typography.majorHeadingWeight : Font.Black
        font.pixelSize: typography ? typography.size("section", 30) : 30 * uiScale
        font.letterSpacing: 5 * uiScale
    }

    readonly property real categoryGap: 24 * uiScale

    Item {
        id: categoryViewport
        x: contentOriginX
        opacity: librarySpace.contentOpacity
        y: librarySpace.headingBottom
            + (librarySpace.firstRowTop - librarySpace.headingBottom
                - librarySpace.categoryRailHeight) / 2
        width: gridVisualWidth
        height: librarySpace.categoryRailHeight
        clip: true

        Item {
            id: categoryRail
            // Keep the selected delegate's left edge anchored while the row
            // underneath it is laid out from each label's natural width.
                readonly property var selectedCategoryDelegate:
                categoryRepeater.itemAt(librarySpace.collectionIndex)
            x: selectedCategoryDelegate ? -selectedCategoryDelegate.x : 0
            width: categoryRow.implicitWidth
            height: librarySpace.categoryRailHeight

            Behavior on x {
                NumberAnimation {
                    duration: 500
                    easing.type: Easing.OutQuint
                }
            }

            Row {
                id: categoryRow
                anchors.left: parent.left
                anchors.top: parent.top
                spacing: librarySpace.categoryGap

                Repeater {
                    id: categoryRepeater
                    model: librarySpace.collections
                    delegate: Text {
                        required property int index
                        required property var modelData
                        // required property string modelData (legacy string-model contract)
                        text: modelData.label
                        horizontalAlignment: Text.AlignHCenter
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

        }
    }

    Text {
        x: 120 * uiScale
        opacity: librarySpace.contentOpacity
        y: 154 * uiScale
        visible: librarySpace.sectionTitle !== ""
        text: librarySpace.sectionTitle
        color: luluPalette.primaryText
        font.family: typography ? typography.displayFamily : "JetBrains Mono"
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
        opacity: librarySpace.contentOpacity * librarySpace.gameContentOpacity
        visible: librarySpace.gameContentVisible && libraryGames.length > 0
        x: gridSlotLeft - gridLeftInset
        y: gridTop - gridTopInset
        width: gridVisualWidth + gridLeftInset + gridRightInset
        height: gridRegionHeight + gridTopInset
        clip: true

        GridView {
            id: gameGrid
            x: gridLeftInset
            y: gridTopInset
            width: gridSlotWidth + gridGap
            height: gridRegionHeight
            cellWidth: libraryCardWidth + gridGap
            cellHeight: libraryCardHeight + gridGap
            cacheBuffer: 2 * gridRowStep
            reuseItems: true
            currentIndex: librarySpace.selectedIndex
            // The outer insets contain the selected card's scaled height;
            // selection must not reposition the grid.
            highlightRangeMode: GridView.NoHighlightRange
            highlightFollowsCurrentItem: false
            contentY: librarySpace.firstVisibleRow * librarySpace.gridRowStep
            interactive: false
            boundsBehavior: Flickable.StopAtBounds
            visible: libraryGames.length > 0

            Behavior on contentY {
                NumberAnimation {
                    duration: 180
                    easing.type: Easing.OutQuint
                }
            }

            model: libraryGames
            delegate: Item {
                required property int index
                required property var modelData
                readonly property var gameData: modelData.game || modelData
                width: libraryCardWidth
                height: libraryCardHeight

                GameCard {
                    anchors.fill: parent
                    visible: !librarySpace.specialCardId
                        || String(gameData.game_id) !== librarySpace.specialCardId
                    game: gameData
                    acquisitionJob: modelData.acquisitionJob || null
                    focused: index === librarySpace.selectedIndex && !librarySpace.collectionFocus
                    compact: true
                    uiScale: librarySpace.uiScale
                    typography: librarySpace.typography
                    luluPalette: librarySpace.luluPalette
                     canonicalTexture: librarySpace.canonicalTexture
                     canonicalCoordinateRoot: librarySpace.canonicalCoordinateRoot
                     canonicalSize: librarySpace.canonicalSize
                     nativeGlassTransparentOutsideMask: true
                     canonicalMappingDependency: ({
                         viewportX: gridViewport.x,
                         viewportY: gridViewport.y,
                         gridX: gameGrid.x,
                         gridY: gameGrid.y,
                         contentY: gameGrid.contentY,
                         delegateX: parent.x,
                         delegateY: parent.y,
                         width: width,
                         height: height,
                         scale: scale,
                         selectionProgress: selectionProgress
                     })
                     canonicalMappingRevision: gridViewport.x
                         + gridViewport.y + gameGrid.x + gameGrid.y
                         + gameGrid.contentY + parent.x + parent.y
                         + scale + selectionProgress
                    showAction: false
                     actionLabel: (modelData.acquisition_state || gameData.acquisition_state) === "queued" ? "Queued"
                         : (modelData.acquisition_state || gameData.acquisition_state) === "starting" ? "Starting"
                         : (modelData.acquisition_state || gameData.acquisition_state) === "transferring" ? "Downloading"
                         : (modelData.acquisition_state || gameData.acquisition_state) === "finalizing" ? "Finalizing"
                         : (modelData.acquisition_state || gameData.acquisition_state) === "failed"
                           && (!modelData.acquisition_error && !gameData.acquisition_error
                               || (modelData.acquisition_error || gameData.acquisition_error).retryable !== false)
                           ? "Retry Download"
                         : librarySpace.actionLabel
                    catalogueCard: true
                    librarySurfaceMaterial: true
                    focusBrightness: (index === librarySpace.selectedIndex
                        && !librarySpace.collectionFocus)
                        ? 1 : librarySpace.unfocusedBrightness
                    scale: focused ? librarySpace.fullscreenPanelCardSelectionScale : 1
                    z: focused ? 2 : 1

                    MouseArea {
                        anchors.fill: parent
                         onClicked: launchRequested(gameData, modelData.acquisitionJob || null)
                    }
                }

                NavigationCard {
                    anchors.fill: parent
                    visible: librarySpace.specialCardId !== ""
                        && String(gameData.game_id) === librarySpace.specialCardId
                    displayTitle: gameData.title
                    symbolicArtwork: ""
                    artworkRole: "raster"
                    artworkSource: gameData.artwork_url
                        || Qt.resolvedUrl(MudosAssetCatalog.suppliedArtwork("store"))
                    focused: index === librarySpace.selectedIndex && !librarySpace.collectionFocus
                    uiScale: librarySpace.uiScale
                    typography: librarySpace.typography
                    luluPalette: librarySpace.luluPalette
                     canonicalTexture: librarySpace.canonicalTexture
                     canonicalCoordinateRoot: librarySpace.canonicalCoordinateRoot
                     canonicalSize: librarySpace.canonicalSize
                     transparentOutsideMask: true
                     mappingRevision: gridViewport.x + gridViewport.y
                         + gameGrid.x + gameGrid.y + gameGrid.contentY
                         + parent.x + parent.y + scale + selectionProgress
                    onActivated: specialActivated(gameData)
                }
            }
        }

    }

}
