import QtQuick
import QtTest

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
}
