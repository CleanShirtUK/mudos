import QtQuick
import QtTest
import "../../ui"
import "../../ui/LibraryDimensions.js" as LibraryDimensions

TestCase {
    id: testCase
    name: "LibraryHomeLanding"

    property var expectedDimensions: LibraryDimensions.all
    property var landing: null

    QtObject {
        id: testPalette
        property color transparent: "transparent"
        property color cardSurface: "#202020"
        property color focusedCardSurface: "#303030"
        property color glassTint: "#404040"
        property color glassBorder: "#606060"
        property color focusIndicator: "#ffffff"
        property color artworkSurface: "#202020"
        property color primaryText: "#ffffff"
        property color secondaryText: "#cccccc"
        property color actionSurface: "#303030"
        property color actionText: "#ffffff"
        property color selectedText: "#ffffff"
        property color chromeLight: "#ffffff"
        property color chromeHighlight: "#dddddd"
        property color chromeShadow: "#333333"
        property color chromeDarkShadow: "#111111"
        property real chromeWidth: 0
        property bool bevelChrome: false
        function radius(_role, fallback) { return fallback }
        function material(_role) { return ({style: "solid"}) }
        function decorations(_role) { return ({}) }
        function role(_name, fallback) { return fallback }
    }

    QtObject {
        id: testTypography
        property string interfaceFamily: "sans-serif"
        property string displayFamily: "sans-serif"
        property string iconFamily: "sans-serif"
        property int displayWeight: Font.Bold
        function size(_role, fallback) { return fallback }
    }

    Component {
        id: landingComponent
        LibraryHome {
            width: 1100
            height: 240
            cardHeight: 200
            compactCardWidth: 180
            uiScale: 1
            luluPalette: testPalette
            typography: testTypography
            categories: testCase.expectedDimensions
        }
    }

    SignalSpy {
        id: openSpy
        target: testCase.landing
        signalName: "openRequested"
    }

    function init() {
        landing = landingComponent.createObject(null)
        verify(landing !== null)
        openSpy.clear()
    }

    function cleanup() {
        if (landing) {
            landing.destroy()
            landing = null
        }
    }

    function test_canonical_card_order_and_in_view_dimension_cycle() {
        compare(expectedDimensions.map(function(item) { return item.mode }),
                ["platform", "provider", "game_mode", "genre"])
        var current = "platform"
        var visited = []
        for (var i = 0; i < expectedDimensions.length; ++i) {
            current = LibraryDimensions.adjacent(current, 1)
            visited.push(current)
        }
        compare(visited, ["provider", "game_mode", "genre", "platform"])
        current = "platform"
        var reverse = []
        for (var j = 0; j < expectedDimensions.length; ++j) {
            current = LibraryDimensions.adjacent(current, -1)
            reverse.push(current)
        }
        compare(reverse, ["genre", "game_mode", "provider", "platform"])
    }

    function test_selection_activates_semantic_dimension_repeatedly() {
        var expected = ["platform", "provider", "game_mode", "genre",
                        "provider", "genre", "platform"]
        for (var i = 0; i < expected.length; ++i) {
            var target = expectedDimensions.findIndex(function(item) {
                return item.mode === expected[i]
            })
            landing.moveSelection(target - landing.selectedIndex)
            landing.finishSelectionMotion()
            landing.activateCategory(landing.selectedIndex)
            compare(openSpy.count, i + 1)
            compare(openSpy.signalArguments[i][0], expected[i])
            compare(landing.selectedIndex, target)
            compare(landing.categories.map(function(item) { return item.mode }),
                    ["platform", "provider", "game_mode", "genre"])
        }
    }

    function test_controller_confirmation_activates_selected_semantic_dimension() {
        var expected = ["platform", "provider", "game_mode", "genre"]
        for (var i = 0; i < expected.length; ++i) {
            landing.selectedIndex = i
            landing.activateSelected()
            compare(openSpy.count, i + 1)
            compare(openSpy.signalArguments[i][0], expected[i])
        }
    }

    function test_activation_ignores_invalid_positions_and_uses_category_identity() {
        landing.activateCategory(-1)
        landing.activateCategory(landing.categories.length)
        compare(openSpy.count, 0)
        landing.categories = [expectedDimensions[3], expectedDimensions[1],
                              expectedDimensions[0], expectedDimensions[2]]
        landing.selectedIndex = 0
        landing.activateCategory(landing.selectedIndex)
        compare(openSpy.count, 1)
        compare(openSpy.signalArguments[0][0], "genre")
    }
}
