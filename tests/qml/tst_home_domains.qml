import QtQuick
import QtTest
import "../../ui/HomeDomains.js" as HomeDomains

TestCase {
    name: "HomeDomains"

    function test_empty_recents_remove_the_bottom_domain() {
        compare(HomeDomains.categories(HomeDomains.recentVisible(0, false, 2, 2)),
                ["system", "store", "library"])
        compare(HomeDomains.clampSelection(3, 0), 2)
        compare(HomeDomains.clampSelection(1, 0), 1)
    }

    function test_recents_return_without_stealing_the_library_selection() {
        compare(HomeDomains.categories(HomeDomains.recentVisible(1, false, 2, 2)),
                ["system", "store", "library", "recent"])
        compare(HomeDomains.clampSelection(2, 1), 2)
        compare(HomeDomains.clampSelection(3, 1), 3)
    }

    function test_in_flight_hop_keeps_its_recent_domain_until_settled() {
        verify(HomeDomains.recentVisible(0, true, 3, 2))
        verify(HomeDomains.recentVisible(0, true, 2, 3))
        verify(!HomeDomains.recentVisible(0, false, 3, 2))
    }

    function test_empty_recent_startup_keeps_title_geometry_attached_to_domain() {
        compare(HomeDomains.titleRailY(480, 2, 84), 312)
        compare(HomeDomains.titleRailY(510, 2, 84), 342)
        compare(HomeDomains.titleRailY(510, 3, 84), 258)
    }

    function test_no_motion_navigation_settles_selection_title_and_transition_flag() {
        var state = HomeDomains.settleSelection(0, 3)
        compare(state.selectedIndex, 3)
        compare(state.progress, 1)
        verify(!state.transitioning)
        compare(HomeDomains.titleRailY(510, state.selectedIndex, 84), 258)
        compare(HomeDomains.settleSelection(3, 2).selectedIndex, 2)
    }
}
