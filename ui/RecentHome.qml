import QtQuick

Item {
    id: recentHome
    property var recentModel
    property int selectedIndex: 0
    property int transitionFromIndex: 0
    property real transitionProgress: 1
    property real transitionFadeProgress: 1
    property bool transitionInitialized: false
    property string selectedGameId: recentModel && selectedIndex >= 0
        ? String(recentModel.gameIdAt(selectedIndex)) : ""
    property string selectionAnchorId: ""
    property real focalCardWidth: 760
    property real focalCardHeight: 500
    property real focalScale: 1
    property int playActivationSerial: 0
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
    signal launchRequested(string gameId)
    signal selectionIndexRequested(int index)
    signal selectionGameChanged(string gameId)
    readonly property int itemCount: recentRepeater.count

    onSelectedIndexChanged: {
        if (recentModel && selectedIndex >= 0 && selectedIndex < recentRepeater.count
                && !selectionAnchorId) {
            selectedGameId = recentModel.gameIdAt(selectedIndex)
            selectionGameChanged(selectedGameId)
        }
    }

    function anchorSelection() {
        selectionAnchorId = selectedGameId
            || (recentModel && selectedIndex >= 0 ? recentModel.gameIdAt(selectedIndex) : "")
    }

    function restoreSelection() {
        if (!recentModel || !selectionAnchorId)
            return
        var index = recentModel.indexOfGame(selectionAnchorId)
        if (index < 0)
            index = Math.max(0, Math.min(selectedIndex, recentRepeater.count - 1))
        if (index !== selectedIndex)
            selectionIndexRequested(index)
        selectedGameId = index >= 0 ? recentModel.gameIdAt(index) : ""
        selectionGameChanged(selectedGameId)
        selectionAnchorId = ""
    }

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
        for (var index = 0; index < recentRepeater.count; index++) {
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
        var toX = []
        var toWidth = []
        for (var index = 0; index < recentRepeater.count; index++) {
            toX[index] = railX(index - selectedIndex)
            toWidth[index] = railWidth(index - selectedIndex)
        }
        console.log("RECENT_RETARGET", "target", selectedIndex,
                    "toX", toX, "toWidth", toWidth)
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
        visible: !recentModel || recentRepeater.count === 0
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
        visible: recentModel && recentRepeater.count > 0

        Repeater {
            id: recentRepeater
            model: recentModel
            delegate: GameCard {
                required property int index
                required property string game_id
                required property string provider
                required property string install_state
                required property var provider_id
                required property var title
                required property var platform
                required property var launchable
                required property var install_dir
                required property var artwork_url
                required property var artwork_suppressed
                required property var last_played
                required property var runtime
                required property var genres
                required property var local_multiplayer
                required property var online_multiplayer
                required property var game_mode
                required property var display_title_override
                required property var canonical_title
                required property var platform_label
                property var gameRecord: ({
                    game_id: game_id,
                    provider: provider,
                    provider_id: provider_id,
                    title: title,
                    platform: platform,
                    install_state: install_state,
                    launchable: launchable,
                    install_dir: install_dir,
                    artwork_url: artwork_url,
                    artwork_suppressed: artwork_suppressed,
                    last_played: last_played,
                    runtime: runtime,
                    genres: genres,
                    local_multiplayer: local_multiplayer,
                    online_multiplayer: online_multiplayer,
                    game_mode: game_mode,
                    display_title_override: display_title_override,
                    canonical_title: canonical_title,
                    platform_label: platform_label
                })
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
                  game: gameRecord
                  focused: index === recentHome.selectedIndex
                presentationProgress: blend
                compactEndpointWidth: recentHome.compactCardWidth
                focalChromeOpacity: startChrome
                    + ((index === recentHome.selectedIndex ? 1 : 0) - startChrome) * railProgress
                compactTitleOpacity: startCompactTitle
                    + ((index === recentHome.selectedIndex ? 0 : 1) - startCompactTitle) * railProgress
                 presentationState: game_id === recentHome.selectedGameId ? "FOCUSED" : "COMPACT"
                liveSceneCoordinates: true
                opticsStage: blend > 0 ? 7 : -1
                 compact: presentationState === "COMPACT"
                 showAction: false
                 actionLabel: install_state === "available"
                      ? "Available to Download" : (provider === "steam-store"
                         ? "A  Open" : "A  Play")
                 homeCard: true
                 playActivationSerial: recentHome.playActivationSerial
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
                    onClicked: launchRequested(game_id)
                }
            }
        }
    }

    Connections {
        target: recentHome.recentModel
        function onRowsAboutToBeInserted() { recentHome.anchorSelection() }
        function onRowsAboutToBeRemoved() { recentHome.anchorSelection() }
        function onRowsAboutToBeMoved() { recentHome.anchorSelection() }
        function onRowsInserted() { recentHome.restoreSelection() }
        function onRowsRemoved() { recentHome.restoreSelection() }
        function onRowsMoved() { recentHome.restoreSelection() }
        function onModelReset() {
            recentHome.anchorSelection()
            recentHome.restoreSelection()
        }
    }
}
