import QtQuick
import QtTest
import "../../ui/HomeDomains.js" as HomeDomains

TestCase {
    name: "ThemeSemantics"
    property var mudosTheme: ({
        motion: {enabled: true, durationScale: 1,
            roles: {navigation: {enabled: true, duration: 250, easing: "outQuint"}}},
        labels: {home: {system: "System", store: "Store", library: "Library", recent: "Recent"}},
        textStyles: {homeTitle: {case: "upper", letterSpacing: 5}}
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
            labels: {home: {system: "System", store: "Store", library: "Library", recent: "Recent"}},
            textStyles: {homeTitle: {case: "upper", letterSpacing: 5}}})
        compare(textLoader.item.homeLabel("recent"), "Recent")
        compare(textLoader.item.homeTitle("recent"), "RECENT")
        compare(textLoader.item.homeTitleSpacing(2), 10)
    }

    function test_95_preserves_case_and_has_no_tracking_or_motion() {
        mudosTheme = ({motion: {enabled: false, durationScale: 1,
                roles: {navigation: {enabled: true, duration: 250, easing: "outQuint"}}},
            labels: {home: {recent: "Recent"}},
            textStyles: {homeTitle: {case: "preserve", letterSpacing: 0}}})
        compare(textLoader.item.homeLabel("recent"), "Recent")
        compare(textLoader.item.homeTitle("recent"), "Recent")
        compare(textLoader.item.homeTitleSpacing(3), 0)
        verify(!motionLoader.item.enabled("navigation"))
    }

    function test_custom_label_does_not_change_semantic_domain_or_selection() {
        mudosTheme = ({motion: {enabled: true, durationScale: 1, roles: {}},
            labels: {home: {recent: "Last Played"}},
            textStyles: {homeTitle: {case: "preserve", letterSpacing: 0}}})
        compare(textLoader.item.homeTitle("recent"), "Last Played")
        compare(HomeDomains.categories(true), ["system", "store", "library", "recent"])
        compare(HomeDomains.categories(true).indexOf("recent"), 3)
        compare(HomeDomains.clampSelection(3, 1), 3)
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
