import QtQuick
import QtTest
import "../../ui/RecentCaptureEnvelope.js" as RecentCaptureEnvelope

TestCase {
    name: "RecentCaptureEnvelope"

    function test_retargetCaptureContainsMovingRightmostCardAcrossTransition() {
        // Retarget right by one card. These are five cards from the old and
        // new logical rails; at p=0 the old rightmost card extends past the
        // target-only capture rectangle.
        var startX = [-356, -178, 0, 778, 956]
        var startWidth = [160, 160, 760, 160, 160]
        var targetX = [-534, -356, -178, 0, 778]
        var targetWidth = [160, 160, 160, 760, 160]
        var targetLeft = Math.min.apply(null, targetX)
        var targetRight = Math.max.apply(null, targetX.map(function(x, index) {
            return x + targetWidth[index]
        }))
        var effectPadding = 64

        for (var sample = 0; sample <= 4; sample++) {
            var progress = sample / 4
            var live = []
            for (var index = 0; index < startX.length; index++) {
                live.push({
                    x: startX[index] + (targetX[index] - startX[index]) * progress,
                    width: startWidth[index]
                        + (targetWidth[index] - startWidth[index]) * progress
                })
            }
            var envelope = RecentCaptureEnvelope.union(targetLeft, targetRight, live)
            var captureLeft = envelope.left - effectPadding
            var captureRight = envelope.right + effectPadding
            for (var card = 0; card < live.length; card++) {
                verify(captureLeft <= live[card].x - effectPadding,
                       "left capture missed card " + card + " at progress " + progress)
                verify(captureRight >= live[card].x + live[card].width + effectPadding,
                       "right capture missed card " + card + " at progress " + progress)
            }
        }

        compare(targetRight, 938)
        verify(startX[4] + startWidth[4] > targetRight,
               "fixture must exercise the live right-edge overflow")
    }
}
