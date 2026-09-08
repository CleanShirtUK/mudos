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
        color: "#060b16"
        opacity: 0.96
    }

    Rectangle {
        x: 76 * uiScale
        y: 64 * uiScale
        width: parent.width - 152 * uiScale
        height: parent.height - 128 * uiScale
        radius: 28 * uiScale
        color: "#14213b"
        opacity: 0.82
        border.color: "#7884c6"
        border.width: uiScale
    }

    Text {
        x: 76 * uiScale + surfaceMargin
        y: 96 * uiScale
        text: "LIBRARY"
        color: "#eadcff"
        font.pixelSize: 30 * uiScale
        font.letterSpacing: 5
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
                color: index === collectionIndex ? "#f0dcff" : "#8c98b6"
                font.pixelSize: 20 * uiScale
                font.bold: index === collectionIndex

                Rectangle {
                    visible: index === collectionIndex
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.top: parent.bottom
                    anchors.topMargin: 12 * uiScale
                    height: 2 * uiScale
                    color: collectionFocus ? "#e0c5ff" : "#7884c6"
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
        color: "#9aa8c2"
        font.pixelSize: 24 * uiScale
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
                GradientStop { position: 0.0; color: "#0014213b" }
                GradientStop { position: 1.0; color: "#e614213b" }
            }
        }
    }
}
