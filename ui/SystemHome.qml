import QtQuick
import "MudosAssetCatalog.js" as MudosAssetCatalog

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
    property var presentationCoordinator
    property real categoryProgress: 1
    property bool categoryTransitioning: false
    property int categoryFrom: -1
    property int categoryTarget: -1
    property int categoryDirection: 1
    property real categoryMotionVelocity: 0
    property var selectionStart: []
    property var presentationStartX: []
    property real selectionProgress: 1
    property bool suppressSelectionCompletion: false
    signal openRequested(int index)
    readonly property bool selectionMotionActive: selectionAnimation.running

    function categoryArtwork(category) {
        return Qt.resolvedUrl(MudosAssetCatalog.systemArtwork(category))
    }

    function railX(relativeIndex) {
        return relativeIndex * (cardWidth + railGap)
    }

    function selectedOpacityOwner(index) {
        return index === selectedIndex
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
            depthDistance: Math.abs(index - root.selectedIndex)
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

             canonicalMappingDependency: ({
                 ownerX: root.x,
                 ownerY: root.y,
                 ownerScale: root.scale,
                 delegateX: x,
                delegateY: y,
                width: width,
                height: height,
                 selectionProgress: root.selectionProgress
             })
             categoryProgress: root.categoryProgress
             categoryTransitioning: root.categoryTransitioning
             categoryFrom: root.categoryFrom
             categoryTarget: root.categoryTarget
             categoryDirection: root.categoryDirection
             presentationAncestorY: root.parent ? root.parent.y : 0
             presentationAncestorScale: root.parent ? root.parent.scale : 1
            canonicalSize: root.canonicalSize
              motionBlurActive: root.selectionMotionActive
                  || root.categoryTransitioning
             motionStartX: startX
             motionTargetX: targetX
             motionProgress: root.selectionProgress
              motionBlurPixels: root.presentationCoordinator
                  ? root.presentationCoordinator.signedMotionBlurPixelsFromVelocity(
                      motionVelocity) : 0
              motionBlurVerticalPixels: root.presentationCoordinator
                  ? root.presentationCoordinator.signedMotionBlurPixelsFromVelocity(
                      root.categoryMotionVelocity) : 0
              motionBlurVector: root.presentationCoordinator
                  ? root.presentationCoordinator.signedMotionBlurVectorFromVelocity(
                      motionVelocity, root.categoryMotionVelocity)
                  : Qt.vector2d(0, 0)
             selectedOpacityOwner: root.selectedOpacityOwner(index)
             onActivated: root.openRequested(index)
        }
    }
}
