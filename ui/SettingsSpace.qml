pragma ComponentBehavior: Bound
import QtQuick

// Unified Settings navigation and panel chrome. Category content remains
// owned by the existing category-specific components hosted in contentHost.
Item {
    id: root
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
    readonly property real panelInset: 20 * uiScale
    readonly property rect leftBounds: Qt.rect(panelInset, 0,
        leftWidth - panelGap / 2 - panelInset, height)
    readonly property rect rightBounds: Qt.rect(leftWidth + panelGap / 2, 0,
        width - leftWidth - panelGap / 2 - panelInset, height)
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

    MudosCardSurface {
        id: leftGlass
        objectName: "settingsLeftGlass"
        x: root.leftBounds.x; y: root.leftBounds.y
        width: root.leftBounds.width; height: root.leftBounds.height
        uiScale: root.uiScale
        luluPalette: root.luluPalette
        canonicalTexture: root.canonicalTexture
        canonicalCoordinateRoot: root.canonicalCoordinateRoot
        canonicalSize: root.canonicalSize
        selectionProgress: 0
    }
    Rectangle {
        objectName: "settingsCategoryPanel"
        x: root.leftBounds.x; y: root.leftBounds.y
        width: root.leftBounds.width; height: root.leftBounds.height
        radius: 14 * root.uiScale
        color: "transparent"
        border.width: root.activePanel === "categories" ? 3 * root.uiScale : 1 * root.uiScale
        border.color: root.activePanel === "categories"
            ? root.luluPalette.focusIndicator : root.luluPalette.glassBorder
        opacity: root.activePanel === "categories" ? 1 : 0.72
        Behavior on border.color { ColorAnimation { duration: 180; easing.type: Easing.OutCubic } }
        Behavior on border.width { NumberAnimation { duration: 180; easing.type: Easing.OutCubic } }
        Behavior on opacity { NumberAnimation { duration: 180; easing.type: Easing.OutCubic } }
    }
    MudosCardSurface {
        id: rightGlass
        objectName: "settingsRightGlass"
        x: root.rightBounds.x; y: root.rightBounds.y
        width: root.rightBounds.width; height: root.rightBounds.height
        uiScale: root.uiScale
        luluPalette: root.luluPalette
        canonicalTexture: root.canonicalTexture
        canonicalCoordinateRoot: root.canonicalCoordinateRoot
        canonicalSize: root.canonicalSize
        selectionProgress: 0
    }
    Rectangle {
        objectName: "settingsContentPanel"
        x: root.rightBounds.x; y: root.rightBounds.y
        width: root.rightBounds.width; height: root.rightBounds.height
        radius: 14 * root.uiScale
        color: "transparent"
        border.width: root.activePanel === "content" ? 3 * root.uiScale : 1 * root.uiScale
        border.color: root.activePanel === "content"
            ? root.luluPalette.focusIndicator : root.luluPalette.glassBorder
        opacity: root.activePanel === "content" ? 1 : 0.72
        Behavior on border.color { ColorAnimation { duration: 180; easing.type: Easing.OutCubic } }
        Behavior on border.width { NumberAnimation { duration: 180; easing.type: Easing.OutCubic } }
        Behavior on opacity { NumberAnimation { duration: 180; easing.type: Easing.OutCubic } }
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
                    radius: 8 * root.uiScale
                    color: categoryRow.index === root.selectedCategory
                        ? Qt.rgba(root.luluPalette.focusIndicator.r,
                                  root.luluPalette.focusIndicator.g,
                                  root.luluPalette.focusIndicator.b, 0.18)
                        : "transparent"
                    opacity: categoryRow.index === root.selectedCategory ? 0.9 : 0
                }
                Text {
                    x: 14 * root.uiScale; width: 30 * root.uiScale
                    height: parent.height
                    text: String(categoryRow.modelData.glyph || "")
                    color: categoryRow.index === root.selectedCategory
                        ? root.luluPalette.headingAccent : root.luluPalette.navigationText
                    font.family: root.typography.displayFamily
                    font.pixelSize: root.typography.size("body", 24)
                    verticalAlignment: Text.AlignVCenter
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
