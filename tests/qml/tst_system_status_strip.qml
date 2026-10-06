import QtQuick
import QtTest
import "../../ui" as UI

TestCase {
    name: "SystemStatusStrip"
    width: 1280
    height: 720
    when: windowShown

    UI.LuluPalette { id: palette }
    UI.Typography { id: typography }
    UI.SystemStatusStrip {
        id: strip
        anchors.right: parent.right
        anchors.top: parent.top
        controllers: []
        activeDownloadCount: 0
        luluPalette: palette
        typography: typography
    }

    function test_backing_grows_and_shrinks_without_moving_right_edge() {
        var backing = findChild(strip, "statusBacking")
        verify(backing !== null)
        var initial = strip.width
        verify(initial > 0)
        compare(backing.width, strip.width)
        compare(strip.x + strip.width, width)
        strip.activeDownloadCount = 2
        wait(260)
        verify(strip.width > initial)
        compare(backing.width, strip.width)
        compare(strip.x + strip.width, width)
        strip.activeDownloadCount = 0
        wait(260)
        compare(strip.width, initial)
        compare(strip.x + strip.width, width)
        strip.controllers = [{index: 1, batteryKind: "percent", battery: 80,
                              batteryPercentage: 80, identity: "fixture-pad"}]
        wait(260)
        compare(strip.presentedControllerCount, 1)
        verify(strip.width > initial)
        compare(strip.x + strip.width, width)
        var expanded = strip.width
        strip.controllers = []
        wait(50)
        verify(strip.width < expanded)
        verify(strip.width > initial)
        var leaving = findChild(strip, "controllerSlot")
        verify(leaving !== null)
        verify(leaving.opacity < 1)
        wait(260)
        compare(strip.presentedControllerCount, 0)
        compare(strip.width, initial)
        compare(strip.x + strip.width, width)
    }

    function test_disconnected_network_has_explicit_warning_glyph_without_geometry_shift() {
        var icon = findChild(strip, "networkIcon")
        verify(icon !== null)
        var disconnectedGlyph = icon.resolvedGlyph
        var disconnectedWidth = strip.width
        verify(disconnectedGlyph !== String.fromCodePoint(0xf1eb))
        compare(icon.glyphColor, palette.warning)
        strip.networkAvailable = true
        wait(220)
        compare(icon.resolvedGlyph, String.fromCodePoint(0xf1eb))
        compare(icon.glyphColor, strip.statusColor)
        compare(strip.x + strip.width, width)
        strip.networkAvailable = false
        wait(220)
        compare(icon.resolvedGlyph, disconnectedGlyph)
        compare(icon.glyphColor, palette.warning)
        compare(strip.x + strip.width, width)
        verify(disconnectedWidth > 0)
    }

    function test_bluetooth_indicator_distinguishes_unavailable_off_powered_and_connected() {
        var icon = findChild(strip, "bluetoothStatusIcon")
        verify(icon !== null)
        strip.bluetoothState = "unavailable"
        var offGlyph = icon.resolvedGlyph
        compare(icon.glyphColor, palette.secondaryText)
        strip.bluetoothState = "off"
        compare(icon.resolvedGlyph, offGlyph)
        compare(icon.glyphColor, palette.warning)
        strip.bluetoothState = "powered"
        verify(icon.resolvedGlyph !== offGlyph)
        compare(icon.glyphColor, strip.statusColor)
        strip.bluetoothState = "connected"
        compare(icon.glyphColor, palette.headingAccent)
    }

    function test_controller_reconnect_before_exit_finishes_preserves_single_slot() {
        strip.controllers = [{index: 1, identity: "same-pad", batteryKind: "unknown"}]
        wait(260)
        compare(strip.presentedControllerCount, 1)
        var connectedWidth = strip.width
        strip.controllers = []
        wait(70)
        strip.controllers = [{index: 1, identity: "same-pad", batteryKind: "unknown"}]
        wait(280)
        compare(strip.presentedControllerCount, 1)
        compare(strip.width, connectedWidth)
        compare(strip.x + strip.width, width)
        strip.controllers = []
        wait(300)
    }

    function test_controller_update_and_staggered_disconnection() {
        strip.controllers = [
            {index: 1, identity: "pad-one", batteryKind: "unknown"},
            {index: 2, identity: "pad-two", batteryKind: "unknown"}
        ]
        wait(260)
        compare(strip.presentedControllerCount, 2)
        var twoPads = strip.width
        strip.controllers = [
            {index: 1, identity: "pad-one", batteryKind: "percent",
             batteryPercentage: 50, battery: "50%"},
            {index: 2, identity: "pad-two", batteryKind: "unknown"}
        ]
        wait(260)
        verify(strip.width > twoPads)
        strip.controllers = [{index: 2, identity: "pad-two", batteryKind: "unknown"}]
        wait(70)
        compare(strip.presentedControllerCount, 2)
        strip.controllers = []
        wait(300)
        compare(strip.presentedControllerCount, 0)
        compare(strip.x + strip.width, width)
    }

    function test_leading_controller_glyph_painted_bounds_fit_clipped_slot() {
        strip.controllers = [{index: 1, identity: "glyph-fit-pad", batteryKind: "unknown"}]
        wait(260)
        var slot = findChild(strip, "controllerSlot")
        var glyph = findChild(strip, "controllerStatusGlyph")
        verify(slot !== null)
        verify(glyph !== null)
        verify(slot.clip)
        verify(glyph.fittedToWidth)

        var bounds = glyph.paintedBounds
        var epsilon = 0.01
        verify(bounds.x >= glyph.safeInset - epsilon)
        verify(bounds.y >= glyph.safeInset - epsilon)
        verify(bounds.x + bounds.width <= glyph.width - glyph.safeInset + epsilon)
        verify(bounds.y + bounds.height <= glyph.height - glyph.safeInset + epsilon)
    }

    function test_exit_deadlines_survive_frequent_snapshots_and_staggered_removals() {
        strip.controllers = [
            {index: 1, identity: "departing-pad", batteryKind: "unknown"},
            {index: 2, identity: "remaining-pad", batteryKind: "percent",
             batteryPercentage: 80, battery: "80%"}
        ]
        wait(260)
        strip.controllers = [{index: 2, identity: "remaining-pad", batteryKind: "percent",
                              batteryPercentage: 80, battery: "80%"}]
        for (var level of [79, 78, 77, 76]) {
            wait(90)
            strip.controllers = [{index: 2, identity: "remaining-pad", batteryKind: "percent",
                                  batteryPercentage: level, battery: level + "%"}]
        }
        compare(strip.presentedControllerCount, 1)
        compare(strip.x + strip.width, width)

        strip.controllers = [{index: 1, identity: "departing-pad", batteryKind: "unknown"},
                             {index: 2, identity: "remaining-pad", batteryKind: "unknown"}]
        wait(260)
        strip.controllers = [{index: 2, identity: "remaining-pad", batteryKind: "unknown"}]
        wait(160)
        strip.controllers = []
        wait(140)
        compare(strip.presentedControllerCount, 1)
        wait(160)
        compare(strip.presentedControllerCount, 0)
        compare(strip.x + strip.width, width)
    }
}
