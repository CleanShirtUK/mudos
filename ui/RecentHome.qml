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
    property var typography
    property var luluPalette
    property real compactCardWidth: Math.min(160 * uiScale, focalCardHeight * 0.62)
    property real railGap: 18 * uiScale
    property int visibleRailRadius: 3
    signal launchRequested(var game)

    Text {
        anchors.centerIn: parent
        visible: recentGames.length === 0
        text: "No recent games yet"
        color: luluPalette.mutedText
        font.family: typography ? typography.interfaceFamily : "JetBrains Mono"
        font.pixelSize: typography ? typography.size("body", 24) : 24 * uiScale
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
                readonly property int relativeIndex: index - recentHome.selectedIndex
                game: modelData
                focused: index === selectedIndex
                presentationState: modelData.game_id === recentHome.selectedGameId ? "FOCUSED" : "COMPACT"
                liveSceneCoordinates: recentFocal
                opticsStage: recentFocal ? 7 : -1
                compact: presentationState === "COMPACT"
                showAction: false
                homeCard: true
                canonicalTexture: recentHome.canonicalTexture
                canonicalCoordinateRoot: recentHome.canonicalCoordinateRoot
                canonicalSize: recentHome.canonicalSize
                focalScale: recentHome.focalScale
                uiScale: recentHome.uiScale
                typography: recentHome.typography
                luluPalette: recentHome.luluPalette
                 visible: Math.abs(relativeIndex) <= recentHome.visibleRailRadius
                 width: relativeIndex === 0
                        ? focalCardWidth
                        : recentHome.compactCardWidth
                 height: focalCardHeight
                 x: relativeIndex === 0
                    ? 0
                    : relativeIndex < 0
                      ? relativeIndex * (recentHome.compactCardWidth + recentHome.railGap)
                      : focalCardWidth + recentHome.railGap
                        + (relativeIndex - 1) * (recentHome.compactCardWidth + recentHome.railGap)

                MouseArea {
                    anchors.fill: parent
                    onClicked: launchRequested(modelData)
                }
            }
        }
    }
}
