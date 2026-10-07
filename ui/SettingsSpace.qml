pragma ComponentBehavior: Bound
import QtQuick

// Unified Settings navigation and panel chrome. Category content remains
// owned by the existing category-specific components hosted in contentHost.
Item {
    id: root
    ThemeMotion { id: themeMotion }
    property var categories: []
    property int selectedCategory: 0
    property string activePanel: "categories"
    property real uiScale: 1
    property var typography
    property var luluPalette
    property var canonicalTexture
    property var canonicalCoordinateRoot
    property size canonicalSize: Qt.size(1280, 720)
    property real leftWidth: Math.max(280 * uiScale, width * 0.29)
    readonly property real panelGap: 18 * uiScale
    property real innerInset: 20 * uiScale
    property real surfaceTopExtension: 8 * uiScale
    readonly property real panelInset: innerInset
    readonly property rect internalFrameBounds: Qt.rect(innerInset, innerInset,
        Math.max(0, width - 2 * innerInset),
        Math.max(0, height - 2 * innerInset))
    readonly property rect leftBounds: Qt.rect(panelInset, panelInset,
        leftWidth - panelGap / 2 - panelInset,
        Math.max(0, height - 2 * panelInset))
    readonly property rect rightBounds: Qt.rect(leftWidth + panelGap / 2, panelInset,
        width - leftWidth - panelGap / 2 - panelInset,
        Math.max(0, height - 2 * panelInset))
    property alias contentHost: host
    signal categoryChanged(int index)
    signal panelFocusRequested(string panel)

    function moveCategory(delta) {
        if (!categories.length) return
        selectedCategory = Math.max(0, Math.min(categories.length - 1,
                                                  selectedCategory + delta))
        categoryChanged(selectedCategory)
    }
    function enterContent() {
        activePanel = "content"
        panelFocusRequested("content")
    }
    function enterCategories() {
        activePanel = "categories"
        panelFocusRequested("categories")
    }

    MudosPanelSurface {
        objectName: "settingsGlassSubstrate"
        x: 0; y: -root.surfaceTopExtension
        width: root.width; height: root.height + root.surfaceTopExtension
        cornerRadius: root.luluPalette.radius("panel", 18) * root.uiScale
        uiScale: root.uiScale
        luluPalette: root.luluPalette
        canonicalTexture: root.canonicalTexture
        canonicalCoordinateRoot: root.canonicalCoordinateRoot
        canonicalSize: root.canonicalSize
        mappingItem: root
    }
    Rectangle {
        objectName: "settingsCategoryPanel"
        x: root.leftBounds.x; y: root.leftBounds.y
        width: root.leftBounds.width; height: root.leftBounds.height
        radius: root.luluPalette.radius("panel", 14) * root.uiScale
        color: root.luluPalette.cardSurface
        border.width: root.activePanel === "categories" ? 3 * root.uiScale : 1 * root.uiScale
        border.color: root.activePanel === "categories"
            ? root.luluPalette.focusIndicator : root.luluPalette.glassBorder
        opacity: root.activePanel === "categories" ? 1 : 0.72
        MudosChromeFrame {
            anchors.fill: parent
            luluPalette: root.luluPalette
            uiScale: root.uiScale
            cornerRadius: parent.radius
            raised: root.activePanel === "categories"
        }
        Behavior on border.color { enabled: themeMotion.enabled("overlay"); ColorAnimation { duration: themeMotion.duration("overlay", 180); easing.type: themeMotion.easing("overlay", "outCubic") } }
        Behavior on border.width { enabled: themeMotion.enabled("overlay"); NumberAnimation { duration: themeMotion.duration("overlay", 180); easing.type: themeMotion.easing("overlay", "outCubic") } }
        Behavior on opacity { enabled: themeMotion.enabled("overlay"); NumberAnimation { duration: themeMotion.duration("overlay", 180); easing.type: themeMotion.easing("overlay", "outCubic") } }
    }
    Rectangle {
        objectName: "settingsContentPanel"
        x: root.rightBounds.x; y: root.rightBounds.y
        width: root.rightBounds.width; height: root.rightBounds.height
        radius: root.luluPalette.radius("panel", 14) * root.uiScale
        color: root.luluPalette.cardSurface
        border.width: root.activePanel === "content" ? 3 * root.uiScale : 1 * root.uiScale
        border.color: root.activePanel === "content"
            ? root.luluPalette.focusIndicator : root.luluPalette.glassBorder
        opacity: root.activePanel === "content" ? 1 : 0.72
        MudosChromeFrame {
            anchors.fill: parent
            luluPalette: root.luluPalette
            uiScale: root.uiScale
            cornerRadius: parent.radius
            raised: root.activePanel === "content"
        }
        Behavior on border.color { enabled: themeMotion.enabled("overlay"); ColorAnimation { duration: themeMotion.duration("overlay", 180); easing.type: themeMotion.easing("overlay", "outCubic") } }
        Behavior on border.width { enabled: themeMotion.enabled("overlay"); NumberAnimation { duration: themeMotion.duration("overlay", 180); easing.type: themeMotion.easing("overlay", "outCubic") } }
        Behavior on opacity { enabled: themeMotion.enabled("overlay"); NumberAnimation { duration: themeMotion.duration("overlay", 180); easing.type: themeMotion.easing("overlay", "outCubic") } }
    }

    Column {
        x: root.leftBounds.x + 20 * root.uiScale
        y: root.leftBounds.y + 18 * root.uiScale
        width: root.leftBounds.width - 40 * root.uiScale
        spacing: 2 * root.uiScale
        Repeater {
            model: root.categories
            delegate: Item {
                id: categoryRow
                objectName: "settingsCategoryRow_" + index
                required property int index
                required property var modelData
                width: parent.width
                height: 54 * root.uiScale
                Rectangle {
                    anchors.fill: parent
                    anchors.leftMargin: 2 * root.uiScale
                    anchors.rightMargin: 2 * root.uiScale
                    radius: root.luluPalette.radius("row", 8) * root.uiScale
                    color: categoryRow.index === root.selectedCategory
                        ? root.luluPalette.selectionSurface
                        : "transparent"
                    border.color: categoryRow.index === root.selectedCategory
                        ? root.luluPalette.focusIndicator : "transparent"
                    border.width: categoryRow.index === root.selectedCategory
                        ? 2 * root.uiScale : 0
                }
                MudosIcon {
                    x: 14 * root.uiScale; width: 30 * root.uiScale
                    height: parent.height
                    name: String(categoryRow.modelData.iconName || "settings")
                    glyph: String(categoryRow.modelData.glyph || "")
                    typography: root.typography
                    iconSize: 24 * root.uiScale
                    semanticColor: categoryRow.index === root.selectedCategory
                        ? root.luluPalette.headingAccent : root.luluPalette.navigationText
                }
                Text {
                    x: 56 * root.uiScale
                    width: parent.width - 70 * root.uiScale
                    height: parent.height
                    text: String(categoryRow.modelData.label || "")
                    color: categoryRow.index === root.selectedCategory
                        ? root.luluPalette.primaryText : root.luluPalette.navigationText
                    font.family: root.typography.interfaceFamily
                    font.pixelSize: root.typography.size("body", 19)
                    font.weight: categoryRow.index === root.selectedCategory ? Font.DemiBold : Font.Normal
                    verticalAlignment: Text.AlignVCenter
                    elide: Text.ElideRight
                }
                MouseArea {
                    anchors.fill: parent
                    onClicked: {
                        root.selectedCategory = categoryRow.index
                        root.enterCategories()
                        root.categoryChanged(categoryRow.index)
                    }
                }
            }
        }
    }

    Item {
        id: host
        objectName: "settingsContentHost"
        x: root.rightBounds.x
        y: root.rightBounds.y
        width: root.rightBounds.width
        height: root.rightBounds.height
        clip: true
        MouseArea {
            anchors.fill: parent
            z: -1
            onPressed: root.enterContent()
        }
    }
}
