import QtQuick
import QtTest
import "../../ui/HomeDomains.js" as HomeDomains

TestCase {
    name: "HomeDomains"

    function test_empty_recents_remove_the_bottom_domain() {
        compare(HomeDomains.categories(HomeDomains.recentVisible(0, false, 2, 2)),
                ["System", "Store", "Library"])
        compare(HomeDomains.clampSelection(3, 0), 2)
        compare(HomeDomains.clampSelection(1, 0), 1)
    }

    function test_recents_return_without_stealing_the_library_selection() {
        compare(HomeDomains.categories(HomeDomains.recentVisible(1, false, 2, 2)),
                ["System", "Store", "Library", "Recent"])
        compare(HomeDomains.clampSelection(2, 1), 2)
        compare(HomeDomains.clampSelection(3, 1), 3)
    }

    function test_in_flight_hop_keeps_its_recent_domain_until_settled() {
        verify(HomeDomains.recentVisible(0, true, 3, 2))
        verify(HomeDomains.recentVisible(0, true, 2, 3))
        verify(!HomeDomains.recentVisible(0, false, 3, 2))
    }
}
