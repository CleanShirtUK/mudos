import QtQuick

Item {
    id: librarySpace
    property var libraryGames: []
    property int selectedIndex: 0
    property int collectionIndex: 0
    property bool collectionFocus: false
    property string transitionState: "RESTING"
    property string returnState: "RESTING"
    property real uiScale: 1
    property var typography
    property var luluPalette
    readonly property string navigationObject: "library"
    readonly property real surfaceMargin: 44 * uiScale
    readonly property real gridGap: 18 * uiScale
    readonly property int gridColumns: 6
    readonly property real collectionSelectorBottomY: 158 * uiScale
    readonly property real currentHeaderToGridGap: 22 * uiScale
    readonly property real headerToGridGap: currentHeaderToGridGap / 2
    readonly property real usableGridWidth: parent.width - 2 * (76 * uiScale + surfaceMargin)
    readonly property real libraryCardWidth: (usableGridWidth - (gridColumns - 1) * gridGap) / gridColumns
    readonly property real libraryCardHeight: libraryCardWidth * 1.55
    readonly property real gridRowStep: libraryCardHeight + gridGap
    readonly property int gridRow: Math.floor(selectedIndex / gridColumns)
    readonly property real gridContentHeight: libraryGames.length
        ? Math.ceil(libraryGames.length / gridColumns) * gridRowStep - gridGap
        : 0
    signal collectionChanged(int index)
    signal launchRequested(var game)

    Rectangle {
        anchors.fill: parent
        color: luluPalette.backdrop
        opacity: 0.96
    }

    Rectangle {
        x: 76 * uiScale
        y: 64 * uiScale
        width: parent.width - 152 * uiScale
        height: parent.height - 128 * uiScale
        radius: 28 * uiScale
        color: luluPalette.librarySurface
        opacity: 0.82
        border.color: luluPalette.libraryHighlight
        border.width: uiScale
    }

    Text {
        x: 76 * uiScale + surfaceMargin
        y: 96 * uiScale
        text: "LIBRARY"
        color: luluPalette.headingAccent
        font.family: typography ? typography.displayFamily : "Zalando Sans Condensed Black"
        font.weight: typography ? typography.displayWeight : Font.Black
        font.pixelSize: typography ? typography.size("section", 30) : 30 * uiScale
        font.letterSpacing: 5 * uiScale
    }

    Row {
        x: 120 * uiScale
        y: 120 * uiScale
        width: parent.width - 240 * uiScale
        spacing: 46 * uiScale

        Repeater {
            model: ["All Games", "Steam"]
            delegate: Text {
                required property int index
                required property string modelData
                text: modelData
                color: index === collectionIndex ? luluPalette.selectedText : luluPalette.navigationText
                font.family: typography ? typography.interfaceFamily : "JetBrains Mono"
                font.pixelSize: typography ? typography.size("body", 20) : 20 * uiScale
                font.bold: index === collectionIndex

                Rectangle {
                    visible: index === collectionIndex
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.top: parent.bottom
                    anchors.topMargin: 12 * uiScale
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
        y: 206 * uiScale
        visible: libraryGames.length === 0
        text: "No installed launchable games"
        color: luluPalette.mutedText
        font.family: typography ? typography.interfaceFamily : "JetBrains Mono"
        font.pixelSize: typography ? typography.size("secondary", 24) : 24 * uiScale
    }

    Item {
        id: gridViewport
        x: 76 * uiScale + surfaceMargin
        y: collectionSelectorBottomY + headerToGridGap
        width: usableGridWidth
        height: parent.height - 240 * uiScale
        clip: true

        Grid {
            id: gameGrid
            y: -gridRow * gridRowStep
            width: usableGridWidth
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
                        game: gameData
                        focused: index === selectedIndex && !collectionFocus
                        compact: true
                        uiScale: librarySpace.uiScale
                        typography: librarySpace.typography
                        luluPalette: librarySpace.luluPalette
                        showAction: false

                        MouseArea {
                            anchors.fill: parent
                            onClicked: launchRequested(gameData)
                        }
                    }
                }
            }
        }

        Rectangle {
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.bottom: parent.bottom
            height: 52 * uiScale
            visible: gridContentHeight + gameGrid.y > parent.height
            gradient: Gradient {
                GradientStop { position: 0.0; color: luluPalette.scrollFadeStart }
                GradientStop { position: 1.0; color: luluPalette.scrollFadeEnd }
            }
        }
    }
}
