import QtQuick

Item {
    id: recentHome
    property var recentGames: []
    property int selectedIndex: 0
    property real focalCardWidth: 760
    property real focalCardHeight: 500
    property real focalScale: 1
    property var canonicalTexture
    property size canonicalSize: Qt.size(1280, 720)
    signal launchRequested(var game)

    Text {
        anchors.centerIn: parent
        visible: recentGames.length === 0
        text: "No recent games yet"
        color: "#9aa8c2"
        font.pixelSize: 24
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
                showAction: false
                homeCard: true
                canonicalTexture: recentHome.canonicalTexture
                canonicalSize: recentHome.canonicalSize
                focalScale: recentHome.focalScale
                width: index === selectedIndex
                       ? focalCardWidth
                       : Math.min(210, focalCardHeight * 0.38)
                height: index === selectedIndex ? focalCardHeight : width * 1.67
                x: index === selectedIndex
                   ? 0
                   : focalCardWidth + 18 + (index < selectedIndex ? index : index - 1) * (Math.min(210, focalCardHeight * 0.38) + 18)

                MouseArea {
                    anchors.fill: parent
                    onClicked: launchRequested(modelData)
                }
            }
        }
    }
}
