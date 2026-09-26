import QtQuick

Item {
    id: root

    property var canonicalTexture
    property var canonicalCoordinateRoot
    property size canonicalSize: Qt.size(1280, 720)
    property real progress: 0
    property real homeX: 0
    property real homeY: 0
    property real homeWidth: 0
    property real homeHeight: 0
    property real fullscreenX: 0
    property real fullscreenY: 0
    property real fullscreenWidth: 0
    property real fullscreenHeight: 0
    property real uiScale: 1
    property real verticalOffset: 0
    property bool surfaceVisible: false
    property bool transparentOutsideMask: true
    property color panelSurfaceColor: "transparent"
    property real panelSurfaceOpacity: 0.40

    readonly property real surfaceX: homeX + (fullscreenX - homeX) * progress
    readonly property real surfaceY: homeY + (fullscreenY - homeY) * progress
    readonly property real surfaceWidth: homeWidth + (fullscreenWidth - homeWidth) * progress
    readonly property real surfaceHeight: homeHeight + (fullscreenHeight - homeHeight) * progress

    x: surfaceX
    y: surfaceY + verticalOffset
    width: surfaceWidth
    height: surfaceHeight
    visible: surfaceVisible

    // mapToItem() does not itself invalidate when an ancestor moves or
    // scales. Read every authoritative presentation input here so the
    // canonical rectangle is recomputed throughout interpolation, including
    // reversal/retarget and category offset changes.
    readonly property rect canonicalRect: {
        var presentationDependency = progress + homeX + homeY
            + homeWidth + homeHeight + fullscreenX + fullscreenY
            + fullscreenWidth + fullscreenHeight + verticalOffset + uiScale
            + x + y + width + height
        var ancestorDependency = parent
            ? parent.x + parent.y + parent.scale : 0
        var dependency = presentationDependency + ancestorDependency
        var topLeft = canonicalCoordinateRoot
            ? root.mapToItem(canonicalCoordinateRoot, 0, 0)
            : Qt.point(0, 0)
        var bottomRight = canonicalCoordinateRoot
            ? root.mapToItem(canonicalCoordinateRoot, width, height)
            : Qt.point(width, height)
        return Qt.rect(topLeft.x + dependency - dependency,
                       topLeft.y + dependency - dependency,
                       bottomRight.x - topLeft.x,
                       bottomRight.y - topLeft.y)
    }

    NavigationCardSurface {
        id: spatialSurface
        anchors.fill: parent
         canonicalTexture: root.canonicalTexture
         canonicalSize: root.canonicalSize
         canonicalCoordinateRoot: root.canonicalCoordinateRoot
         canonicalRect: root.canonicalRect
         transparentOutsideMask: root.transparentOutsideMask
         cornerRadius: 16 * root.uiScale + 12 * root.uiScale * root.progress
         bevelWidthPx: 3 * root.uiScale + 3 * root.uiScale * root.progress
    }

    // Match the list/detail surface tint only as this shared backing expands;
    // the established uncoloured Home card remains unchanged at progress 0.
    Rectangle {
        anchors.fill: parent
        radius: spatialSurface.cornerRadius
        color: root.panelSurfaceColor
        opacity: root.panelSurfaceOpacity * root.progress
    }
}
