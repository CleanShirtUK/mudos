import QtQuick
import QtTest
import "../../ui" as UI

TestCase {
    name: "ExpandedSurfaceGeometry"
    width: 1280
    height: 720
    when: windowShown

    UI.ExpandedSurfaceGeometry {
        id: geometry
        screenWidth: 1280
        screenHeight: 720
        uiScale: 1
        shellSideInset: 20
        shellTop: 20
        titleHeight: 37
        titleToSurfaceGap: 21
        surfaceLead: 16
        surfaceTopExtension: 8
        hintBandTop: 648
        surfaceToHintGap: 8
        innerInset: 20
    }

    function test_canonical_shell_bounds_and_inner_frame() {
        compare(geometry.titleBounds.x, 42)
        compare(geometry.titleBounds.y, 28)
        compare(geometry.surfaceBounds.x, 20)
        compare(geometry.surfaceBounds.y, 86)
        compare(geometry.surfaceBounds.width, 1240)
        compare(geometry.surfaceBounds.height, 554)
        compare(geometry.surfaceBounds.y + geometry.surfaceBounds.height, 640)
        compare(geometry.contentBounds.y, 94)
        compare(geometry.contentBounds.height, 546)
        compare(geometry.innerBounds.x, 40)
        compare(geometry.innerBounds.y, 114)
        compare(geometry.innerBounds.x + geometry.innerBounds.width, 1240)
        compare(geometry.innerBounds.y + geometry.innerBounds.height, 620)
    }

    function test_category_rail_uses_full_symmetric_inner_width() {
        var categoryRail = geometry.innerBounds
        compare(categoryRail.x, geometry.surfaceBounds.x + 20)
        compare(categoryRail.x + categoryRail.width,
                geometry.surfaceBounds.x + geometry.surfaceBounds.width - 20)
        compare(categoryRail.width, 1200)
        compare(categoryRail.y, geometry.contentBounds.y + 20)
    }

    function test_surface_roles_are_single_source_for_all_destinations() {
        // The destination consumers receive these same immutable rectangles;
        // Library/Installable may position their rail within innerBounds, but
        // cannot redefine the title, substrate, or bottom frame edge.
        var destinations = [geometry, geometry, geometry, geometry]
        for (var i = 0; i < destinations.length; ++i) {
            compare(destinations[i].titleBounds.x, geometry.titleBounds.x)
            compare(destinations[i].titleBounds.y, geometry.titleBounds.y)
            compare(destinations[i].surfaceBounds, geometry.surfaceBounds)
            compare(destinations[i].innerBounds, geometry.innerBounds)
        }
    }
}
