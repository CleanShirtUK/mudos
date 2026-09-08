import QtQuick

Item {
    property var libraryGames: []
    property int selectedIndex: 0
    property int collectionIndex: 0
    property bool collectionFocus: false
    readonly property int surfaceMargin: 44
    readonly property int gridGap: 18
    readonly property int gridColumns: 6
    readonly property int collectionSelectorBottomY: 158
    readonly property int currentHeaderToGridGap: 22
    readonly property int headerToGridGap: currentHeaderToGridGap / 2
    readonly property real usableGridWidth: parent.width - 2 * (76 + surfaceMargin)
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
        x: 76
        y: 64
        width: parent.width - 152
        height: parent.height - 128
        radius: 28
        color: "#14213b"
        opacity: 0.82
        border.color: "#7884c6"
        border.width: 1
    }

    Text {
        x: 76 + surfaceMargin
        y: 96
        text: "LIBRARY"
        color: "#eadcff"
        font.pixelSize: 30
        font.letterSpacing: 5
    }

    Row {
        x: 120
        y: 120
        width: parent.width - 240
        spacing: 46

        Repeater {
            model: ["All Games", "Steam"]
            delegate: Text {
                required property int index
                text: modelData
                color: index === collectionIndex ? "#f0dcff" : "#8c98b6"
                font.pixelSize: 20
                font.bold: index === collectionIndex

                Rectangle {
                    visible: index === collectionIndex
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.top: parent.bottom
                    anchors.topMargin: 12
                    height: 2
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
        x: 120
        y: 206
        visible: libraryGames.length === 0
        text: "No installed launchable games"
        color: "#9aa8c2"
        font.pixelSize: 24
    }

    Item {
        id: gridViewport
        x: 76 + surfaceMargin
        y: collectionSelectorBottomY + headerToGridGap
        width: usableGridWidth
        height: parent.height - 240
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
                    width: libraryCardWidth
                    height: libraryCardHeight

                    GameCard {
                        anchors.fill: parent
                        game: modelData
                        focused: index === selectedIndex && !collectionFocus
                        compact: true
                        showAction: false

                        MouseArea {
                            anchors.fill: parent
                            onClicked: launchRequested(modelData)
                        }
                    }
                }
            }
        }

        Rectangle {
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.bottom: parent.bottom
            height: 52
            visible: gridContentHeight + gameGrid.y > parent.height
            gradient: Gradient {
                GradientStop { position: 0.0; color: "#0014213b" }
                GradientStop { position: 1.0; color: "#e614213b" }
            }
        }
    }
}
