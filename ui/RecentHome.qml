import QtQuick

Item {
    id: recentHome
    property var recentGames: []
    property int selectedIndex: 0
    readonly property string selectedGameId: recentGames.length && selectedIndex >= 0
        ? String(recentGames[selectedIndex].game_id) : ""
    property real focalCardWidth: 760
    property real focalCardHeight: 500
    property real focalScale: 1
    property var canonicalTexture
    property var canonicalCoordinateRoot
    property size canonicalSize: Qt.size(1280, 720)
    property real uiScale: 1
    readonly property real compactCardWidth: Math.min(160 * uiScale, focalCardHeight * 0.62)
    signal launchRequested(var game)

    Text {
        anchors.centerIn: parent
        visible: recentGames.length === 0
        text: "No recent games yet"
        color: "#9aa8c2"
        font.pixelSize: 24 * uiScale
    }

    Item {
        x: 0
        y: 0
        width: parent.width
        height: parent.height
        visible: recentGames.length > 0

        Repeater {
            model: recentGames
            delegate: GameCard {
                required property int index
                required property var modelData
                game: modelData
                focused: index === selectedIndex
                presentationState: modelData.game_id === recentHome.selectedGameId ? "FOCUSED" : "COMPACT"
                compact: presentationState === "COMPACT"
                showAction: false
                homeCard: true
                canonicalTexture: recentHome.canonicalTexture
                canonicalCoordinateRoot: recentHome.canonicalCoordinateRoot
                canonicalSize: recentHome.canonicalSize
                focalScale: recentHome.focalScale
                uiScale: recentHome.uiScale
                width: index === selectedIndex
                       ? focalCardWidth
                       : recentHome.compactCardWidth
                height: focalCardHeight
                x: index === selectedIndex
                   ? 0
                   : focalCardWidth + 18 * uiScale + (index < selectedIndex ? index : index - 1)
                      * (recentHome.compactCardWidth + 18 * uiScale)

                MouseArea {
                    anchors.fill: parent
                    onClicked: launchRequested(modelData)
                }
            }
        }
    }
}
