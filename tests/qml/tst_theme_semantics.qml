import QtQuick
import QtTest
import "../../ui/HomeDomains.js" as HomeDomains

TestCase {
    name: "ThemeSemantics"
    property var mudosTheme: ({
        motion: {enabled: true, durationScale: 1,
            roles: {navigation: {enabled: true, duration: 250, easing: "outQuint"}}},
        labels: {home: {system: "System", store: "Store", library: "Library", recent: "Recent"},
            views: {settings: "Settings", utilities: "Utilities", library: "Library", installable: "Installable", downloads: "Downloads"}},
        textStyles: {homeTitle: {case: "upper", letterSpacing: 5}, viewTitle: {case: "upper", letterSpacing: 5}}
    })
    Loader { id: textLoader; source: Qt.resolvedUrl("../../ui/ThemeText.qml") }
    Loader { id: motionLoader; source: Qt.resolvedUrl("../../ui/ThemeMotion.qml") }
    Loader { id: paletteLoader; active: false; source: Qt.resolvedUrl("../../ui/LuluPalette.qml") }
    Loader { id: typographyLoader; active: false; source: Qt.resolvedUrl("../../ui/Typography.qml") }
    Loader { id: coordinatorLoader; active: false; source: Qt.resolvedUrl("../../ui/PresentationCoordinator.qml") }
    Loader {
        id: iconLoader
        active: false
        source: Qt.resolvedUrl("../../ui/MudosIcon.qml")
        onLoaded: {
            item.name = "settings"
            item.iconSize = 24
            item.semanticColor = "#0088ff"
            item.typography = typographyLoader.item
        }
    }
    Item { id: blurSource; width: 40; height: 40 }
    Loader {
        id: blurLoader
        source: Qt.resolvedUrl("../../ui/DirectionalMotionBlur.qml")
        onLoaded: { item.sourceItem = blurSource; item.active = true }
    }

    function test_modern_home_label_and_title_style() {
        mudosTheme = ({motion: {enabled: true, durationScale: 1,
                roles: {navigation: {enabled: true, duration: 250, easing: "outQuint"}}},
            labels: {home: {system: "System", store: "Store", library: "Library", recent: "Recent"},
                views: {settings: "Settings", utilities: "Utilities", library: "Library", installable: "Installable", downloads: "Downloads"}},
            textStyles: {homeTitle: {case: "upper", letterSpacing: 5}, viewTitle: {case: "upper", letterSpacing: 5}}})
        compare(textLoader.item.homeLabel("recent"), "Recent")
        compare(textLoader.item.homeTitle("recent"), "RECENT")
        compare(textLoader.item.homeTitleSpacing(2), 10)
        compare(textLoader.item.viewLabel("utilities"), "Utilities")
        compare(textLoader.item.viewTitle("utilities"), "UTILITIES")
        compare(textLoader.item.viewTitle("settings"), "SETTINGS")
        compare(textLoader.item.viewTitle("library") + ": "
            + textLoader.item.format("Platform", "viewTitle"), "LIBRARY: PLATFORM")
        compare(textLoader.item.viewTitle("installable"), "INSTALLABLE")
        compare(textLoader.item.viewTitle("downloads"), "DOWNLOADS")
        compare(textLoader.item.letterSpacing("viewTitle", 1), 5)
    }

    function test_95_preserves_case_and_has_no_tracking_or_motion() {
        mudosTheme = ({motion: {enabled: false, durationScale: 1,
                roles: {navigation: {enabled: true, duration: 250, easing: "outQuint"}}},
            labels: {home: {recent: "Recent"}, views: {settings: "Settings", utilities: "Utilities",
                library: "Library", installable: "Installable", downloads: "Downloads"}},
            textStyles: {homeTitle: {case: "preserve", letterSpacing: 0}, viewTitle: {case: "preserve", letterSpacing: 0}}})
        compare(textLoader.item.homeLabel("recent"), "Recent")
        compare(textLoader.item.homeTitle("recent"), "Recent")
        compare(textLoader.item.homeTitleSpacing(3), 0)
        verify(!motionLoader.item.enabled("navigation"))
        compare(textLoader.item.viewTitle("utilities"), "Utilities")
        compare(textLoader.item.viewTitle("settings"), "Settings")
        compare(textLoader.item.viewTitle("library") + ": "
            + textLoader.item.format("Platform", "viewTitle"), "Library: Platform")
        compare(textLoader.item.letterSpacing("viewTitle", 3), 0)
    }

    function test_custom_label_does_not_change_semantic_domain_or_selection() {
        mudosTheme = ({motion: {enabled: true, durationScale: 1, roles: {}},
            labels: {home: {recent: "Last Played"}, views: {utilities: "Tools", library: "Archive"}},
            textStyles: {homeTitle: {case: "preserve", letterSpacing: 0}, viewTitle: {case: "preserve", letterSpacing: 0}}})
        compare(textLoader.item.homeTitle("recent"), "Last Played")
        compare(HomeDomains.categories(true), ["system", "store", "library", "recent"])
        compare(HomeDomains.categories(true).indexOf("recent"), 3)
        compare(HomeDomains.clampSelection(3, 1), 3)
        compare(textLoader.item.viewTitle("utilities"), "Tools")
        var activeSpace = "library"
        compare(textLoader.item.viewTitle("library"), "Archive")
        compare(activeSpace, "library")
    }

    function test_motion_role_override_and_duration_scale() {
        mudosTheme = ({motion: {enabled: true, durationScale: 0.5,
                roles: {navigation: {enabled: true, duration: 500, easing: "inOutCubic"}}}})
        verify(motionLoader.item.enabled("navigation"))
        compare(motionLoader.item.duration("navigation", 250), 250)
        compare(motionLoader.item.easing("navigation", "linear"), Easing.InOutCubic)
        mudosTheme.motion.enabled = false
        verify(!motionLoader.item.enabled("navigation"))
    }

    function test_exact_and_component_baseline_radius_policies_and_chrome() {
        mudosTheme = ({
            radiusPolicy: "componentBaseline",
            radii: {panel: 18, card: 10, row: 7, media: 14, status: 12, overlay: 14},
            chrome: {style: "flat"}, colors: ({}),
            motion: {enabled: true, durationScale: 1, roles: ({})}
        })
        paletteLoader.active = true
        compare(paletteLoader.item.radius("panel", 14), 14)
        compare(paletteLoader.item.radius("media", 9, 2), 9)
        verify(!paletteLoader.item.bevelChrome)

        mudosTheme = ({
            radiusPolicy: "exact",
            radii: {panel: 0, card: 0, row: 0, media: 0, status: 0, overlay: 0},
            chrome: {style: "bevel"}, colors: ({}),
            motion: {enabled: true, durationScale: 1, roles: ({})}
        })
        compare(paletteLoader.item.radius("panel", 14), 0)
        compare(paletteLoader.item.radius("row", 8), 0)
        verify(paletteLoader.item.bevelChrome)

        mudosTheme = ({
            radiusPolicy: "exact",
            radii: {panel: 3, card: 0, row: 1, media: 0, status: 0, overlay: 0},
            chrome: {style: "flat"}, colors: ({}),
            motion: {enabled: true, durationScale: 1, roles: ({})}
        })
        compare(paletteLoader.item.radius("panel", 14), 3)
        compare(paletteLoader.item.radius("row", 8, 2), 2)
        verify(!paletteLoader.item.bevelChrome)
        paletteLoader.active = false
    }

    function test_wallpaper_clock_is_independent_of_intro_and_switches_live() {
        mudosTheme = ({motion: {enabled: true, durationScale: 1,
            roles: {intro: {enabled: true}, wallpaper: {enabled: true, speed: 1}}}})
        coordinatorLoader.active = true
        tryCompare(coordinatorLoader.item, "ready", true)
        coordinatorLoader.item.contentState = "PRESENTED"
        tryCompare(coordinatorLoader.item, "wallpaperClockRunning", true)
        compare(coordinatorLoader.item.wallpaperClockSpeed, 1)
        var modernStart = coordinatorLoader.item.orbitBaseTime
        wait(150)
        verify(coordinatorLoader.item.orbitBaseTime > modernStart)

        mudosTheme = ({motion: {enabled: false, durationScale: 1,
            roles: {intro: {enabled: true}, wallpaper: {enabled: false, speed: 1}}}})
        tryCompare(coordinatorLoader.item, "wallpaperClockRunning", false)
        var ninetyFiveStoppedAt = coordinatorLoader.item.orbitBaseTime
        wait(150)
        compare(coordinatorLoader.item.orbitBaseTime, ninetyFiveStoppedAt)

        mudosTheme = ({motion: {enabled: true, durationScale: 0.72,
            roles: {intro: {enabled: true}, wallpaper: {enabled: true, speed: 1}}}})
        tryCompare(coordinatorLoader.item, "wallpaperClockRunning", true)
        compare(coordinatorLoader.item.wallpaperClockSpeed, 1)
        var metalheartStart = coordinatorLoader.item.orbitBaseTime
        wait(150)
        verify(coordinatorLoader.item.orbitBaseTime > metalheartStart)
        coordinatorLoader.active = false
    }

    function test_metalheart_theme_consumers_resolve_configured_roles() {
        var root = Qt.resolvedUrl("../../themes/metalheart/")
        mudosTheme = ({
            activeId: "metalheart",
            motion: {enabled: true, durationScale: 0.72,
                roles: {surface: {enabled: true, duration: 340, easing: "outQuint"}}},
            colors: {primaryText: "#E0E0E8", accent: "#0088FF", backdrop: "#050508",
                surface: "#D9141418", headingAccent: "#E0E0E8", border: "#B5606068"},
            chrome: {style: "flat"},
            radiusPolicy: "exact",
            radii: {panel: 0, card: 0, row: 0, media: 0, status: 0, overlay: 0},
            glass: {enabled: true, panel: {transmission: 0.86}},
            fonts: {
                regular: root + "fonts/ShareTechMono-Regular.ttf",
                bold: root + "fonts/ShareTechMono-Regular.ttf",
                heavy: root + "fonts/Oxanium-Variable.ttf",
                icons: root + "fonts/JetBrainsMonoNLNerdFont-Regular.ttf",
                roles: {interface: "regular", display: "heavy", majorHeading: "heavy", icon: "icons"}
            },
            labels: {home: {system: "SYSTEM", store: "ACQUIRE", library: "LIBRARY", recent: "RECENT"},
                views: {settings: "SETTINGS", utilities: "UTILITIES", library: "LIBRARY",
                    installable: "INSTALLABLE", downloads: "DOWNLOADS"}},
            textStyles: {homeTitle: {case: "preserve", letterSpacing: 1.25},
                viewTitle: {case: "preserve", letterSpacing: 1.25}},
            wallpaperShader: root + "wallpaper/wallpaper.frag.qsb",
            iconUrl: function(name) { return name === "settings" ? root + "icons/settings.svg" : "" }
        })
        paletteLoader.active = true
        typographyLoader.active = true
        iconLoader.active = true
        tryCompare(typographyLoader.item.regularFont, "status", FontLoader.Ready)
        tryCompare(typographyLoader.item.extraBoldFont, "status", FontLoader.Ready)
        compare(typographyLoader.item.interfaceFamily, typographyLoader.item.regularFont.name)
        compare(typographyLoader.item.displayFamily, typographyLoader.item.extraBoldFont.name)
        verify(typographyLoader.item.interfaceFamily !== typographyLoader.item.displayFamily)
        compare(paletteLoader.item.primaryText.toString().toLowerCase(), "#e0e0e8")
        compare(paletteLoader.item.accent.toString().toLowerCase(), "#0088ff")
        verify(!paletteLoader.item.bevelChrome)
        compare(paletteLoader.item.radius("panel", 14), 0)
        compare(mudosTheme.glass.panel.transmission, 0.86)
        compare(textLoader.item.homeLabel("store"), "ACQUIRE")
        compare(textLoader.item.homeTitle("store"), "ACQUIRE")
        compare(textLoader.item.homeTitleSpacing(1), 1.25)
        compare(motionLoader.item.duration("surface", 500), 244.8)
        compare(mudosTheme.wallpaperShader, root + "wallpaper/wallpaper.frag.qsb")
        compare(iconLoader.item.overrideUrl, root + "icons/settings.svg")
        iconLoader.active = false
        typographyLoader.active = false
        paletteLoader.active = false
    }

    function test_global_no_motion_disables_blur_capture() {
        mudosTheme = ({motion: {enabled: false, durationScale: 1, roles: {motionBlur: {enabled: true}}}})
        verify(!blurLoader.item.motionEnabled)
        compare(findChild(blurLoader.item, "motionBlurSourceTexture").sourceItem, null)
    }
}
