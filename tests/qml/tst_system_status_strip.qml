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
                              batteryPercentage: 80}]
        wait(50)
        verify(strip.width > initial)
        compare(strip.x + strip.width, width)
        strip.controllers = []
        wait(50)
        compare(strip.width, initial)
    }
}
