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
    property bool nativeGlassEnabled: false
    property bool transparentOutsideMask: false
    property bool glassDiscriminatorEnabled: false
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


    function dumpNativeMapping() {
        navigationSurface.dumpNativeMapping(Qt.point(root.x, root.y))
    }

    function dumpRuntimeState() {
        navigationSurface.dumpRuntimeState(Qt.point(root.x, root.y))
    }

    function dumpRendererState() {
        navigationSurface.dumpRendererState(root.objectName || root.displayTitle)
    }

    function dumpPresentationState(mark, identity) {
        var cardIdentity = identity || root.objectName || root.displayTitle
        console.log("MUDOS_NAVIGATION_CARD_PRESENTATION",
                    "mark", mark, "identity", cardIdentity,
                    "visible", root.visible, "opacity", root.opacity,
                    "focused", root.focused,
                    "selectionProgress", root.selectionProgress,
                    "position", root.x, root.y,
                    "size", root.width, root.height,
                    "motionBlurActive", motionBlur.active,
                    "motionBlurVisible", motionBlur.visible,
                    "logicalCardVisible", logicalCard.visible,
                    "logicalCardOpacity", logicalCard.opacity,
                    "canonicalRect", root.nativeCanonicalRect.x,
                        root.nativeCanonicalRect.y,
                        root.nativeCanonicalRect.width,
                        root.nativeCanonicalRect.height)
        navigationSurface.dumpPresentationState(mark, cardIdentity)
        cardVisual.dumpPresentationState(mark, cardIdentity)
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
            nativeGlassEnabled: root.nativeGlassEnabled
            transparentOutsideMask: root.transparentOutsideMask
            glassDiscriminatorEnabled: root.glassDiscriminatorEnabled
            selected: root.focused
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

        Rectangle {
            visible: root.glassDiscriminatorEnabled && root.focused
            z: 100
            x: 8 * root.uiScale
            y: 8 * root.uiScale
            width: label.implicitWidth + 14 * root.uiScale
            height: 24 * root.uiScale
            radius: 4 * root.uiScale
            color: root.nativeGlassEnabled ? "#b8f7c5" : "#ffd0d0"
            Text {
                id: label
                anchors.centerIn: parent
                text: root.nativeGlassEnabled ? "NATIVE" : "LEGACY"
                color: "#101010"
                font.bold: true
                font.pixelSize: 13 * root.uiScale
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
