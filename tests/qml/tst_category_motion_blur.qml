import QtQuick
import QtTest

TestCase {
    name: "CategoryMotionBlur"

    Loader {
        id: coordinatorLoader
        source: Qt.resolvedUrl("../../ui/PresentationCoordinator.qml")
    }

    property var coordinator: coordinatorLoader.item

    function initTestCase() {
        wait(0)
        verify(coordinator !== null)
    }

    function test_outQuintDerivativeAndTerminalZero() {
        var duration = 250
        compare(coordinator.easeOutQuintProgressVelocity(0, duration), 5 / duration)
        compare(coordinator.easeOutQuintProgressVelocity(0.5, duration),
                5 * Math.pow(0.5, 4) / duration)
        compare(coordinator.easeOutQuintProgressVelocity(1, duration), 0)
    }

    function test_verticalVelocitySignAndMagnitude() {
        var progress = 0.25
        var travel = 1188
        var duration = 250
        var expected = travel * 5 * Math.pow(1 - progress, 4) / duration
        compare(coordinator.categoryPresentationVelocity(
                    progress, 1, travel, duration), expected)
        compare(coordinator.categoryPresentationVelocity(
                    progress, -1, travel, duration), -expected)
        compare(coordinator.categoryPresentationVelocity(
                    1, 1, travel, duration), 0)
    }

    function test_signedVerticalBlurAndHorizontalCompatibility() {
        var positive = coordinator.signedMotionBlurPixelsFromVelocity(1.2)
        var negative = coordinator.signedMotionBlurPixelsFromVelocity(-1.2)
        verify(positive > 0)
        verify(negative < 0)
        compare(coordinator.signedMotionBlurPixelsFromVelocity(0), 0)
    }

    function test_gammaResponseKeepsModerateVelocityVisible() {
        var blur = coordinator.signedMotionBlurPixelsFromVelocity(1.44)
        var expected = 64 * Math.sqrt((1.44 * 8) / 64)
        verify(Math.abs(blur - expected) < 0.000001)
        compare(coordinator.signedMotionBlurPixelsFromVelocity(100), 64)
        compare(coordinator.signedMotionBlurPixelsFromVelocity(-100), -64)
        compare(coordinator.signedMotionBlurPixelsFromVelocity(0), 0)
    }

    function test_vectorResponsePreservesDirectionAndSupportsDiagonalMotion() {
        var vector = coordinator.signedMotionBlurVectorFromVelocity(3, 4)
        var magnitude = Math.sqrt(vector.x * vector.x + vector.y * vector.y)
        var expected = 64 * Math.sqrt((5 * 8) / 64)
        verify(Math.abs(magnitude - expected) < 0.000001)
        verify(Math.abs(vector.x / vector.y - 3 / 4) < 0.000001)
        verify(coordinator.signedMotionBlurVectorFromVelocity(0, 0).x === 0)
        verify(coordinator.signedMotionBlurVectorFromVelocity(0, 0).y === 0)
        verify(coordinator.signedMotionBlurVectorFromVelocity(0, -4).y < 0)
    }

    function test_chainedDurationAndSettlementRemainExact() {
        var atStart = coordinator.categoryPresentationVelocity(0, 1, 1152, 100)
        var requested = coordinator.signedMotionBlurPixelsFromVelocity(atStart)
        compare(requested, 64)
        compare(coordinator.signedMotionBlurPixelsFromVelocity(
                    coordinator.categoryPresentationVelocity(1, 1, 1152, 100)), 0)
    }

    function test_capturePaddingDoesNotChangeCanonicalGeometry() {
        var sourceRoot = Qt.createQmlObject(
            'import QtQuick; Item { width: 1920; height: 1080 }', this)
        var card = Qt.createQmlObject(
            'import QtQuick; Item { x: 78; y: 472.68; width: 239.27; height: 385.92 }',
            sourceRoot)
        var topLeft = card.mapToItem(sourceRoot, 0, 0)
        var bottomRight = card.mapToItem(sourceRoot, card.width, card.height)
        var padding = 64
        compare(topLeft.y, 472.68)
        compare(bottomRight.y - topLeft.y, 385.92)
        compare(-padding, -64)
        compare(card.y, 472.68)
        card.destroy()
        sourceRoot.destroy()
    }
}
