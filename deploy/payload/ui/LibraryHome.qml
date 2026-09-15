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
    readonly property string navigationObject: "library"
    readonly property bool selectionMotionActive: selectionAnimation.running
    signal openRequested(int index)

    function categoryArtwork(category) {
        var artwork = {
            "all": ["platform-all.svg", "icon"],
            "pc": ["platform-pc.png", "raster"],
            "platform:nes": ["platform-nes.png", "raster"],
            "platform:snes": ["platform-snes.png", "raster"],
            "platform:genesis": ["platform-genesis.png", "raster"],
            "platform:gb": ["platform-gb.png", "raster"],
            "platform:gbc": ["platform-gbc.png", "raster"],
            "platform:gba": ["platform-gba.png", "raster"],
            "platform:nds": ["platform-nds.png", "raster"],
            "platform:gamecube": ["platform-gamecube.png", "raster"],
            "platform:wii": ["platform-wii.png", "raster"],
            "platform:switch": ["platform-switch.png", "raster"],
            "platform:ps1": ["platform-ps1.png", "raster"],
            "platform:ps2": ["platform-ps2.png", "raster"],
            "platform:ps3": ["platform-ps3.png", "raster"]
        }
        return artwork[category] || artwork.all
    }

    function railX(relativeIndex) {
        return relativeIndex * (compactCardWidth + 18 * uiScale)
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
            artworkRole: libraryHome.categoryArtwork(modelData.scope)[1]
            artworkSource: Qt.resolvedUrl("artwork/" + libraryHome.categoryArtwork(modelData.scope)[0])
            uiScale: libraryHome.uiScale
            typography: libraryHome.typography
            luluPalette: libraryHome.luluPalette
            canonicalTexture: libraryHome.canonicalTexture
            canonicalCoordinateRoot: libraryHome.canonicalCoordinateRoot
             canonicalSize: libraryHome.canonicalSize
             motionBlurActive: libraryHome.selectionMotionActive
             motionStartX: startX
             motionTargetX: targetX
             motionProgress: libraryHome.selectionProgress
             motionBlurPixels: libraryHome.presentationCoordinator
                 ? libraryHome.presentationCoordinator.signedMotionBlurPixelsFromVelocity(
                     motionVelocity) : 0
             selectedOpacityOwner: libraryHome.selectedOpacityOwner(index)
             opacity: libraryHome.contentOpacity
            onActivated: libraryHome.openRequested(index)
        }
    }

}
