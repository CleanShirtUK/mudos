import QtQuick
import QtTest
import "../../ui" as UI

TestCase {
    name: "Utilities"
    width: 1280
    height: 720
    when: windowShown

    UI.LuluPalette { id: palette }
    UI.Typography { id: typography }
    UI.UtilitiesHome {
        id: utilities
        width: 1280
        height: 720
        luluPalette: palette
        typography: typography
        expandedContentX: 40
        expandedContentY: 80
        expandedContentWidth: 1200
        expandedContentHeight: 560
        applications: [
            {name: "Example Graphics", ref: "app/org.example.Graphics/x86_64/stable",
             screenshots: [{url: "https://example.test/one.png"},
                           {url: "https://example.test/two.png"}]},
            {name: "Example Editor", ref: "app/org.example.Editor/x86_64/stable",
             screenshots: []}
        ]
    }

    function test_selection_launch_and_screenshot_navigation_are_controller_first() {
        utilities.applications = [
            {name: "Example Graphics", ref: "app/org.example.Graphics/x86_64/stable",
             screenshots: [{url: "https://example.test/one.png"},
                           {url: "https://example.test/two.png"}]},
            {name: "Example Editor", ref: "app/org.example.Editor/x86_64/stable",
             screenshots: []}
        ]
        utilities.selectedIndex = 0
        var launched = ""
        utilities.launchRequested.connect(function(ref) { launched = ref })
        compare(utilities.selectedApplication.name, "Example Graphics")
        compare(utilities.screenshots.length, 2)
        compare(utilities.selectedScreenshot.url, "https://example.test/one.png")
        var media = findChild(utilities, "utilitiesScreenshot")
        verify(media !== null)
        verify(media.width > 0 && media.height > 0)
        verify(Math.abs(media.width / media.height - 16 / 9) < 0.02)
        utilities.moveScreenshot(1)
        compare(utilities.selectedScreenshot.url, "https://example.test/two.png")
        utilities.move(1)
        compare(utilities.selectedApplication.name, "Example Editor")
        compare(utilities.screenshots.length, 0)
        utilities.moveScreenshot(1)
        compare(utilities.screenshotIndex, 0)
        utilities.activateSelected()
        compare(launched, "app/org.example.Editor/x86_64/stable")
        utilities.move(1)
        compare(utilities.selectedIndex, 1)
    }

    function test_empty_utility_inventory_has_graceful_message() {
        utilities.applications = []
        verify(utilities.selectedApplication === null)
        utilities.activateSelected()
    }

    function test_shell_geometry_and_hint_contract_are_exposed() {
        verify(findChild(utilities, "utilitiesGlassSubstrate") !== null)
        verify(findChild(utilities, "utilitiesApplicationRows") !== null)
        verify(utilities.controllerHints.some(function(hint) {
            return hint.action === "confirm" && hint.label === "Launch"
        }))
        verify(!utilities.controllerHints.some(function(hint) {
            return hint.label.indexOf("A ") === 0
        }))
    }
}
