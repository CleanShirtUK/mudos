import QtQuick
import QtTest
import "../../ui/MudosAssetCatalog.js" as Assets

TestCase {
    name: "AssetSystem"
    property var mudosTheme: ({
        activeId: "modern",
        iconUrl: function(name) { return activeId === "95" && name === "settings"
            ? Qt.resolvedUrl("../../themes/95/icons/settings.svg") : "" },
        colors: {primaryText: "#eadcff", backdrop: "#060607", surface: "#6b070809", border: "#665f68"},
        radii: {panel: 18, card: 10, row: 7, media: 14, status: 12, overlay: 14},
        glass: {enabled: true}, chrome: {style: "flat"},
        wallpaperShader: Qt.resolvedUrl("../../themes/modern/wallpaper/wallpaper.frag.qsb"),
        wallpaper: {primary: "#7aa2f7"},
        fonts: {
            regular: Qt.resolvedUrl("../../themes/modern/fonts/JetBrainsMonoNLNerdFont-Regular.ttf"),
            bold: Qt.resolvedUrl("../../themes/modern/fonts/JetBrainsMonoNLNerdFont-Bold.ttf"),
            heavy: Qt.resolvedUrl("../../themes/modern/fonts/JetBrainsMonoNLNerdFont-ExtraBold.ttf"),
            icons: Qt.resolvedUrl("../../themes/modern/fonts/JetBrainsMonoNLNerdFont-Regular.ttf"),
            controller: Qt.resolvedUrl("../../themes/modern/fonts/Config-Glyphs.otf"),
            roles: {interface: "regular", display: "heavy", majorHeading: "heavy", icon: "icons"}
        }
    })

    Loader {
        id: typographyLoader
        source: Qt.resolvedUrl("../../ui/Typography.qml")
    }

    Loader {
        id: controllerGlyphLoader
        source: Qt.resolvedUrl("../../ui/ControllerGlyph.qml")
    }
    Loader {
        id: iconLoader
        source: Qt.resolvedUrl("../../ui/MudosIcon.qml")
    }
    Loader {
        id: paletteLoader
        source: Qt.resolvedUrl("../../ui/LuluPalette.qml")
    }
    Loader {
        id: panelSurfaceLoader
        source: Qt.resolvedUrl("../../ui/MudosPanelSurface.qml")
        onLoaded: {
            item.width = 200
            item.height = 100
            item.luluPalette = paletteLoader.item
        }
    }

    function test_generic_theme_icon_component_loads() {
        compare(iconLoader.status, Loader.Ready)
    }

    function test_bundled_font_loads_with_runtime_family_name() {
        verify(typographyLoader.status === Loader.Ready)
        var typography = typographyLoader.item
        verify(typography.regularFont.status === FontLoader.Ready)
        verify(typography.boldFont.status === FontLoader.Ready)
        compare(typography.iconFamily, typography.regularFont.name)
        compare(typography.interfaceFamily, typography.regularFont.name)
    }

    function test_live_theme_font_and_icon_bindings_change() {
        verify(typographyLoader.status === Loader.Ready)
        var modernFamily = typographyLoader.item.interfaceFamily
        mudosTheme = ({
            activeId: "95",
            iconUrl: function(name) { return name === "settings"
                ? Qt.resolvedUrl("../../themes/95/icons/settings.svg") : "" },
            colors: {primaryText: "#000000", backdrop: "#008080", surface: "#C0C0C0", border: "#808080"},
            radii: {panel: 0, card: 0, row: 0, media: 0, status: 0, overlay: 0},
            glass: {enabled: false}, chrome: {style: "bevel", highlight: "#FFFFFF", light: "#DFDFDF", shadow: "#808080", darkShadow: "#000000", width: 2},
            wallpaperShader: Qt.resolvedUrl("../../themes/95/wallpaper/wallpaper.frag.qsb"),
            wallpaper: {primary: "#008080"},
            fonts: {
                regular: Qt.resolvedUrl("../../themes/95/fonts/LiberationSans-Regular.ttf"),
                bold: Qt.resolvedUrl("../../themes/95/fonts/LiberationSans-Bold.ttf"),
                heavy: Qt.resolvedUrl("../../themes/95/fonts/LiberationSans-Bold.ttf"),
                icons: Qt.resolvedUrl("../../themes/95/fonts/JetBrainsMonoNLNerdFont-Regular.ttf"),
                controller: Qt.resolvedUrl("../../themes/95/fonts/Config-Glyphs.otf"),
                roles: {interface: "regular", display: "bold", majorHeading: "bold", icon: "icons"}
            }
        })
        tryCompare(typographyLoader.item.regularFont, "status", FontLoader.Ready)
        tryVerify(function() { return typographyLoader.item.interfaceFamily !== modernFamily })
        compare(typographyLoader.item.iconFamily, typographyLoader.item.iconFont.name)
        compare(paletteLoader.item.primaryText, "#000000")
        compare(paletteLoader.item.backdrop, "#008080")
        compare(paletteLoader.item.radius("panel", 18), 0)
        compare(paletteLoader.item.bevelChrome, true)
        compare(panelSurfaceLoader.item.radius, 0)
        var glassItem = findChild(panelSurfaceLoader.item, "mudosPanelGlassItem")
        verify(glassItem !== null)
        compare(glassItem.visible, false)
        verify(String(mudosTheme.wallpaperShader).endsWith("/themes/95/wallpaper/wallpaper.frag.qsb"))
        iconLoader.item.name = "settings"
        tryCompare(iconLoader.item, "overrideUrl", Qt.resolvedUrl("../../themes/95/icons/settings.svg"))
        compare(mudosTheme.iconUrl("settings"), Qt.resolvedUrl("../../themes/95/icons/settings.svg"))
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
