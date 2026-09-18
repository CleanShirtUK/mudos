import QtQuick

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
    readonly property real nominalRowWidth: root.expandedShellWidth
        - 2 * root.contentInset - root.horizontalScaleInset
    signal rowActivated(int index)

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
        contentHeight: rowColumn.height + 8 * root.uiScale
        contentY: Math.max(0, Math.min(contentHeight - height,
            root.selectedIndex * (58 * root.uiScale + 10 * root.uiScale)))
        boundsBehavior: Flickable.StopAtBounds

        Column {
            id: rowColumn
            y: 4 * root.uiScale
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
                        scale: 1 + 0.05 * rowDelegate.selectionProgress
                        transformOrigin: Item.Left

                        MudosCardSurface {
                            anchors.fill: parent
                            selectionProgress: rowDelegate.selectionProgress
                            uiScale: root.uiScale
                            luluPalette: root.luluPalette
                            canonicalTexture: root.canonicalTexture
                            canonicalCoordinateRoot: root.canonicalCoordinateRoot
                            canonicalSize: root.canonicalSize
                            mappingItem: rowDelegate
                        }

                        Text {
                            id: labelText
                            x: 18 * root.uiScale
                            anchors.verticalCenter: parent.verticalCenter
                            width: Math.max(0, parent.width - valueText.width
                                - 40 * root.uiScale)
                            text: rowDelegate.modelData.label
                            color: rowDelegate.index === root.selectedIndex
                                ? root.luluPalette.primaryText
                                : root.luluPalette.navigationText
                            font.family: root.typography.interfaceFamily
                            font.pixelSize: root.typography.size("body", 18)
                            elide: Text.ElideRight
                        }
                        Text {
                            id: valueText
                            anchors.right: parent.right
                            anchors.rightMargin: 18 * root.uiScale
                            anchors.verticalCenter: parent.verticalCenter
                            width: Math.min(implicitWidth, parent.width * 0.48)
                            text: String(rowDelegate.modelData.value || "")
                            color: rowDelegate.index === root.selectedIndex
                                ? root.luluPalette.primaryText
                                : root.luluPalette.navigationText
                            font.family: root.typography.interfaceFamily
                            font.pixelSize: root.typography.size("body", 16)
                            horizontalAlignment: Text.AlignRight
                            elide: Text.ElideRight
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
