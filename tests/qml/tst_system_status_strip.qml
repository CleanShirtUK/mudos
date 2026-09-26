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
