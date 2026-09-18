import QtQuick
import "SpatialDepth.js" as SpatialDepth
import "MudosAssetCatalog.js" as MudosAssetCatalog

Item {
    id: libraryHome
    property real cardHeight: 0
    property var typography
    property var luluPalette
    property var canonicalTexture
    property var canonicalCoordinateRoot
    property size canonicalSize: Qt.size(1280, 720)
    property real compactCardWidth: 160 * uiScale
    property string transitionState: "RESTING"
    property real transitionProgress: 0
    property bool transitionExpanding: true
    property real contentOpacity: 1
    property int selectedIndex: 0
    property var categories: [{"label": "All Games", "scope": "all"}, {"label": "PC Games", "scope": "pc"}]
    property var selectionStart: [1, 0]
    property real selectionProgress: 1
    property var presentationStartX: [0, 178]
    property int transitionFromIndex: 0
    property bool suppressSelectionCompletion: false
    readonly property bool transitioning: transitionState === "ACTIVATING"

    property real uiScale: 1
    property var presentationCoordinator
    property real categoryProgress: 1
    property bool categoryTransitioning: false
    property int categoryFrom: -1
    property int categoryTarget: -1
    property int categoryDirection: 1
    property real categoryMotionVelocity: 0
    readonly property string navigationObject: "library"
    readonly property bool selectionMotionActive: selectionAnimation.running
    signal openRequested(int index)

    function categoryArtwork(category) {
        return MudosAssetCatalog.libraryPlatformArtwork(category)
    }

    function railX(relativeIndex) {
        return relativeIndex * (compactCardWidth + 18 * uiScale)
    }

    function visualRailX(relativeIndex) {
        return SpatialDepth.projectedXForRelativeIndex(relativeIndex,
            compactCardWidth, compactCardWidth, 18 * uiScale)
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
            startsX[index] = card ? card.x : visualRailX(index - selectedIndex)
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
        model: libraryHome.categories
        delegate: NavigationCard {
            required property int index
            required property var modelData
            readonly property real startX: libraryHome.presentationStartX[index] || 0
            readonly property real targetX: libraryHome.visualRailX(index - libraryHome.selectedIndex)
            x: startX + (targetX - startX) * libraryHome.selectionProgress
            y: 0
            width: libraryHome.compactCardWidth
            height: libraryHome.cardHeight
            focused: index === libraryHome.selectedIndex
            depthDistance: Math.abs(index - libraryHome.selectedIndex)
            selectionProgress: (libraryHome.selectionStart[index] || 0)
                + ((index === libraryHome.selectedIndex ? 1 : 0)
                   - (libraryHome.selectionStart[index] || 0)) * libraryHome.selectionProgress
            displayTitle: modelData.label
            symbolicArtwork: ""
            artworkRole: libraryHome.categoryArtwork(modelData.scope)[1]
            artworkSource: Qt.resolvedUrl("artwork/" + libraryHome.categoryArtwork(modelData.scope)[0])
            uiScale: libraryHome.uiScale
            typography: libraryHome.typography
            luluPalette: libraryHome.luluPalette
             canonicalTexture: libraryHome.canonicalTexture
             canonicalCoordinateRoot: libraryHome.canonicalCoordinateRoot

              canonicalMappingDependency: ({
                  ownerX: libraryHome.x,
                   ownerY: libraryHome.y,
                   ownerScale: libraryHome.scale,
                   delegateX: x,
                 delegateY: y,
                 width: width,
                 height: height,
                  selectionProgress: libraryHome.selectionProgress
              })
              categoryProgress: libraryHome.categoryProgress
              categoryTransitioning: libraryHome.categoryTransitioning
              categoryFrom: libraryHome.categoryFrom
              categoryTarget: libraryHome.categoryTarget
              categoryDirection: libraryHome.categoryDirection
              presentationAncestorY: libraryHome.parent ? libraryHome.parent.y : 0
              presentationAncestorScale: libraryHome.parent ? libraryHome.parent.scale : 1
             canonicalSize: libraryHome.canonicalSize
             motionBlurActive: libraryHome.selectionMotionActive
                 || libraryHome.categoryTransitioning
             motionStartX: startX
             motionTargetX: targetX
             motionProgress: libraryHome.selectionProgress
              motionBlurPixels: libraryHome.presentationCoordinator
                  ? libraryHome.presentationCoordinator.signedMotionBlurPixelsFromVelocity(
                      motionVelocity) : 0
              motionBlurVerticalPixels: libraryHome.presentationCoordinator
                  ? libraryHome.presentationCoordinator.signedMotionBlurPixelsFromVelocity(
                      libraryHome.categoryMotionVelocity) : 0
              motionBlurVector: libraryHome.presentationCoordinator
                  ? libraryHome.presentationCoordinator.signedMotionBlurVectorFromVelocity(
                      motionVelocity, libraryHome.categoryMotionVelocity)
                  : Qt.vector2d(0, 0)
             selectedOpacityOwner: libraryHome.selectedOpacityOwner(index)
             opacity: libraryHome.contentOpacity
            onActivated: libraryHome.openRequested(index)
        }
    }

}
