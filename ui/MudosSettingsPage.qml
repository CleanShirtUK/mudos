import QtQuick
import QtQuick.Effects

Item {
    id: root

    property string title: "SETTINGS"
    property var rows: []
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
    property real expandedShellBottom: 0
    property string footerText: ""
    property bool rowsVisible: true
    readonly property real contentInset: 44 * root.uiScale
    readonly property real horizontalScaleInset: 72 * root.uiScale
    readonly property real selectionScale: 1.01
    readonly property real selectedBorderWidth: 3 * root.uiScale
    readonly property real selectedGlassEdgeSafety: 3 * root.uiScale
    readonly property real verticalScaleInset:
        58 * root.uiScale * (root.selectionScale - 1) / 2
        + root.selectedBorderWidth * root.selectionScale / 2
        + root.selectedGlassEdgeSafety
    readonly property real nominalRowWidth: root.expandedShellWidth
        - 2 * root.contentInset - root.horizontalScaleInset
    property real scrollY: 0
    signal rowActivated(int index)

    function ensureSelectedVisible() {
        var step = 58 * root.uiScale + 10 * root.uiScale
        var top = root.verticalScaleInset + root.selectedIndex * step
        var bottom = top + 58 * root.uiScale
        var viewportTop = root.scrollY + root.verticalScaleInset
        var viewportBottom = root.scrollY
            + (7 * 58 * root.uiScale + 6 * 10 * root.uiScale)
            - root.verticalScaleInset
        var maximum = Math.max(0, rowColumn.height
            + 2 * root.verticalScaleInset
            - (7 * 58 * root.uiScale + 6 * 10 * root.uiScale))
        if (top < viewportTop)
            root.scrollY = Math.max(0, top)
        else if (bottom > viewportBottom)
            root.scrollY = Math.min(maximum, bottom
                - (7 * 58 * root.uiScale + 6 * 10 * root.uiScale))
    }

    onSelectedIndexChanged: ensureSelectedVisible()
    onRowsChanged: ensureSelectedVisible()
    Component.onCompleted: ensureSelectedVisible()

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
        text: root.title
        color: root.luluPalette.headingAccent
        font.family: root.typography.majorHeadingFamily
        font.weight: root.typography.majorHeadingWeight
        font.pixelSize: root.typography.size("section", 30)
        font.letterSpacing: 5 * root.uiScale
    }

    Flickable {
        x: root.expandedShellX + root.contentInset
            - root.horizontalScaleInset
        y: root.expandedShellY + 110 * root.uiScale
        width: root.nominalRowWidth + 2 * root.horizontalScaleInset
        height: 7 * 58 * root.uiScale + 6 * 10 * root.uiScale
        visible: root.rowsVisible
        clip: true
        contentWidth: width
        contentHeight: rowColumn.height + 2 * root.verticalScaleInset
        contentY: root.scrollY
        boundsBehavior: Flickable.StopAtBounds

        Column {
            id: rowColumn
            y: root.verticalScaleInset
            x: root.horizontalScaleInset
            width: root.nominalRowWidth
            spacing: 10 * root.uiScale

            Repeater {
                model: root.rows
                delegate: Item {
                    id: rowDelegate
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

                    Item {
                        id: visualRow
                        anchors.fill: parent
                        MudosCardSurface {
                            anchors.fill: parent
                            scale: 1 + (root.selectionScale - 1)
                                * rowDelegate.selectionProgress
                            transformOrigin: Item.Center
                            selectionProgress: rowDelegate.selectionProgress
                            uiScale: root.uiScale
                            luluPalette: root.luluPalette
                            canonicalTexture: root.canonicalTexture
                            canonicalCoordinateRoot: root.canonicalCoordinateRoot
                            canonicalSize: root.canonicalSize
                            mappingItem: rowDelegate
                        }

                        Item {
                            id: contentRow
                            anchors.fill: parent

                            TextMetrics {
                                id: labelMetrics
                                text: String(rowDelegate.modelData.label || "")
                                font.family: root.typography.interfaceFamily
                                font.pixelSize: root.typography.size("body", 18)
                            }
                            TextMetrics {
                                id: valueMetrics
                                text: String(rowDelegate.modelData.value || "")
                                font.family: root.typography.interfaceFamily
                                font.pixelSize: root.typography.size("body", 16)
                            }

                            readonly property real valueVisualWidth: Math.min(
                                valueMetrics.advanceWidth, parent.width * 0.48)
                            readonly property real labelMaximumWidth:
                                Math.max(1, parent.width - valueVisualWidth
                                    - 40 * root.uiScale)
                            readonly property real labelVisualWidth: Math.min(
                                labelMaximumWidth,
                                Math.max(1, labelMetrics.advanceWidth))

                            Item {
                                id: labelVisual
                                x: 18 * root.uiScale
                                width: contentRow.labelVisualWidth
                                height: parent.height
                                anchors.verticalCenter: parent.verticalCenter
                                scale: 1 + (root.selectionScale - 1)
                                    * rowDelegate.selectionProgress
                                transformOrigin: Item.Center

                                Text {
                                    id: labelText
                                    x: 0
                                    width: parent.width
                                    height: parent.height
                                    text: rowDelegate.modelData.label
                                    color: rowDelegate.index === root.selectedIndex
                                        ? root.luluPalette.primaryText
                                        : root.luluPalette.navigationText
                                    font.family: root.typography.interfaceFamily
                                    font.pixelSize: root.typography.size("body", 18)
                                    elide: Text.ElideRight
                                    verticalAlignment: Text.AlignVCenter
                                }
                                layer.enabled: true
                                layer.effect: MultiEffect {
                                    shadowEnabled: true
                                    shadowColor: "#000000"
                                    shadowOpacity: 0.35
                                    shadowBlur: 0.2
                                    shadowVerticalOffset: 1 * root.uiScale
                                }
                            }
                            Item {
                                id: valueVisual
                                x: parent.width - 18 * root.uiScale
                                    - contentRow.valueVisualWidth
                                width: contentRow.valueVisualWidth
                                height: parent.height
                                visible: width > 0
                                scale: 1 + (root.selectionScale - 1)
                                    * rowDelegate.selectionProgress
                                transformOrigin: Item.Center

                                Text {
                                    id: valueText
                                    x: 0
                                    width: parent.width
                                    height: parent.height
                                    text: String(rowDelegate.modelData.value || "")
                                    color: rowDelegate.index === root.selectedIndex
                                        ? root.luluPalette.primaryText
                                        : root.luluPalette.navigationText
                                    font.family: root.typography.interfaceFamily
                                    font.pixelSize: root.typography.size("body", 16)
                                    horizontalAlignment: Text.AlignRight
                                    elide: Text.ElideRight
                                    verticalAlignment: Text.AlignVCenter
                                }
                                layer.enabled: true
                                layer.effect: MultiEffect {
                                    shadowEnabled: true
                                    shadowColor: "#000000"
                                    shadowOpacity: 0.35
                                    shadowBlur: 0.2
                                    shadowVerticalOffset: 1 * root.uiScale
                                }
                            }
                        }
                    }

                    MouseArea {
                        anchors.fill: parent
                        enabled: rowDelegate.modelData.writable !== false
                        onClicked: root.rowActivated(rowDelegate.index)
                    }
                }
            }
        }
    }

    Text {
        visible: root.footerText !== ""
        x: root.expandedShellX + root.contentInset
        y: root.expandedShellBottom - 42 * root.uiScale
        width: root.expandedShellWidth - 2 * root.contentInset
        text: root.footerText
        color: root.luluPalette.secondaryText
        font.family: root.typography.interfaceFamily
        font.pixelSize: root.typography.size("body", 16)
        elide: Text.ElideRight
    }
}
