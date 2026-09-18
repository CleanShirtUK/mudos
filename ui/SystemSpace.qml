import QtQuick

Item {
    id: root
    property string category: "System"
    property var settings: []
    property int selectedIndex: 0
    property real uiScale: 1
    property var typography
    property var luluPalette
    property var canonicalTexture
    property var canonicalCoordinateRoot
    property size canonicalSize: Qt.size(1280, 720)
    property real expandedShellX: 0
    property real expandedShellY: 0
    property real expandedShellWidth: 0
    property real expandedShellHeight: 0
    readonly property real contentInset: 44 * root.uiScale
    signal actionRequested(string key)
    property int visibleRows: 7

    LibrarySpatialSurface {
        fullscreenX: root.expandedShellX
        fullscreenY: root.expandedShellY
        fullscreenWidth: root.expandedShellWidth
        fullscreenHeight: root.expandedShellHeight
        progress: 1
        uiScale: root.uiScale
        canonicalTexture: root.canonicalTexture
        canonicalCoordinateRoot: root.canonicalCoordinateRoot
        canonicalSize: root.canonicalSize
        surfaceVisible: true
        transparentOutsideMask: true
    }

    Text {
        x: root.expandedShellX + root.contentInset
        y: root.expandedShellY + root.contentInset
        text: root.category.toUpperCase()
        color: luluPalette.headingAccent
        font.family: typography.majorHeadingFamily
        font.weight: typography.majorHeadingWeight
        font.pixelSize: typography.size("section", 30)
        font.letterSpacing: 5 * root.uiScale
    }

    Flickable {
        x: root.expandedShellX + root.contentInset
        y: root.expandedShellY + 110 * root.uiScale
        width: root.expandedShellWidth - 2 * root.contentInset
        height: 7 * 58 * root.uiScale + 6 * 10 * root.uiScale
        clip: true
        contentWidth: width
        contentHeight: rowColumn.height + 8 * root.uiScale
        contentY: Math.max(0, Math.min(contentHeight - height,
            root.selectedIndex * (58 * root.uiScale + 10 * root.uiScale)))
        boundsBehavior: Flickable.StopAtBounds

        Column {
            id: rowColumn
            y: 4 * root.uiScale
            width: parent.width
            spacing: 10 * root.uiScale

            Repeater {
                model: root.settings
                delegate: Item {
                required property int index
                required property var modelData
                width: parent.width
                height: 58 * root.uiScale
                z: index === root.selectedIndex ? 1 : 0
                property real selectionProgress: index === root.selectedIndex ? 1 : 0
                Behavior on selectionProgress {
                    NumberAnimation {
                        duration: 180
                        easing.type: Easing.OutQuint
                    }
                }

                MudosCardSurface {
                    anchors.fill: parent
                    scale: 1 + 0.05 * parent.selectionProgress
                    transformOrigin: Item.Center
                    selectionProgress: parent.selectionProgress
                    uiScale: root.uiScale
                    luluPalette: root.luluPalette
                    canonicalTexture: root.canonicalTexture
                    canonicalCoordinateRoot: root.canonicalCoordinateRoot
                    canonicalSize: root.canonicalSize
                }

                Text {
                    x: 18 * root.uiScale
                    anchors.verticalCenter: parent.verticalCenter
                    text: modelData.label
                    color: luluPalette.primaryText
                    font.family: typography.interfaceFamily
                    font.pixelSize: typography.size("body", 18)
                    z: 1
                }
                Text {
                    anchors.right: parent.right
                    anchors.rightMargin: 18 * root.uiScale
                    anchors.verticalCenter: parent.verticalCenter
                    text: String(modelData.value)
                    color: luluPalette.secondaryText
                    font.family: typography.interfaceFamily
                    font.pixelSize: typography.size("body", 16)
                    z: 1
                }
                MouseArea {
                    anchors.fill: parent
                    enabled: modelData.writable === true && modelData.kind === "action"
                    onClicked: root.actionRequested(modelData.key)
                }
                }
            }
        }
    }
}
