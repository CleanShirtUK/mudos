import QtQuick

Item {
    id: libraryHome
    property real cardHeight: 0
    property var typography
    property var luluPalette
    property var canonicalTexture
    property var canonicalCoordinateRoot
    property size canonicalSize: Qt.size(1280, 720)
    property real compactCardWidth: 160 * uiScale
    property point allGamesSceneOrigin: Qt.point(0, 0)
    property string transitionState: "RESTING"
    property real transitionProgress: 0
    property bool transitionExpanding: true
    property real contentOpacity: 1
    property int selectedIndex: 0
    property var categories: [{"label": "All Games", "scope": "all"}, {"label": "Steam", "scope": "steam"}]
    property var selectionStart: [1, 0]
    property real selectionProgress: 1
    property var presentationStartX: [0, 178]
    property int transitionFromIndex: 0
    property bool suppressSelectionCompletion: false
    readonly property bool transitioning: transitionState === "ACTIVATING"

    property real uiScale: 1
    readonly property string navigationObject: "library"
    signal openRequested(int index)

    function platformArtwork(scope) {
        return scope === "steam"
            ? Qt.resolvedUrl("artwork/platform-steam.png")
            : Qt.resolvedUrl("artwork/platform-all.svg")
    }

    function railX(relativeIndex) {
        return relativeIndex * (compactCardWidth + 18 * uiScale)
    }

    function captureSelection() {
        var starts = []
        var startsX = []
        for (var index = 0; index < categories.length; index++) {
            var card = cardRepeater.itemAt(index)
            starts[index] = card ? card.selectionProgress : (index === selectedIndex ? 1 : 0)
            startsX[index] = card ? card.x : railX(index - selectedIndex)
        }
        selectionStart = starts
        presentationStartX = startsX
    }

    function moveSelection(delta) {
        var nextIndex = Math.max(0, Math.min(categories.length - 1, selectedIndex + delta))
        if (nextIndex === selectedIndex)
            return
        captureSelection()
        transitionFromIndex = selectedIndex
        selectedIndex = nextIndex
        suppressSelectionCompletion = true
        selectionAnimation.stop()
        suppressSelectionCompletion = false
        selectionProgress = 0
        selectionAnimation.start()
    }

    Component.onCompleted: captureSelection()

    NumberAnimation {
        id: selectionAnimation
        target: libraryHome
        property: "selectionProgress"
        to: 1
        duration: 500
        easing.type: Easing.OutQuint
        onStopped: {
            if (libraryHome.suppressSelectionCompletion)
                return
            libraryHome.selectionProgress = 1
            libraryHome.captureSelection()
        }
    }

    Repeater {
        id: cardRepeater
        model: libraryHome.categories // model: ["All Games", "Steam"]
        delegate: NavigationCard {
            required property int index
            required property var modelData
            readonly property real startX: libraryHome.presentationStartX[index] || 0
            readonly property real targetX: libraryHome.railX(index - libraryHome.selectedIndex)
            x: startX + (targetX - startX) * libraryHome.selectionProgress
            y: 0
            width: libraryHome.compactCardWidth
            height: libraryHome.cardHeight
            focused: index === libraryHome.selectedIndex
            selectionProgress: (libraryHome.selectionStart[index] || 0)
                + ((index === libraryHome.selectedIndex ? 1 : 0)
                   - (libraryHome.selectionStart[index] || 0)) * libraryHome.selectionProgress
            displayTitle: modelData.label
            symbolicArtwork: ""
            artworkRole: modelData.scope === "steam" ? "raster" : "icon"
            artworkSource: libraryHome.platformArtwork(modelData.scope)
            uiScale: libraryHome.uiScale
            typography: libraryHome.typography
            luluPalette: libraryHome.luluPalette
            canonicalTexture: libraryHome.canonicalTexture
            canonicalCoordinateRoot: libraryHome.canonicalCoordinateRoot
            canonicalSize: libraryHome.canonicalSize
            opacity: libraryHome.contentOpacity
            onActivated: libraryHome.openRequested(index)
        }
    }

    Timer {
        interval: 16
        running: libraryHome.visible
        repeat: true
        onTriggered: {
            var card = cardRepeater.itemAt(0)
            if (card)
                libraryHome.allGamesSceneOrigin = card.mapToItem(
                    libraryHome.canonicalCoordinateRoot, 0, 0)
        }
    }
}
