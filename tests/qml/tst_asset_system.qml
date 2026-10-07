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
        id: statusIconLoader
        source: Qt.resolvedUrl("../../ui/StatusGlyph.qml")
        onLoaded: {
            item.iconName = "settings"
            item.glyphColor = "#23aadd"
        }
    }
    Loader {
        id: metadataRowLoader
        source: Qt.resolvedUrl("../../ui/FocalMetadataRow.qml")
        onLoaded: {
            item.width = 180
            item.height = 24
            item.iconName = "settings"
            item.text = "Platform"
        }
    }
    Loader {
        id: paletteLoader
        source: Qt.resolvedUrl("../../ui/LuluPalette.qml")
        onItemChanged: if (item && panelSurfaceLoader.item)
            panelSurfaceLoader.item.luluPalette = item
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

    function test_svg_tint_png_original_and_fallback_switch_without_stale_effects() {
        function themeFor(id) {
            var theme = {
                activeId: id,
                colors: {primaryText: "#163b5e", secondaryText: "#355a72", mutedText: "#54788e",
                    selectedText: "#163b5e", accent: "#168be0", focusIndicator: "#168be0",
                    warning: "#d87918", backdrop: "#bfe8ff", surface: "#7feffbff",
                    surfaceElevated: "#a8d9f5ff", surfaceInternal: "#ddf3fcff",
                    cardSurface: "#83d9f5ff", focusedCardSurface: "#b945d8f2",
                    actionSurface: "#e8ffffff", actionText: "#163b5e", artworkSurface: "#cdeaf7ff",
                    border: "#7a74b8d4", focusBorder: "#168be0", overlayBackdrop: "#783b8cc0",
                    overlaySurface: "#edf2fbff", launchOverlaySurface: "#f2eef9ff", guideSurface: "#eaf3fcff",
                    guideBorder: "#7a74b8d4", guideItemSurface: "#d9eaf8ff", guideSelectedText: "#163b5e",
                    scrollFadeStart: "#00bfe8ff", scrollFadeEnd: "#e8bfe8ff", navigationText: "#163b5e",
                    headingAccent: "#07599d", selectionSurface: "#6145bee8", librarySurface: "#9ed9f5ff",
                    libraryCardSurface: "#95d9f5ff", libraryBorder: "#7a74b8d4", overlay: "#edf2fbff"},
                radii: {panel: 22, card: 16, row: 12, media: 16, status: 18, overlay: 22},
                glass: {enabled: true}, chrome: {style: "flat"},
                fonts: {
                    regular: Qt.resolvedUrl("../../themes/modern/fonts/JetBrainsMonoNLNerdFont-Regular.ttf"),
                    bold: Qt.resolvedUrl("../../themes/modern/fonts/JetBrainsMonoNLNerdFont-Bold.ttf"),
                    heavy: Qt.resolvedUrl("../../themes/modern/fonts/JetBrainsMonoNLNerdFont-ExtraBold.ttf"),
                    icons: Qt.resolvedUrl("../../themes/modern/fonts/JetBrainsMonoNLNerdFont-Regular.ttf"),
                    controller: Qt.resolvedUrl("../../themes/modern/fonts/Config-Glyphs.otf"),
                    roles: {interface: "regular", display: "heavy", majorHeading: "heavy", icon: "icons", controller: "controller"}
                }
            }
            if (id === "frutiger-aero") {
                theme.iconAsset = function(name) {
                    return name === "settings" ? {
                        url: Qt.resolvedUrl("../assets/full-colour-icon.png").toString(),
                        renderMode: "original", format: "png"
                    } : ({})
                }
            } else if (id === "metalheart") {
                theme.iconAsset = function(name) {
                    return name === "settings" ? {
                        url: Qt.resolvedUrl("../../themes/metalheart/icons/settings.svg").toString(),
                        renderMode: "tint", format: "svg"
                    } : ({})
                }
            } else {
                theme.iconAsset = function() { return ({}) }
            }
            return theme
        }

        mudosTheme = themeFor("frutiger-aero")
        iconLoader.item.name = "settings"
        statusIconLoader.item.iconName = "settings"
        metadataRowLoader.item.iconName = "settings"
        compare(iconLoader.item.renderMode, "original")
        compare(iconLoader.item.overrideUrl,
            Qt.resolvedUrl("../assets/full-colour-icon.png").toString())
        var original = findChild(iconLoader.item, "semanticOriginalImage")
        var tintEffect = findChild(iconLoader.item, "semanticTintEffect")
        verify(original !== null)
        verify(tintEffect !== null)
        compare(iconLoader.item.paintsOriginal, true)
        compare(iconLoader.item.appliesSemanticTint, false)
        compare(original.fillMode, Image.PreserveAspectFit)
        tryCompare(original, "status", Image.Ready)
        var statusOriginal = findChild(statusIconLoader.item, "statusOriginalImage")
        var statusTint = findChild(statusIconLoader.item, "statusTintEffect")
        verify(statusOriginal !== null)
        compare(statusIconLoader.item.paintsOriginal, true)
        compare(statusIconLoader.item.appliesSemanticTint, false)
        compare(statusOriginal.fillMode, Image.PreserveAspectFit)
        compare(statusOriginal.width, statusIconLoader.item.availablePaintedSize)
        var metadataGlyph = findChild(metadataRowLoader.item, "metadataStatusGlyph")
        verify(metadataGlyph !== null)
        compare(metadataGlyph.paintsOriginal, true)

        mudosTheme = themeFor("modern")
        compare(iconLoader.item.overrideUrl, "")
        compare(iconLoader.item.renderMode, "tint")
        compare(original.source, "")
        compare(iconLoader.item.appliesSemanticTint, false)
        compare(iconLoader.item.usesFallbackGlyph, true)
        compare(statusIconLoader.item.overrideUrl, "")
        compare(statusIconLoader.item.usesFallbackGlyph, true)

        mudosTheme = themeFor("metalheart")
        compare(iconLoader.item.renderMode, "tint")
        compare(iconLoader.item.appliesSemanticTint, true)
        compare(original.source, "")
        compare(statusIconLoader.item.appliesSemanticTint, true)
        compare(statusIconLoader.item.paintsOriginal, false)
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
