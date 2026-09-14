import QtQuick

Item {
    id: recentHome
    property var recentGames: []
    property int selectedIndex: 0
    property int transitionFromIndex: 0
    property real transitionProgress: 1
    property real transitionFadeProgress: 1
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
    property var presentationStartX: []
    property var presentationStartWidth: []
    property var presentationStartProgress: []
    property var presentationStartChrome: []
    property var presentationStartCompactTitle: []
    property var presentationStartVisible: []
    property bool suppressTransitionCompletion: false
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

    function capturePresentation() {
        var startsX = []
        var startsWidth = []
        var startsProgress = []
        var startsChrome = []
        var startsCompactTitle = []
        var startsVisible = []
        for (var index = 0; index < recentGames.length; index++) {
            var card = recentRepeater.itemAt(index)
            startsX[index] = card ? card.x : railX(index - selectedIndex)
            startsWidth[index] = card ? card.width : railWidth(index - selectedIndex)
            startsProgress[index] = card ? card.presentationProgress
                                          : (index === selectedIndex ? 1 : 0)
            startsChrome[index] = card ? card.focalChromeOpacity
                                        : (index === selectedIndex ? 1 : 0)
            startsCompactTitle[index] = card ? card.compactTitleOpacity
                                              : (index === selectedIndex ? 0 : 1)
            startsVisible[index] = card ? card.visible : true
        }
        presentationStartX = startsX
        presentationStartWidth = startsWidth
        presentationStartProgress = startsProgress
        presentationStartChrome = startsChrome
        presentationStartCompactTitle = startsCompactTitle
        presentationStartVisible = startsVisible
        console.log("RECENT_RETARGET", "capture", "selected", selectedIndex,
                    "progress", transitionProgress, "x", startsX,
                    "width", startsWidth, "presentation", startsProgress,
                    "chrome", startsChrome, "compactTitle", startsCompactTitle)
    }

    function beginRetarget() {
        transitionFromIndex = selectedIndex
        console.log("RECENT_RETARGET", "target", selectedIndex,
                    "toX", recentGames.map(function(game, index) {
                        return railX(index - selectedIndex)
                    }), "toWidth", recentGames.map(function(game, index) {
                        return railWidth(index - selectedIndex)
                    }))
        suppressTransitionCompletion = true
        transitionAnimation.stop()
        suppressTransitionCompletion = false
        transitionProgress = 0
        transitionFadeProgress = 0
        transitionAnimation.start()
        fadeAnimation.restart()
    }

    Component.onCompleted: {
        transitionFromIndex = selectedIndex
        transitionProgress = 1
        transitionFadeProgress = 1
        transitionInitialized = true
        capturePresentation()
    }

    NumberAnimation {
        id: transitionAnimation
        target: recentHome
        property: "transitionProgress"
        to: 1
        duration: 500
        easing.type: Easing.OutQuint
        onStopped: {
            if (recentHome.suppressTransitionCompletion)
                return
            recentHome.transitionProgress = 1
            recentHome.transitionFadeProgress = 1
            recentHome.capturePresentation()
        }
    }

    NumberAnimation {
        id: fadeAnimation
        target: recentHome
        property: "transitionFadeProgress"
        to: 1
        duration: 300
        easing.type: Easing.Linear
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
            id: recentRepeater
            model: recentGames
            delegate: GameCard {
                required property int index
                required property var modelData
                readonly property int toRelativeIndex: index - recentHome.selectedIndex
                readonly property real railProgress: recentHome.transitionProgress
                readonly property real startX: recentHome.presentationStartX[index] || 0
                readonly property real startWidth: recentHome.presentationStartWidth[index] || 0
                readonly property real startProgress: recentHome.presentationStartProgress[index] || 0
                readonly property real startChrome: recentHome.presentationStartChrome[index] || 0
                readonly property real startCompactTitle: recentHome.presentationStartCompactTitle[index] || 0
                readonly property real targetProgress: index === recentHome.selectedIndex ? 1 : 0
                readonly property real blend: startProgress
                    + (targetProgress - startProgress) * railProgress
                game: modelData
                focused: index === recentHome.selectedIndex
                presentationProgress: blend
                compactEndpointWidth: recentHome.compactCardWidth
                focalChromeOpacity: startChrome
                    + ((index === recentHome.selectedIndex ? 1 : 0) - startChrome) * railProgress
                compactTitleOpacity: startCompactTitle
                    + ((index === recentHome.selectedIndex ? 0 : 1) - startCompactTitle) * railProgress
                presentationState: modelData.game_id === recentHome.selectedGameId ? "FOCUSED" : "COMPACT"
                liveSceneCoordinates: true
                opticsStage: blend > 0 ? 7 : -1
                 compact: presentationState === "COMPACT"
                 showAction: false
                 actionLabel: modelData.install_state === "available"
                     ? "Available to Download" : (modelData.provider === "steam-store"
                         ? "A  Open" : "A  Play")
                 homeCard: true
                canonicalTexture: recentHome.canonicalTexture
                canonicalCoordinateRoot: recentHome.canonicalCoordinateRoot
                canonicalSize: recentHome.canonicalSize
                focalScale: recentHome.focalScale
                uiScale: recentHome.uiScale
                typography: recentHome.typography
                luluPalette: recentHome.luluPalette
                  visible: recentHome.presentationStartVisible[index]
                      || Math.abs(toRelativeIndex) <= recentHome.visibleRailRadius
                  width: startWidth + (recentHome.railWidth(toRelativeIndex) - startWidth) * railProgress
                  height: focalCardHeight
                  x: startX + (recentHome.railX(toRelativeIndex) - startX) * railProgress

                MouseArea {
                    anchors.fill: parent
                    onClicked: launchRequested(modelData)
                }
            }
        }
    }
}
