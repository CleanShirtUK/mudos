import QtQuick
import QtQuick.Effects
import "MudosAssetCatalog.js" as MudosAssetCatalog
import Mudos.Poc 1.0

Rectangle {
    id: card

    property var game: null
    property bool focused: false
    property bool compact: false
    property bool showAction: false
    property bool homeCard: false
    property bool glassVisible: true
    property bool librarySurfaceMaterial: false
    property string presentationState: "COMPACT"
    property var canonicalTexture: null
    property var canonicalCoordinateRoot: null
    property size canonicalSize: Qt.size(1280, 720)
    property real focalScale: 1
    property real uiScale: 1
    property var typography
    property var luluPalette
    property string displayTitle: ""
    property string actionLabel: "Play"
    property url artworkSource: ""
    property string artworkRole: "raster"
    // The supplied fallback asset belongs at this normal artwork-pipeline path.
    property url fallbackArtworkSource: Qt.resolvedUrl(MudosAssetCatalog.suppliedArtwork("fallback"))
    property string presentationId: ""
    property string symbolicArtwork: ""
    property bool identitySampling: false
    property bool liveSceneCoordinates: false
    // Recent supplies the authoritative row/delegate presentation inputs.
    // Reading this value in the mapping binding makes ancestor translations
    // invalidate the mapToItem() result without changing the item hierarchy.
    property var canonicalMappingDependency: null
    property real canonicalMappingRevision: 0
    // Catalogue cards use the rounded mask as the presentation boundary;
    // outside the boundary must remain transparent rather than falling back
    // to an undiffused canonical backdrop. Recent/landing keep their
    // established native composition by default.
    property bool nativeGlassTransparentOutsideMask: false
    property bool neutralOptics: false
    // Focal diagnostic stages: 0 neutral, then transmission, diffusion, bevel,
    // bulge, refraction, dispersion, and edge lighting.
    property int opticsStage: -1
    property real presentationProgress: recentFocal ? 1 : 0
    property real focalChromeOpacity: presentationProgress
    property real presentationContentOpacity: 1
    property real compactTitleOpacity: 1
    property real selectionProgress: focused ? 1 : 0
    property int playActivationSerial: 0
    property real playButtonScale: 1
    signal playFeedbackCompleted()
    property real compactEndpointWidth: 0
    property point sceneOriginOverride: canonicalSceneOrigin
    property size sceneSizeOverride: Qt.size(width, height)
    // Catalogue cards share the same glass-backed visual surface as navigation cards.
    // Interaction remains owned by the containing delegate.
    property bool catalogueCard: false
    property real focusBrightness: 1
    Behavior on selectionProgress {
        NumberAnimation {
            duration: 180
            easing.type: Easing.OutQuint
        }
    }
    Behavior on focusBrightness {
        NumberAnimation {
            duration: 180
            easing.type: Easing.OutQuint
        }
    }
    Behavior on scale {
        NumberAnimation {
            duration: 180
            easing.type: Easing.OutQuint
        }
    }
    readonly property bool recentFocal: homeCard && focused
    readonly property string presentationGameId: presentationId || (game ? String(game.game_id) : "")
    onPlayActivationSerialChanged: {
        if (card.recentFocal)
            playPressAnimation.restart()
    }

    SequentialAnimation {
        id: playPressAnimation
        NumberAnimation {
            target: card
            property: "playButtonScale"
            to: 0.97
            duration: 60
            easing.type: Easing.OutQuint
        }
        NumberAnimation {
            target: card
            property: "playButtonScale"
            to: 1
            duration: 100
            easing.type: Easing.OutQuint
        }
        onStopped: {
            if (card.playButtonScale === 1)
                card.playFeedbackCompleted()
        }
    }
    readonly property var focalMetadataRows: {
        var rows = []
        if (!card.game)
            return rows
        var genres = card.game.genres || []
        var usefulGenres = []
        for (var genreIndex = 0; genreIndex < genres.length; genreIndex++) {
            if (String(genres[genreIndex]).trim().length > 0)
                usefulGenres.push(String(genres[genreIndex]).trim())
        }
        if (usefulGenres.length)
            rows.push("Genres  " + usefulGenres.join(" · "))
        if (Number(card.game.last_played) > 0)
            rows.push("Last Played  " + Qt.formatDateTime(
                new Date(Number(card.game.last_played) * 1000), "d MMM yyyy"))
        if (card.game.local_multiplayer === true || Number(card.game.local_multiplayer) === 1)
            rows.push("Local Multiplayer")
        if (card.game.online_multiplayer === true || Number(card.game.online_multiplayer) === 1)
            rows.push("Online Multiplayer")
        return rows
    }
    readonly property url displayedArtworkSource: String(card.artworkSource).length > 0
        ? card.artworkSource
        : (card.game && !card.game.artwork_suppressed && card.game.artwork_url
            ? card.game.artwork_url : card.fallbackArtworkSource)
    readonly property bool iconArtwork: card.artworkRole === "icon" || !!card.symbolicArtwork
    readonly property real focalMargin: 30 * focalScale * uiScale
    readonly property real compactMargin: 14 * uiScale
    readonly property real artworkHeight: height - 2 * focalMargin
    readonly property real artworkWidth: artworkHeight / 1.5
    readonly property real compactArtworkWidth: compactEndpointWidth > 0
        ? compactEndpointWidth - 28 * uiScale : width - 28 * uiScale
    readonly property real compactArtworkHeight: compactArtworkWidth * 1.5
    function mix(a, b, amount) { return a + (b - a) * amount }
    function focusedColor(color) {
        return Qt.rgba(color.r * focusBrightness, color.g * focusBrightness,
                       color.b * focusBrightness, color.a)
    }
    readonly property point canonicalSceneOrigin: {
        var presentationDependency = canonicalMappingDependency
        var origin = canonicalCoordinateRoot
            ? card.mapToItem(canonicalCoordinateRoot, 0, 0)
            : Qt.point(0, 0)
        // mapToItem() is not reactive to ancestor layout changes by itself.
        var layoutDependency = card.x + card.y + card.width + card.height
            + card.canonicalMappingRevision
        return Qt.point(origin.x + layoutDependency * 0, origin.y + layoutDependency * 0)
    }
    readonly property rect nativeRecentCanonicalRect: {
        var presentationDependency = canonicalMappingDependency
        var topLeft = canonicalCoordinateRoot
            ? card.mapToItem(canonicalCoordinateRoot, 0, 0) : Qt.point(0, 0)
        var bottomRight = canonicalCoordinateRoot
            ? card.mapToItem(canonicalCoordinateRoot, width, height)
            : Qt.point(width, height)
        var layoutDependency = card.x + card.y + card.width + card.height
            + card.canonicalMappingRevision
        return Qt.rect(topLeft.x + layoutDependency * 0,
                       topLeft.y + layoutDependency * 0,
                       bottomRight.x - topLeft.x,
                       bottomRight.y - topLeft.y)
    }

    // Play is a second canonical native-glass consumer. Its backdrop remains
    // Orbit, but its consumer-owned rectangle is derived from the Play item
    // itself so it tracks focal interpolation, resize, and retargeting.
    readonly property rect nativePlayCanonicalRect: {
        var presentationDependency = canonicalMappingDependency
        var layoutDependency = card.x + card.y + card.width + card.height
            + card.canonicalMappingRevision + card.presentationProgress
            + card.focalChromeOpacity + card.focalScale + card.uiScale
            + playButton.x + playButton.y + playButton.width
            + playButton.height + playButton.scale
        var topLeft = canonicalCoordinateRoot
            ? playButton.mapToItem(canonicalCoordinateRoot, 0, 0)
            : Qt.point(playButton.x, playButton.y)
        var bottomRight = canonicalCoordinateRoot
            ? playButton.mapToItem(canonicalCoordinateRoot,
                                   playButton.width, playButton.height)
            : Qt.point(playButton.x + playButton.width,
                       playButton.y + playButton.height)
        return Qt.rect(topLeft.x + layoutDependency - layoutDependency,
                       topLeft.y + layoutDependency - layoutDependency,
                       bottomRight.x - topLeft.x,
                       bottomRight.y - topLeft.y)
    }

    implicitWidth: recentFocal ? 1100 * uiScale : (compact ? 260 : 210) * uiScale
    implicitHeight: recentFocal ? 560 * uiScale : (compact ? 430 : 330) * uiScale
    radius: recentFocal ? 28 * focalScale * uiScale : (compact ? 16 : 18) * uiScale
    color: card.librarySurfaceMaterial ? luluPalette.transparent
        : (recentFocal ? luluPalette.glassTint
           : Qt.rgba(luluPalette.cardSurface.r
               + (luluPalette.focusedCardSurface.r - luluPalette.cardSurface.r) * card.selectionProgress,
               luluPalette.cardSurface.g
               + (luluPalette.focusedCardSurface.g - luluPalette.cardSurface.g) * card.selectionProgress,
               luluPalette.cardSurface.b
               + (luluPalette.focusedCardSurface.b - luluPalette.cardSurface.b) * card.selectionProgress,
               luluPalette.cardSurface.a
               + (luluPalette.focusedCardSurface.a - luluPalette.cardSurface.a) * card.selectionProgress))
    border.color: card.librarySurfaceMaterial ? luluPalette.transparent
        : Qt.rgba(luluPalette.glassBorder.r
            + (luluPalette.focusIndicator.r - luluPalette.glassBorder.r) * card.selectionProgress,
            luluPalette.glassBorder.g
            + (luluPalette.focusIndicator.g - luluPalette.glassBorder.g) * card.selectionProgress,
            luluPalette.glassBorder.b
            + (luluPalette.focusIndicator.b - luluPalette.glassBorder.b) * card.selectionProgress,
            luluPalette.glassBorder.a
            + (luluPalette.focusIndicator.a - luluPalette.glassBorder.a) * card.selectionProgress)
    border.width: card.librarySurfaceMaterial ? 0 : (1 + 2 * card.selectionProgress) * uiScale
    clip: true

    MudosGlassItem {
        id: nativeGlassSurface
        anchors.fill: parent
        visible: (card.homeCard || card.catalogueCard) && card.glassVisible
        backdrop: card.canonicalTexture
        canonicalSize: card.canonicalSize
        canonicalRect: card.nativeRecentCanonicalRect
        cornerRadius: card.radius
        refractionPixels: card.opticsStage >= 0 && card.opticsStage < 5 ? 0 : 80 * card.uiScale
        dispersionIor: card.opticsStage >= 0 && card.opticsStage < 6 ? 0 : 0.0175
        diffusionPixels: card.opticsStage >= 0 && card.opticsStage < 2 ? 0 : 5 * card.uiScale
        transmission: card.librarySurfaceMaterial ? 1
            : (card.opticsStage >= 0 && card.opticsStage < 1 ? 1 : 0.75)
        bevelWidthPx: card.opticsStage >= 0 && card.opticsStage < 3 ? 0 : 3 * card.uiScale
        bulgeStrength: card.opticsStage >= 0 && card.opticsStage < 4 ? 0 : 100.0
        sceneLightStrength: 0
        sceneLightPixels: 24
        edgeLightStrength: card.opticsStage >= 0 && card.opticsStage < 7 ? 0 : 0.10
        edgeLightDirection: Qt.vector2d(1, -1)
        transparentOutsideMask: card.nativeGlassTransparentOutsideMask
    }

    Rectangle {
        id: artworkFrame
        x: card.mix(compactMargin, focalMargin, card.presentationProgress)
        y: card.mix(compactMargin, focalMargin, card.presentationProgress)
        width: card.mix(compactArtworkWidth, artworkWidth, card.presentationProgress)
        height: card.mix(compactArtworkHeight, artworkHeight, card.presentationProgress)
        property real artworkRadius: card.mix(10 * uiScale, 18 * focalScale * uiScale,
                                              card.presentationProgress)
        property real artworkBorderAlpha: 0.15
        radius: artworkRadius
        z: 2
        opacity: card.presentationContentOpacity
        color: recentFocal
                ? luluPalette.transparent : luluPalette.artworkSurface
        clip: true

        Image {
            id: artworkSource
            anchors.fill: parent
            source: card.displayedArtworkSource
            fillMode: Image.PreserveAspectFit
            asynchronous: true
            retainWhileLoading: false
            visible: !card.iconArtwork
        }

        ShaderEffectSource {
            id: rasterArtworkTexture
            anchors.fill: parent
            sourceItem: artworkSource
            hideSource: true
            visible: false
        }

        ShaderEffect {
            anchors.fill: parent
            property var source: rasterArtworkTexture
            property real cornerRadius: artworkFrame.artworkRadius / Math.min(width, height)
            property vector2d artworkSize: Qt.vector2d(width, height)
            property real borderWidthPx: card.uiScale
            property real borderAlpha: artworkFrame.artworkBorderAlpha
            property real focusBrightness: card.focusBrightness
        opacity: card.focused ? 1 : 0.68
            visible: !card.iconArtwork
            fragmentShader: "shaders/card-rounded.frag.qsb"
        }

        Image {
            id: iconArtworkSource
            anchors.centerIn: parent
            width: card.iconArtwork ? parent.width * 0.5 : parent.width
            height: card.iconArtwork ? parent.height * 0.5 : parent.height
            source: card.displayedArtworkSource
            fillMode: Image.PreserveAspectFit
            asynchronous: true
            retainWhileLoading: false
            visible: card.iconArtwork
        }

        MultiEffect {
            anchors.fill: iconArtworkSource
            source: iconArtworkSource
            visible: card.iconArtwork
            z: 1
            colorization: 1.0
            colorizationColor: card.focusedColor(card.luluPalette.primaryText)
        }

        Text {
            anchors.centerIn: parent
            visible: !!card.symbolicArtwork
            text: card.symbolicArtwork
            color: card.focusedColor(card.luluPalette.primaryText)
            font.family: card.typography.displayFamily
            font.weight: card.typography.displayWeight
            font.pixelSize: card.typography.size("display", 100)
        }
    }

        Item {
        visible: card.focalChromeOpacity > 0
        opacity: card.focalChromeOpacity
        z: 1
        x: focalMargin + artworkWidth + focalMargin
        y: focalMargin
        width: parent.width - x - focalMargin
        height: artworkHeight

        Text {
            id: focalTitle
            width: parent.width
            text: card.displayTitle || (card.game
                ? (card.game.display_title_override || card.game.canonical_title || card.game.title) : "")
            color: Qt.rgba(card.luluPalette.primaryText.r * card.focusBrightness,
                           card.luluPalette.primaryText.g * card.focusBrightness,
                           card.luluPalette.primaryText.b * card.focusBrightness,
                           card.luluPalette.primaryText.a)
            font.family: card.typography ? card.typography.displayFamily : "JetBrains Mono"
            font.weight: card.typography ? card.typography.displayWeight : Font.Black
            font.pixelSize: card.typography ? card.typography.size("display", 34 * focalScale) : 34 * focalScale * card.uiScale
            wrapMode: Text.WordWrap
            maximumLineCount: 3
            elide: Text.ElideRight
        }

        Column {
            id: focalMetadata
            width: parent.width
            y: focalTitle.height + 22 * focalScale * card.uiScale
            spacing: 8 * focalScale * card.uiScale

            Repeater {
                model: card.focalMetadataRows
                delegate: Text {
                    required property string modelData
                    width: focalMetadata.width
                    text: modelData
                    color: card.focusedColor(card.luluPalette.secondaryText)
                    font.family: card.typography ? card.typography.interfaceFamily : "JetBrains Mono"
                    font.pixelSize: card.typography ? card.typography.size("secondary", 17 * focalScale) : 17 * focalScale * card.uiScale
                    elide: Text.ElideRight
                }
            }
        }

        Rectangle {
            id: playButton
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.bottom: parent.bottom
            height: 82 * focalScale * card.uiScale
            scale: card.playButtonScale
            radius: 20 * focalScale * card.uiScale
            color: card.presentationProgress > 0 && card.presentationProgress < 1
                ? card.luluPalette.transparent : card.luluPalette.actionSurface
            border.color: card.luluPalette.focusIndicator
            border.width: 2 * card.uiScale

            MudosGlassItem {
                id: nativePlayGlassSurface
                anchors.fill: parent
                visible: card.focalChromeOpacity > 0
                    && card.homeCard
                backdrop: card.canonicalTexture
                canonicalSize: card.canonicalSize
                canonicalRect: card.nativePlayCanonicalRect
                cornerRadius: playButton.radius
                ior: 1.08
                glassDepth: 0.18
                refractionPixels: 40 * card.uiScale
                dispersionIor: 0
                diffusionPixels: 5 * card.uiScale
                transmission: 0.82
                bevelWidthPx: 0
                bulgeStrength: 20
                edgeLightStrength: 0
                transparentOutsideMask: true
                opacity: card.focusBrightness
            }

            Text {
                anchors.centerIn: parent
                 text: card.actionLabel || "Play"
                color: card.focusedColor(card.luluPalette.actionText)
                font.family: card.typography ? card.typography.interfaceFamily : "JetBrains Mono"
                font.pixelSize: card.typography ? card.typography.size("control", 28 * focalScale) : 28 * focalScale * card.uiScale
            }
        }
    }

    Column {
        visible: card.compactTitleOpacity > 0
        opacity: card.compactTitleOpacity * card.presentationContentOpacity
        x: 14 * uiScale
        y: 14 * uiScale + ((card.compactEndpointWidth > 0
                            ? card.compactEndpointWidth : parent.width) - 28 * uiScale) * 1.5
        width: (card.compactEndpointWidth > 0 ? card.compactEndpointWidth : parent.width)
            - 28 * uiScale
        height: parent.height - y

        Text {
            width: parent.width
            text: card.displayTitle || (card.game
                ? (card.game.display_title_override || card.game.canonical_title || card.game.title) : "")
            color: card.focusedColor(card.luluPalette.primaryText)
            font.family: card.typography ? card.typography.interfaceFamily : "JetBrains Mono"
            font.weight: card.compact || card.compactEndpointWidth > 0 ? Font.Bold : Font.Normal
            layer.enabled: card.librarySurfaceMaterial
            layer.effect: MultiEffect {
                shadowEnabled: true
                shadowColor: "#000000"
                shadowOpacity: 0.35
                shadowBlur: 0.2
                shadowVerticalOffset: 1 * card.uiScale
            }
            font.pixelSize: card.typography
                ? card.typography.size("body", card.compactEndpointWidth > 0 ? 13 * 0.8
                    : (card.compact ? 13 * 0.8 : 16))
                : (card.compactEndpointWidth > 0 ? 13 * 0.8
                    : (card.compact ? 13 * 0.8 : 16)) * card.uiScale
            wrapMode: Text.WordWrap
            maximumLineCount: 2
            elide: Text.ElideRight
            horizontalAlignment: Text.AlignHCenter
            verticalAlignment: Text.AlignVCenter
            height: parent.height
        }
    }

}
