import QtQuick
import QtTest

TestCase {
    name: "PresentationCoordinator"

    Loader {
        id: coordinatorLoader
        source: Qt.resolvedUrl("../../ui/PresentationCoordinator.qml")
    }

    Loader {
        id: recentHomeLoader
        source: Qt.resolvedUrl("../../ui/RecentHome.qml")
        onLoaded: {
            item.luluPalette = testPalette
            item.width = 1280
            item.height = 500
        }
    }

    QtObject {
        id: testPalette
        property color mutedText: "white"
    }

    property var coordinator: coordinatorLoader.item

    Item {
        id: recentRowViewport
        width: 1280
        height: 200

        Item {
            id: recentRow
            x: coordinator ? coordinator.recentRowPresentationX(600, recentRowViewport.width) : 0
            Repeater {
                id: recentRowRepeater
                model: [0, 1, 2]
                delegate: Rectangle {
                    required property int modelData
                    x: modelData * 200
                    width: 180
                    height: 100
                }
            }
        }
    }

    Item {
        id: blurGeometryHarness
        width: 800
        height: 300

        Item {
            id: logicalSource
            x: 120
            y: 40
            width: 400
            height: 180

            Rectangle {
                id: logicalCard
                x: 36
                y: 24
                width: 180
                height: 100
            }
        }

        Loader {
            id: blurLoader
            source: Qt.resolvedUrl("../../ui/DirectionalMotionBlur.qml")
            onLoaded: {
                item.sourceItem = logicalSource
                item.sourceRect = Qt.rect(-64, -64, 528, 308)
            }
        }
    }

    function test_starts_hidden_with_explicit_offscreen_geometry() {
        coordinator.startupClock = 0
        compare(coordinator.contentState, coordinator.hiddenState)
        verify(!coordinator.contentVisible)
        verify(coordinator.titleOffset(0, 52, 180) < 0)
        verify(coordinator.recentRowStartupX(1800) < -1800)
        verify(coordinator.recentRowPresentationX(1800, 1280) < -1800)
        verify(coordinator.hintsOffset() > 0)
    }

    function test_title_and_recent_envelopes_are_synchronized() {
        compare(coordinator.titleCount, 4)
        compare(coordinator.titleTrainDuration, 670)
        compare(coordinator.titleTrainCompletionAt, 780)
        compare(coordinator.cardStartAt, coordinator.titleStartAt)
        compare(coordinator.cardDuration, coordinator.titleTrainDuration)
        compare(coordinator.recentRowCompletionAt, 780)
        compare(coordinator.hintsCompletionAt, 1280)
        compare(coordinator.startupDuration, coordinator.hintsCompletionAt)
    }

    function test_final_geometry_returns_to_authoritative_layout() {
        coordinator.startupClock = coordinator.startupDuration
        compare(coordinator.titleOffset(0, 52, 180), 0)
        compare(coordinator.titleOffset(3, 52, 180), 0)
        compare(coordinator.recentRowPresentationX(1800, 1280), 0)
        compare(coordinator.hintsOffset(), 0)
        compare(coordinator.hintsOpacity(), 1)
    }

    function test_titles_have_individual_local_progress() {
        coordinator.startupClock = 300
        verify(coordinator.titleTravelProgress(0) > 0)
        verify(coordinator.titleTravelProgress(0) > coordinator.titleTravelProgress(1))
        verify(coordinator.titleTravelProgress(1) > coordinator.titleTravelProgress(2))
        verify(coordinator.titleTravelProgress(2) > coordinator.titleTravelProgress(3))
        verify(coordinator.titleTravelProgress(3) === 0)
    }

    function test_title_velocity_respects_stagger_and_turning_points() {
        var widths = [180, 140, 220, 160]
        for (var index = 0; index < coordinator.titleCount; index++) {
            var start = coordinator.titleStartAt + index * coordinator.titleStagger
            coordinator.startupClock = start - 1
            compare(coordinator.titleTravelVelocityAt(index), 0)
            compare(coordinator.titleSignedBlurPixels(index, 52, widths[index]), 0)

            coordinator.startupClock = start + 1
            verify(coordinator.titlePresentationVelocityPxPerMs(
                       index, 52, widths[index]) > 0)
            verify(coordinator.titleSignedBlurPixels(index, 52, widths[index]) > 0)

            coordinator.startupClock = start
                + coordinator.titleDuration * coordinator.titleApproachFraction
            verify(Math.abs(coordinator.titleTravelVelocityAt(index)) < 0.000001)
            verify(Math.abs(coordinator.titleSignedBlurPixels(
                        index, 52, widths[index])) < 0.000001)

            coordinator.startupClock = start + coordinator.titleDuration * 0.9
            verify(coordinator.titlePresentationVelocityPxPerMs(
                       index, 52, widths[index]) < 0)
            verify(coordinator.titleSignedBlurPixels(index, 52, widths[index]) < 0)

            coordinator.startupClock = start + coordinator.titleDuration
            compare(coordinator.titleTravelVelocityAt(index), 0)
            compare(coordinator.titlePresentationVelocityPxPerMs(
                        index, 52, widths[index]), 0)
            compare(coordinator.titleSignedBlurPixels(index, 52, widths[index]), 0)
            compare(coordinator.titleOffset(index, 52, widths[index]), 0)
        }
    }

    function test_title_velocity_is_independent_of_other_titles() {
        var index = 2
        var width = 220
        coordinator.startupClock = coordinator.titleStartAt
            + index * coordinator.titleStagger + 120
        var velocity = coordinator.titlePresentationVelocityPxPerMs(index, 52, width)
        var blur = coordinator.titleSignedBlurPixels(index, 52, width)
        coordinator.titleCount = 1
        compare(coordinator.titlePresentationVelocityPxPerMs(index, 52, width), velocity)
        compare(coordinator.titleSignedBlurPixels(index, 52, width), blur)
        coordinator.titleCount = 4
    }

    function test_title_startup_geometry_is_fully_offscreen_per_width() {
        var widths = [100, 240, 140, 200]
        for (var index = 0; index < widths.length; index++) {
            var restingLeft = 52
            var startup = coordinator.titleStartupTranslation(restingLeft, widths[index])
            verify(restingLeft + startup + widths[index]
                   <= -coordinator.titleStartupSafetyMargin)
            compare(coordinator.titleOffset(index, restingLeft, widths[index]), startup)
        }
    }

    function test_recent_row_is_rigid_and_entirely_offscreen_before_entrance() {
        coordinator.startupClock = 0
        compare(recentRowRepeater.count, 3)
        verify(recentRow.x + 600 < 0)
        compare(recentRowRepeater.itemAt(1).x - recentRowRepeater.itemAt(0).x, 200)
        compare(recentRowRepeater.itemAt(2).x - recentRowRepeater.itemAt(1).x, 200)
    }

    function test_recent_row_translation_preserves_relative_geometry() {
        coordinator.startupClock = coordinator.cardStartAt + 120
        var firstOffset = recentRowRepeater.itemAt(1).x - recentRowRepeater.itemAt(0).x
        var secondOffset = recentRowRepeater.itemAt(2).x - recentRowRepeater.itemAt(1).x
        compare(firstOffset, 200)
        compare(secondOffset, 200)
        coordinator.startupClock = coordinator.startupDuration
        compare(recentRow.x, 0)
    }

    function test_recent_row_curve_has_one_smooth_overshoot() {
        var boundary = 0.22
        var before = coordinator.recentRowProgressAt(boundary - 0.001, 1800)
        var after = coordinator.recentRowProgressAt(boundary + 0.001, 1800)
        verify(after > before)
        verify(Math.abs(coordinator.recentRowVelocityAt(boundary - 0.001, 1800)
                        - coordinator.recentRowVelocityAt(boundary + 0.001, 1800)) < 0.04)
        compare(coordinator.recentRowProgressAt(0, 1800), 0)
        compare(coordinator.recentRowProgressAt(1, 1800), 1)
        verify(coordinator.recentRowMaximumProgress(1800) > 1)
        verify(coordinator.recentRowOvershootTime(1800) > 0)
        verify(coordinator.recentRowOvershootTime(1800) < coordinator.cardDuration)
        coordinator.startupClock = coordinator.cardStartAt
            + coordinator.recentRowOvershootTime(1800)
        verify(Math.abs(coordinator.recentRowPresentationX(1800, 1280) - 40) < 0.01)
    }

    function test_recent_analytic_velocity_follows_signed_trajectory() {
        var rowEdge = 1800
        var turningPoint = coordinator.recentRowOvershootTime(rowEdge)
            / coordinator.cardDuration
        verify(coordinator.recentPresentationVelocityAt(0, rowEdge) > 0)
        verify(coordinator.recentPresentationVelocityAt(turningPoint, rowEdge) < 0.000001)
        verify(coordinator.recentPresentationVelocityAt(turningPoint, rowEdge) > -0.000001)
        verify(coordinator.recentPresentationVelocityAt(0.9, rowEdge) < 0)
        compare(coordinator.recentPresentationVelocityAt(1, rowEdge), 0)
        coordinator.startupClock = coordinator.cardStartAt
            + turningPoint * coordinator.cardDuration
        verify(Math.abs(coordinator.recentPresentationVelocityPxPerMs(rowEdge)) < 0.000001)
        coordinator.startupClock = coordinator.cardStartAt + coordinator.cardDuration
        compare(coordinator.recentPresentationVelocityPxPerMs(rowEdge), 0)
    }

    function test_recent_blur_mapping_preserves_sign_dead_zone_and_clamp() {
        compare(coordinator.recentSignedBlurPixelsFromVelocity(0), 0)
        compare(coordinator.recentSignedBlurPixelsFromVelocity(0.01), 0)
        verify(coordinator.recentSignedBlurPixelsFromVelocity(1) > 0)
        verify(coordinator.recentSignedBlurPixelsFromVelocity(-1) < 0)
        compare(coordinator.recentSignedBlurPixelsFromVelocity(100),
                coordinator.motionBlurMaxPixels)
        compare(coordinator.recentSignedBlurPixelsFromVelocity(-100),
                -coordinator.motionBlurMaxPixels)
    }

    function test_motion_blur_padding_does_not_move_source_geometry() {
        verify(blurLoader.item !== null)
        var before = logicalCard.mapToItem(blurGeometryHarness, 0, 0)
        blurLoader.item.sourceRect = Qt.rect(-64, -64, 528, 308)
        var padded = logicalCard.mapToItem(blurGeometryHarness, 0, 0)
        blurLoader.item.sourceRect = Qt.rect(-23, -17, 446, 220)
        var differentlyPadded = logicalCard.mapToItem(blurGeometryHarness, 0, 0)
        compare(before.x, padded.x)
        compare(before.y, padded.y)
        compare(before.x, differentlyPadded.x)
        compare(before.y, differentlyPadded.y)
        compare(logicalSource.x, 120)
        compare(logicalSource.y, 40)
        verify(blurLoader.item.sourceItem === logicalSource)
    }

    function test_recent_selection_velocity_is_per_card_and_rebases() {
        verify(recentHomeLoader.item !== null)
        var recent = recentHomeLoader.item
        var rightVelocity = recent.selectionCardVelocityAt(0, 760, 0)
        var leftVelocity = recent.selectionCardVelocityAt(0, 0, 760)
        compare(rightVelocity, -leftVelocity)
        verify(rightVelocity < 0)
        verify(recent.selectionCardVelocityAt(1, 760, 0) === 0)
        compare(recent.selectionSignedBlurPixelsAt(1, 760, 0), 0)

        var focal = recent.selectionCardVelocityAt(0.2, 760, 0)
        var compact = recent.selectionCardVelocityAt(0.2, 160, 0)
        verify(Math.abs(focal) > Math.abs(compact))

        // A retarget is a new segment from the captured current geometry; its
        // sign follows the new displacement rather than stale input direction.
        var rebasedRight = recent.selectionCardVelocityAt(0, 300, 80)
        var rebasedLeft = recent.selectionCardVelocityAt(0, 300, 520)
        verify(rebasedRight < 0)
        verify(rebasedLeft > 0)
        verify(rebasedRight !== rebasedLeft)
    }

    function test_presentation_state_boundaries_are_explicit() {
        coordinator.beginStartup()
        compare(coordinator.contentState, coordinator.transitioningInState)
        verify(!coordinator.contentVisible)
        coordinator.startupClock = coordinator.contentRevealAt
        verify(coordinator.contentVisible)
        coordinator.markContentPresented()
        verify(coordinator.contentPresented)
        coordinator.beginContentExit()
        verify(coordinator.contentTransitioning)
        coordinator.markContentHidden()
        verify(coordinator.contentHidden)
        verify(!coordinator.contentVisible)
    }
}
