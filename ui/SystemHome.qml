import QtQuick

Item {
    id: root
    property var categories: []
    property int selectedIndex: 0
    property real cardWidth: 248 * uiScale
    property real cardHeight: 170 * uiScale
    property real railGap: 18 * uiScale
    property real uiScale: 1
    property var typography
    property var luluPalette
    property var canonicalTexture
    property var canonicalCoordinateRoot
    property size canonicalSize: Qt.size(1280, 720)
    property var selectionStart: []
    property var presentationStartX: []
    property real selectionProgress: 1
    property bool suppressSelectionCompletion: false
    signal openRequested(int index)

    function categoryArtwork(category) {
        return Qt.resolvedUrl("artwork/system-" + category.toLowerCase() + ".svg")
    }

    function railX(relativeIndex) {
        return relativeIndex * (cardWidth + railGap)
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
        var nextIndex = Math.max(0, Math.min(categories.length - 1,
                                             selectedIndex + delta))
        if (nextIndex === selectedIndex)
            return
        captureSelection()
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
        target: root
        property: "selectionProgress"
        to: 1
        duration: 500
        easing.type: Easing.OutQuint
        onStopped: {
            if (root.suppressSelectionCompletion)
                return
            root.selectionProgress = 1
            root.captureSelection()
        }
    }

    Repeater {
        id: cardRepeater
        model: root.categories
        delegate: NavigationCard {
            required property int index
            required property string modelData
            readonly property real startX: root.presentationStartX[index] || 0
            readonly property real targetX: root.railX(index - root.selectedIndex)
            x: startX + (targetX - startX) * root.selectionProgress
            y: 0
            width: root.cardWidth
            height: root.cardHeight
            focused: index === root.selectedIndex
            selectionProgress: (root.selectionStart[index] || 0)
                + ((index === root.selectedIndex ? 1 : 0)
                   - (root.selectionStart[index] || 0)) * root.selectionProgress
            displayTitle: modelData
            symbolicArtwork: ""
            artworkSource: root.categoryArtwork(modelData)
            uiScale: root.uiScale
            typography: root.typography
            luluPalette: root.luluPalette
            canonicalTexture: root.canonicalTexture
            canonicalCoordinateRoot: root.canonicalCoordinateRoot
            canonicalSize: root.canonicalSize
            onActivated: root.openRequested(index)
        }
    }
}
