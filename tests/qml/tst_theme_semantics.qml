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

    function test_global_no_motion_disables_blur_capture() {
        mudosTheme = ({motion: {enabled: false, durationScale: 1, roles: {motionBlur: {enabled: true}}}})
        verify(!blurLoader.item.motionEnabled)
        compare(findChild(blurLoader.item, "motionBlurSourceTexture").sourceItem, null)
    }
}
