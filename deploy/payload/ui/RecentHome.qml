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
    property var presentationCoordinator
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
    readonly property real rowRightEdge: {
        var rightEdge = 0
        for (var index = 0; index < recentRepeater.count; index++) {
            var relativeIndex = index - selectedIndex
            rightEdge = Math.max(rightEdge,
                                 railX(relativeIndex) + railWidth(relativeIndex))
        }
        return rightEdge
    }
    readonly property real rowLeftEdge: {
        var leftEdge = 0
        for (var index = 0; index < recentRepeater.count; index++) {
            var relativeIndex = index - selectedIndex
            leftEdge = Math.min(leftEdge, railX(relativeIndex))
        }
        return leftEdge
    }
    readonly property real motionBlurPadding: presentationCoordinator
        ? presentationCoordinator.motionBlurMaxPixels : 64
    readonly property real recentRowStartupX: presentationCoordinator
        ? presentationCoordinator.recentRowStartupX(rowRightEdge) : 0
    readonly property real presentationX: presentationCoordinator
        ? presentationCoordinator.recentRowPresentationX(rowRightEdge, width) : 0
    readonly property bool selectionMotionActive: transitionAnimation.running
    readonly property bool selectionBlurAllowed: presentationCoordinator
        ? presentationCoordinator.contentPresented : true

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

    function selectionProgressVelocityPxPerMs(progress) {
        var normalized = Math.max(0, Math.min(1, progress))
        return 5 * Math.pow(1 - normalized, 4) / transitionAnimation.duration
    }

    function selectedOpacityOwner(index) {
        return index === selectedIndex
    }

    function selectionCardVelocityAt(progress, startX, targetX) {
        return (targetX - startX)
            * selectionProgressVelocityPxPerMs(progress)
    }

    function selectionCardVelocityPxPerMs(startX, targetX) {
        if (!selectionMotionActive)
            return 0
        return selectionCardVelocityAt(transitionProgress, startX, targetX)
    }

    function selectionSignedBlurPixelsAt(progress, startX, targetX) {
        return presentationCoordinator
            ? presentationCoordinator.signedMotionBlurPixelsFromVelocity(
                selectionCardVelocityAt(progress, startX, targetX)) : 0
    }

    function selectionSignedBlurPixels(startX, targetX) {
        return selectionSignedBlurPixelsAt(transitionProgress, startX, targetX)
    }

    readonly property int selectionBlurSurfaceCount: {
        if (!selectionMotionActive || !selectionBlurAllowed)
            return 0
        var count = 0
        for (var index = 0; index < recentRepeater.count; index++) {
            var card = recentRepeater.itemAt(index)
            if (card && card.visible)
                count++
        }
        return count
    }

    function logSelectionMotionDiagnostic(label, cardId, startX, targetX,
                                          captureWidth, captureHeight) {
        var velocity = selectionCardVelocityPxPerMs(startX, targetX)
        console.log("RECENT_SELECTION_BLUR", label, "card", cardId,
                    "startX", startX, "targetX", targetX,
                    "displacement", targetX - startX,
                    "velocity", velocity,
                    "blur", selectionSignedBlurPixels(startX, targetX),
                    "capture", captureWidth, "x", captureHeight,
                    "activeSurfaces", selectionBlurSurfaceCount)
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
            id: recentRow
            y: 0
            width: parent.width
            height: parent.height
            x: recentHome.presentationX
            visible: recentModel && recentRepeater.count > 0

        Repeater {
            id: recentRepeater
            model: recentModel
            delegate: RecentCardPresentation {
                home: recentHome
                toRelativeIndex: index - recentHome.selectedIndex
                startX: recentHome.presentationStartX[index] || 0
                startWidth: recentHome.presentationStartWidth[index] || 0
                startProgress: recentHome.presentationStartProgress[index] || 0
                startChrome: recentHome.presentationStartChrome[index] || 0
                startCompactTitle: recentHome.presentationStartCompactTitle[index] || 0
                railProgress: recentHome.transitionProgress
                focused: index === recentHome.selectedIndex
                presentationState: game_id === recentHome.selectedGameId ? "FOCUSED" : "COMPACT"
                selectionBlurActive: recentHome.selectionMotionActive
                    && recentHome.selectionBlurAllowed
                playActivationSerial: recentHome.playActivationSerial
                canonicalTexture: recentHome.canonicalTexture
                canonicalCoordinateRoot: recentHome.canonicalCoordinateRoot
                canonicalSize: recentHome.canonicalSize
                focalCardWidth: recentHome.focalCardWidth
                focalCardHeight: recentHome.focalCardHeight
                compactCardWidth: recentHome.compactCardWidth
                focalScale: recentHome.focalScale
                uiScale: recentHome.uiScale
                typography: recentHome.typography
                luluPalette: recentHome.luluPalette
                visible: recentHome.presentationStartVisible[index]
                    || Math.abs(toRelativeIndex) <= recentHome.visibleRailRadius
                width: startWidth
                    + (recentHome.railWidth(toRelativeIndex) - startWidth) * railProgress
                height: focalCardHeight
                x: startX + (recentHome.railX(toRelativeIndex) - startX) * railProgress
            }
        }
    }

    // This is an output overlay only. recentRow remains the live logical
    // hierarchy and retains ownership of presentationX and delegate geometry.
    DirectionalMotionBlur {
        id: recentMotionBlur
        x: recentHome.presentationX + recentHome.rowLeftEdge
            - recentHome.motionBlurPadding
        y: -recentHome.motionBlurPadding
        width: recentHome.rowRightEdge - recentHome.rowLeftEdge
            + 2 * recentHome.motionBlurPadding
        height: recentHome.height + 2 * recentHome.motionBlurPadding
        visible: recentModel && recentRepeater.count > 0
        active: !recentHome.selectionMotionActive
        sourceItem: recentRow
        sourceRect: Qt.rect(recentHome.rowLeftEdge - recentHome.motionBlurPadding,
                            -recentHome.motionBlurPadding,
                            recentHome.rowRightEdge - recentHome.rowLeftEdge
                                + 2 * recentHome.motionBlurPadding,
                            recentHome.height + 2 * recentHome.motionBlurPadding)
        blurPixels: presentationCoordinator
            ? presentationCoordinator.recentSignedBlurPixels(rowRightEdge) : 0
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
