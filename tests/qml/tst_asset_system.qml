import QtQuick
import QtTest
import "../../ui/MudosAssetCatalog.js" as Assets

TestCase {
    name: "AssetSystem"

    Loader {
        id: typographyLoader
        source: Qt.resolvedUrl("../../ui/Typography.qml")
    }

    Loader {
        id: controllerGlyphLoader
        source: Qt.resolvedUrl("../../ui/ControllerGlyph.qml")
    }

    function test_bundled_font_loads_with_runtime_family_name() {
        verify(typographyLoader.status === Loader.Ready)
        var typography = typographyLoader.item
        verify(typography.regularFont.status === FontLoader.Ready)
        verify(typography.boldFont.status === FontLoader.Ready)
        compare(typography.iconFamily, typography.regularFont.name)
        compare(typography.interfaceFamily, typography.regularFont.name)
    }

    function test_controller_font_loads_with_config_family() {
        verify(controllerGlyphLoader.status === Loader.Ready)
        var glyph = controllerGlyphLoader.item
        verify(glyph.controllerFont.status === FontLoader.Ready)
        compare(glyph.controllerFont.name, "Config")
        compare(glyph.glyphText, "\u0100")
    }

    function test_home_library_dimensions_and_flathub_have_distinct_icons() {
        var modes = ["provider", "game_mode", "genre", "platform"]
        var expected = [Assets.icon("plug"), "\uf0c0", "\ueeb6", "\uf11b"]
        for (var i = 0; i < modes.length; ++i) {
            compare(Assets.libraryDimensionIcon(modes[i]), expected[i])
            verify(expected[i] !== Assets.icon("collection"))
            for (var j = 0; j < i; ++j)
                verify(expected[i] !== expected[j])
        }
        compare(Assets.storeIcon("flathub", "store"), "\uf324")
        compare(Assets.storeIcon("steam", "store"), Assets.icon("steam"))
        compare(Assets.storeIcon("custom", "store"), Assets.icon("fallback"))
    }
}
