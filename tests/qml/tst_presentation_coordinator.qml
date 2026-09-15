import QtQuick
import QtTest

TestCase {
    name: "PresentationCoordinator"

    Loader {
        id: coordinatorLoader
        source: Qt.resolvedUrl("../../ui/PresentationCoordinator.qml")
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
