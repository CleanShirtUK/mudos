import QtQuick
import QtTest
import "../../ui/LibrarySpatialGeometry.js" as SpatialGeometry
import "../../ui/LibrarySurfaceTransition.js" as SurfaceTransition

TestCase {
    name: "LibraryNoMotionTransition"
    property var mudosTheme: ({motion: {enabled: false, durationScale: 1, roles: {}}})
    readonly property var homeBounds: ({x: 96, y: 310, width: 420, height: 250})
    readonly property var expandedBounds: ({x: 20, y: 86, width: 1240, height: 554})

    function spatialBounds(progress) {
        return SpatialGeometry.bounds(progress,
            homeBounds.x, homeBounds.y, homeBounds.width, homeBounds.height,
            expandedBounds.x, expandedBounds.y,
            expandedBounds.width, expandedBounds.height, false)
    }

    function test_no_motion_open_library_settles_to_full_surface_geometry() {
        verify(!mudosTheme.motion.enabled)
        var state = SurfaceTransition.completedState(true, "library")
        compare(state.progress, 1)
        compare(state.space, "library")
        verify(!state.libraryTransitioning)
        verify(!state.storeTransitioning)
        compare(state.contentOpacity, 1)
        var bounds = spatialBounds(state.progress)
        compare(bounds.x, expandedBounds.x)
        compare(bounds.y, expandedBounds.y)
        compare(bounds.width, expandedBounds.width)
        compare(bounds.height, expandedBounds.height)
    }

    function test_no_motion_open_installable_settles_to_full_surface_geometry() {
        var state = SurfaceTransition.completedState(true, "store")
        compare(state.progress, 1)
        compare(state.space, "store")
        verify(!state.libraryTransitioning)
        verify(!state.storeTransitioning)
        compare(state.contentOpacity, 1)
        var bounds = spatialBounds(state.progress)
        compare(bounds.x, expandedBounds.x)
        compare(bounds.y, expandedBounds.y)
        compare(bounds.width, expandedBounds.width)
        compare(bounds.height, expandedBounds.height)
    }

    function test_no_motion_back_from_both_destinations_settles_to_home_bounds() {
        var destinations = ["library", "store"]
        for (var i = 0; i < destinations.length; ++i) {
            var state = SurfaceTransition.completedState(false, destinations[i])
            compare(state.progress, 0)
            compare(state.space, "home")
            verify(!state.libraryTransitioning)
            verify(!state.storeTransitioning)
            compare(state.contentOpacity, 0)
            verify(state.handoffPending)
            var bounds = spatialBounds(state.progress)
            compare(bounds.x, homeBounds.x)
            compare(bounds.y, homeBounds.y)
            compare(bounds.width, homeBounds.width)
            compare(bounds.height, homeBounds.height)
        }
    }
}
