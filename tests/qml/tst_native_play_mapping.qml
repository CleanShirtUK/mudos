import QtQuick
import QtTest

TestCase {
    name: "NativePlayMapping"

    Item {
        id: card
        width: 720
        height: 520
        property real presentationProgress: 1
        property real focalChromeOpacity: 1
        property real focalScale: 1
        property real uiScale: 1

        Item {
            id: playButton
            x: 34
            y: 420
            width: 652
            height: 82
            scale: 1
        }

        readonly property rect nativePlayCanonicalRect: {
            var playDependency = playButton.x + playButton.y
                + playButton.width + playButton.height + playButton.scale
                + card.width + card.height + card.presentationProgress
                + card.focalChromeOpacity + card.focalScale + card.uiScale
            var dependency = playDependency
            var topLeft = playButton.mapToItem(card, 0, 0)
            var bottomRight = playButton.mapToItem(card,
                                                   playButton.width,
                                                   playButton.height)
            return Qt.rect(topLeft.x + dependency - dependency,
                           topLeft.y + dependency - dependency,
                           bottomRight.x - topLeft.x,
                           bottomRight.y - topLeft.y)
        }
    }

    function init() {
        card.width = 720
        card.height = 520
        card.presentationProgress = 1
        card.focalChromeOpacity = 1
        card.focalScale = 1
        card.uiScale = 1
        playButton.x = 34
        playButton.y = 420
        playButton.width = 652
        playButton.height = 82
        playButton.scale = 1
        wait(1)
    }

    function test_localPlayRegion() {
        var topLeft = playButton.mapToItem(card, 0, 0)
        var bottomRight = playButton.mapToItem(card,
                                               playButton.width,
                                               playButton.height)
        compare(card.nativePlayCanonicalRect.x, topLeft.x)
        compare(card.nativePlayCanonicalRect.y, topLeft.y)
        compare(card.nativePlayCanonicalRect.width, bottomRight.x - topLeft.x)
        compare(card.nativePlayCanonicalRect.height, bottomRight.y - topLeft.y)
    }

    function test_focalResizeAndInterpolation() {
        card.presentationProgress = 0.4
        card.focalChromeOpacity = 0.4
        card.width = 1080
        card.height = 680
        playButton.x = 50
        playButton.y = 548
        playButton.width = 980
        wait(10)
        var firstTopLeft = playButton.mapToItem(card, 0, 0)
        var firstBottomRight = playButton.mapToItem(card,
                                                    playButton.width,
                                                    playButton.height)
        compare(card.nativePlayCanonicalRect.x, firstTopLeft.x)
        compare(card.nativePlayCanonicalRect.y, firstTopLeft.y)
        compare(card.nativePlayCanonicalRect.width,
                firstBottomRight.x - firstTopLeft.x)

        card.presentationProgress = 0.9
        card.focalChromeOpacity = 0.9
        playButton.x = 30
        playButton.y = 470
        playButton.width = 1020
        wait(10)
        var secondTopLeft = playButton.mapToItem(card, 0, 0)
        var secondBottomRight = playButton.mapToItem(card,
                                                     playButton.width,
                                                     playButton.height)
        compare(card.nativePlayCanonicalRect.x, secondTopLeft.x)
        compare(card.nativePlayCanonicalRect.y, secondTopLeft.y)
        compare(card.nativePlayCanonicalRect.width,
                secondBottomRight.x - secondTopLeft.x)
    }

    function test_playMovementScaleAndRetarget() {
        playButton.x = 22
        playButton.y = 390
        playButton.scale = 0.97
        card.presentationProgress = 0.2
        wait(10)
        var firstOrigin = playButton.mapToItem(card, 0, 0)
        compare(card.nativePlayCanonicalRect.x, firstOrigin.x)
        compare(card.nativePlayCanonicalRect.y, firstOrigin.y)

        playButton.x = 68
        playButton.y = 444
        playButton.scale = 1.03
        card.presentationProgress = 0.8
        wait(10)
        var secondOrigin = playButton.mapToItem(card, 0, 0)
        compare(card.nativePlayCanonicalRect.x, secondOrigin.x)
        compare(card.nativePlayCanonicalRect.y, secondOrigin.y)
    }
}
