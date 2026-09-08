import QtQuick

Item {
    id: recentHome
    property var recentGames: []
    property int selectedIndex: 0
    property int transitionFromIndex: 0
    property real transitionProgress: 1
    property bool transitionInitialized: false
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

    function railX(relativeIndex) {
        return relativeIndex === 0
            ? 0
            : relativeIndex < 0
              ? relativeIndex * (compactCardWidth + railGap)
              : focalCardWidth + railGap
                + (relativeIndex - 1) * (compactCardWidth + railGap)
    }

    function railWidth(relativeIndex) {
        return relativeIndex === 0 ? focalCardWidth : compactCardWidth
    }

    onSelectedIndexChanged: {
        if (!transitionInitialized) {
            transitionFromIndex = selectedIndex
            transitionProgress = 1
            return
        }
        transitionFromIndex = Math.max(0, Math.min(recentGames.length - 1,
                                                    transitionFromIndex))
        transitionProgress = 0
        transitionAnimation.restart()
    }

    Component.onCompleted: {
        transitionFromIndex = selectedIndex
        transitionProgress = 1
        transitionInitialized = true
    }

    NumberAnimation {
        id: transitionAnimation
        target: recentHome
        property: "transitionProgress"
        to: 1
        duration: 300
        easing.type: Easing.Linear
        onStopped: {
            recentHome.transitionFromIndex = recentHome.selectedIndex
            recentHome.transitionProgress = 1
        }
    }

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
                readonly property int fromRelativeIndex: index - recentHome.transitionFromIndex
                readonly property int toRelativeIndex: index - recentHome.selectedIndex
                readonly property real railProgress: recentHome.transitionProgress
                readonly property real blend: fromRelativeIndex === 0
                    ? (toRelativeIndex === 0 ? 1 : 1 - railProgress)
                    : (toRelativeIndex === 0 ? railProgress : 0)
                game: modelData
                focused: index === recentHome.selectedIndex
                presentationProgress: blend
                compactEndpointWidth: recentHome.compactCardWidth
                focalChromeOpacity: fromRelativeIndex === 0 && toRelativeIndex === 0
                    ? 1
                    : fromRelativeIndex === 0
                      ? Math.max(0, 1 - railProgress * 3)
                      : toRelativeIndex === 0
                        ? Math.max(0, (railProgress - 0.67) * 3)
                        : 0
                presentationState: modelData.game_id === recentHome.selectedGameId ? "FOCUSED" : "COMPACT"
                liveSceneCoordinates: true
                opticsStage: blend > 0 ? 7 : -1
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
                 visible: Math.min(Math.abs(fromRelativeIndex), Math.abs(toRelativeIndex))
                     <= recentHome.visibleRailRadius
                 width: recentHome.railWidth(fromRelativeIndex)
                     + (recentHome.railWidth(toRelativeIndex)
                        - recentHome.railWidth(fromRelativeIndex)) * railProgress
                 height: focalCardHeight
                 x: recentHome.railX(fromRelativeIndex)
                    + (recentHome.railX(toRelativeIndex)
                       - recentHome.railX(fromRelativeIndex)) * railProgress

                MouseArea {
                    anchors.fill: parent
                    onClicked: launchRequested(modelData)
                }
            }
        }
    }
}
