import QtQuick
import QtTest
import "../../ui" as UI
import "../../ui/MudosAssetCatalog.js" as Catalog

TestCase {
    name: "SettingsSpace"
    width: 1280
    height: 720
    when: windowShown

    UI.LuluPalette { id: palette }
    UI.SettingsSpace {
        id: settings
        width: 1240
        height: 560
        x: 20
        categories: Catalog.settingsCategories(
            ["System", "Display", "Audio", "Network", "Bluetooth", "Controllers", "Storage", "Utilities"])
        luluPalette: palette
        typography: QtObject {
            property string displayFamily: "sans-serif"
            property string interfaceFamily: "sans-serif"
            function size(_role, fallback) { return fallback }
        }
    }
    property string currentTarget: ""
    Connections {
        target: settings
        function onCategoryChanged(index) {
            currentTarget = settings.categories[index].target
        }
    }

    function test_category_model_uses_existing_targets_and_glyphs() {
        compare(settings.categories.length, 7)
        compare(settings.categories.map(function(item) { return item.target }).join(","),
                "Network,Bluetooth,Display,Audio,Controllers,Storage,System")
        verify(settings.categories.every(function(item) {
            return item.id.length > 0 && item.glyph.length > 0 && item.component.length > 0
        }))
        verify(settings.categories.every(function(item) { return item.target !== "Utilities" }))
    }

    function test_category_selection_and_panel_focus_are_independent() {
        compare(settings.selectedCategory, 0)
        compare(settings.activePanel, "categories")
        settings.moveCategory(1)
        compare(settings.selectedCategory, 1)
        compare(currentTarget, "Bluetooth")
        compare(settings.activePanel, "categories")
        settings.enterContent()
        compare(settings.activePanel, "content")
        settings.enterCategories()
        compare(settings.activePanel, "categories")
        compare(settings.selectedCategory, 1)
    }

    function test_two_panels_have_no_secondary_category_rail() {
        verify(findChild(settings, "settingsGlassSubstrate") !== null)
        verify(findChild(settings, "settingsCategoryPanel") !== null)
        verify(findChild(settings, "settingsContentPanel") !== null)
        verify(findChild(settings, "settingsContentHost") !== null)
        verify(findChild(settings, "settingsCategoryRow_0") !== null)
        verify(findChild(settings, "settingsCategoryRail") === null)
    }
}
