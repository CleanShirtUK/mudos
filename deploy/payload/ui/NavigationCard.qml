import QtQuick

Item {
    id: root
    property string displayTitle: ""
    property string symbolicArtwork: ""
    property url artworkSource: ""
    property string artworkRole: "icon"
    property bool focused: false
    property bool selectedOpacityOwner: focused
    property real selectionProgress: focused ? 1 : 0
    property real uiScale: 1
    property var typography
    property var luluPalette
    property var canonicalTexture
    property var canonicalCoordinateRoot
    property size canonicalSize: Qt.size(1280, 720)
    property bool transparentOutsideMask: false
    property var canonicalMappingDependency: null
    property real mappingRevision: 0
    property real categoryProgress: 1
    property bool categoryTransitioning: false
    property int categoryFrom: -1
    property int categoryTarget: -1
    property int categoryDirection: 1
    property real presentationAncestorY: 0
    property real presentationAncestorScale: 1
    property bool motionBlurActive: false
    property real motionStartX: 0
    property real motionTargetX: 0
    property real motionProgress: 1
    property real motionDuration: 500
    property real motionBlurPixels: 0
    property real motionBlurVerticalPixels: 0
    property vector2d motionBlurVector: Qt.vector2d(motionBlurPixels,
                                                     motionBlurVerticalPixels)
    property real motionBlurPadding: 64
    readonly property real motionVelocity: motionBlurActive
        ? (motionTargetX - motionStartX) * 5
            * Math.pow(1 - Math.max(0, Math.min(1, motionProgress)), 4)
            / motionDuration : 0
    signal activated()

    readonly property rect nativeCanonicalRect: {
        var presentationDependency = canonicalMappingDependency
        var categoryDependency = categoryProgress
            + (categoryTransitioning ? 1 : 0)
            + categoryFrom + categoryTarget + categoryDirection
            + presentationAncestorY + presentationAncestorScale + mappingRevision
        var topLeft = canonicalCoordinateRoot
            ? root.mapToItem(canonicalCoordinateRoot, 0, 0) : Qt.point(0, 0)
        var bottomRight = canonicalCoordinateRoot
            ? root.mapToItem(canonicalCoordinateRoot, root.width, root.height)
            : Qt.point(root.width, root.height)
        return Qt.rect(topLeft.x + categoryDependency - categoryDependency,
                       topLeft.y + categoryDependency - categoryDependency,
                       bottomRight.x - topLeft.x,
                       bottomRight.y - topLeft.y)
    }


    Item {
        id: logicalCard
        anchors.fill: parent

        NavigationCardSurface {
            id: navigationSurface
            anchors.fill: parent
            canonicalTexture: root.canonicalTexture
            canonicalSize: root.canonicalSize
            canonicalCoordinateRoot: root.canonicalCoordinateRoot
            canonicalRect: root.nativeCanonicalRect
            canonicalMappingDependency: root.canonicalMappingDependency
            transparentOutsideMask: root.transparentOutsideMask
            uiScale: root.uiScale
        }

        GameCard {
            id: cardVisual
            anchors.fill: parent
            compact: true
            homeCard: false
            glassVisible: false
            librarySurfaceMaterial: true
            focused: root.focused
            selectionProgress: root.selectionProgress
        // Selection ownership changes with the logical focus immediately;
        // selectionProgress remains presentation-only for the existing 180 ms
        // focus choreography.
        focusBrightness: root.selectedOpacityOwner ? 1 : 0.68
            displayTitle: root.displayTitle
            symbolicArtwork: root.symbolicArtwork
            artworkRole: root.artworkRole
            artworkSource: root.artworkSource
            uiScale: root.uiScale
            typography: root.typography
            luluPalette: root.luluPalette
            MouseArea {
                anchors.fill: parent
                onClicked: root.activated()
            }
        }

    }

    DirectionalMotionBlur {
        id: motionBlur
        x: -root.motionBlurPadding
        y: -root.motionBlurPadding
        width: root.width + 2 * root.motionBlurPadding
        height: root.height + 2 * root.motionBlurPadding
        active: root.motionBlurActive && root.visible
        sourceItem: logicalCard
        sourceRect: Qt.rect(-root.motionBlurPadding, -root.motionBlurPadding,
                            width, height)
        blurPixels: root.motionBlurPixels
        blurVector: root.motionBlurVector
    }

}
