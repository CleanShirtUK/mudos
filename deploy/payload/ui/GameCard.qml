import QtQuick
import QtQuick.Effects

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
    property var canonicalTexture
    property var canonicalCoordinateRoot
    property size canonicalSize: Qt.size(1280, 720)
    property real focalScale: 1
    property real uiScale: 1
    property var typography
    property var luluPalette
    property string displayTitle: ""
    property url artworkSource: ""
    property string artworkRole: "raster"
    // The supplied fallback asset belongs at this normal artwork-pipeline path.
    property url fallbackArtworkSource: Qt.resolvedUrl("artwork/fallback.jpg")
    property string presentationId: ""
    property string symbolicArtwork: ""
    property bool identitySampling: false
    property bool liveSceneCoordinates: false
    property bool neutralOptics: false
    // Focal diagnostic stages: 0 neutral, then transmission, diffusion, bevel,
    // bulge, refraction, dispersion, and edge lighting.
    property int opticsStage: -1
    property real presentationProgress: recentFocal ? 1 : 0
    property real focalChromeOpacity: presentationProgress
    property real presentationContentOpacity: 1
    property real compactTitleOpacity: 1
    property real selectionProgress: focused ? 1 : 0
    property real compactEndpointWidth: 0
    property point sceneOriginOverride: canonicalSceneOrigin
    property size sceneSizeOverride: Qt.size(width, height)
    property point liveSceneOrigin: Qt.point(0, 0)
    property vector2d livePlayOrigin: Qt.vector2d(0, 0)
    property alias actualGlassSurface: glassSurface
    property bool stackedGlass: false
    property var stackedCoordinateRoot
    property vector2d stackedCardOrigin: Qt.vector2d(0, 0)
    property vector2d stackedCardSize: Qt.vector2d(0, 0)
    property vector2d stackedPlayOrigin: Qt.vector2d(0, 0)
    property real focusBrightness: 1
    property real stackedCardBevelWidth: 3 * uiScale
    property real stackedCardBulgeStrength: 0
    property real stackedCardRefractionPixels: 80 * uiScale
    property real stackedCardDispersionIor: 0.0175
    property real stackedPlayRefractionPixels: 40 * uiScale
    property real stackedPlayDispersionIor: 0.0175
    property real stackedPlayBulgeStrength: 20
    property real stackedPlayBevelWidth: 0
    property real stackedPlayEdgeLightStrength: 0
    readonly property bool recentFocal: homeCard && focused
    readonly property string presentationGameId: presentationId || (game ? String(game.game_id) : "")
    readonly property url displayedArtworkSource: card.artworkSource ? card.artworkSource
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
        var origin = canonicalCoordinateRoot
            ? card.mapToItem(canonicalCoordinateRoot, 0, 0)
            : Qt.point(0, 0)
        // mapToItem() is not reactive to ancestor layout changes by itself.
        var layoutDependency = card.x + card.y + card.width + card.height
        return Qt.point(origin.x + layoutDependency * 0, origin.y + layoutDependency * 0)
    }

    implicitWidth: recentFocal ? 1100 * uiScale : (compact ? 260 : 210) * uiScale
    implicitHeight: recentFocal ? 560 * uiScale : (compact ? 430 : 330) * uiScale
    radius: recentFocal ? 28 * focalScale * uiScale : (compact ? 16 : 18) * uiScale
    color: card.stackedGlass || card.librarySurfaceMaterial ? luluPalette.transparent
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

    GlassSurface {
        id: glassSurface
        anchors.fill: parent
        visible: card.homeCard && card.glassVisible
        debugLabel: ""
        debugCoordinateRoot: card.canonicalCoordinateRoot
        canonicalTexture: card.canonicalTexture
        canonicalSize: card.canonicalSize
        cornerRadius: card.radius
        useExplicitSceneGeometry: card.presentationState === "COMPACT"
            || card.identitySampling || card.liveSceneCoordinates
        sceneOriginOverride: card.identitySampling || card.liveSceneCoordinates
            ? card.liveSceneOrigin : card.sceneOriginOverride
        sceneSizeOverride: card.identitySampling || card.liveSceneCoordinates
            ? Qt.size(card.width, card.height) : card.sceneSizeOverride
        identitySampling: false
        refractionPixels: card.opticsStage >= 0 && card.opticsStage < 5 ? 0 : 80 * card.uiScale
        dispersionIor: card.opticsStage >= 0 && card.opticsStage < 6 ? 0 : 0.0175
        diffusionPixels: card.opticsStage >= 0 && card.opticsStage < 2 ? 0 : 5 * card.uiScale
        transmission: card.librarySurfaceMaterial ? 1
            : (card.opticsStage >= 0 && card.opticsStage < 1 ? 1 : 0.75)
        bevelWidthPx: card.opticsStage >= 0 && card.opticsStage < 3 ? 0 : 3 * card.uiScale
        bulgeStrength: card.opticsStage >= 0 && card.opticsStage < 4 ? 0 : 100.0
        // Retained as a disabled experiment; scene-derived illumination is not material.
        sceneLightStrength: 0
        sceneLightPixels: 24
        edgeLightStrength: card.opticsStage >= 0 && card.opticsStage < 7 ? 0 : 0.10
        edgeLightDirection: Qt.vector2d(1, -1)
        diagnosticMode: 0
    }

    PlayGlassSurface {
        anchors.fill: parent
        visible: card.stackedGlass
        canonicalTexture: card.canonicalTexture
        canonicalSize: card.canonicalSize
        cardOrigin: card.stackedCardOrigin
        cardSize: Qt.size(card.stackedCardSize.x, card.stackedCardSize.y)
        cardRadius: 28 * card.uiScale
        cardRefractionPixels: card.stackedCardRefractionPixels
        cardDispersionIor: card.stackedCardDispersionIor
        cardDiffusionPixels: 5 * card.uiScale
        cardTransmission: 0.75
        cardBevelWidth: card.stackedCardBevelWidth
        cardBulgeStrength: card.stackedCardBulgeStrength
        cardEdgeLightStrength: 0.10
        cardEdgeLightDirection: Qt.vector2d(1, -1)
        playOrigin: card.stackedPlayOrigin
        playRefractionPixels: card.stackedPlayRefractionPixels
        playDispersionIor: card.stackedPlayDispersionIor
        playDiffusionPixels: 5 * card.uiScale
        playTransmission: 0.82
        playBulgeStrength: card.stackedPlayBulgeStrength
        playBevelWidth: card.stackedPlayBevelWidth
        playEdgeLightStrength: card.stackedPlayEdgeLightStrength
        focusBrightness: card.focusBrightness
    }

    Timer {
        interval: 16
        running: (card.stackedGlass || card.identitySampling || card.liveSceneCoordinates)
            && card.canonicalCoordinateRoot
        repeat: true
        onTriggered: {
            if (card.stackedGlass) {
                var stackedOrigin = card.mapToItem(card.stackedCoordinateRoot, 0, 0)
                card.stackedPlayOrigin = Qt.vector2d(stackedOrigin.x, stackedOrigin.y)
            }
            if (card.identitySampling || card.liveSceneCoordinates)
                card.liveSceneOrigin = card.actualGlassSurface.mapToItem(
                    card.canonicalCoordinateRoot, 0, 0)
            if (card.presentationProgress > 0) {
                var playOrigin = playButton.mapToItem(card, 0, 0)
                card.livePlayOrigin = Qt.vector2d(playOrigin.x, playOrigin.y)
            }
        }
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
            color: recentFocal || card.stackedGlass
                ? luluPalette.transparent : luluPalette.artworkSurface
        clip: true

        Image {
            id: artworkSource
            anchors.fill: parent
            source: card.displayedArtworkSource
            fillMode: Image.PreserveAspectFit
            asynchronous: true
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
            property int diagnosticMode: 0
            opacity: card.stackedGlass ? 1 : (card.focused ? 1 : 0.68)
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
            font.family: card.typography ? card.typography.displayFamily : "Zalando Sans Condensed Black"
            font.weight: card.typography ? card.typography.displayWeight : Font.Black
            font.pixelSize: card.typography ? card.typography.size("display", 34 * focalScale) : 34 * focalScale * card.uiScale
            wrapMode: Text.WordWrap
            maximumLineCount: 3
            elide: Text.ElideRight
        }

        Text {
            id: focalHistory
            visible: card.game && Number(card.game.last_played) > 0
            width: parent.width
            y: focalTitle.height + 22 * focalScale * card.uiScale
            text: card.game ? "Last played " + Qt.formatDateTime(new Date(Number(card.game.last_played) * 1000), "d MMM yyyy") : ""
            color: card.focusedColor(card.luluPalette.secondaryText)
            font.family: card.typography ? card.typography.interfaceFamily : "JetBrains Mono"
            font.pixelSize: card.typography ? card.typography.size("secondary", 17 * focalScale) : 17 * focalScale * card.uiScale
            elide: Text.ElideRight
        }

        Rectangle {
            id: playButton
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.bottom: parent.bottom
            height: 82 * focalScale * card.uiScale
            radius: 20 * focalScale * card.uiScale
            color: card.presentationProgress > 0 && card.presentationProgress < 1
                ? card.luluPalette.transparent : card.luluPalette.actionSurface
            border.color: card.luluPalette.focusIndicator
            border.width: 2 * card.uiScale

            PlayGlassSurface {
                anchors.fill: parent
                visible: card.focalChromeOpacity > 0
                canonicalTexture: card.canonicalTexture
                canonicalSize: card.canonicalSize
                cardOrigin: card.canonicalTexture
                    ? Qt.vector2d(card.mapToItem(card.canonicalTexture, 0, 0).x,
                                  card.mapToItem(card.canonicalTexture, 0, 0).y)
                    : Qt.vector2d(0, 0)
                cardSize: Qt.size(card.width, card.height)
                cardRadius: card.radius
                 playOrigin: card.livePlayOrigin
                cardRefractionPixels: 80 * card.uiScale
                cardDiffusionPixels: 5 * card.uiScale
                 cardBevelWidth: 3 * card.uiScale
                 playRefractionPixels: 40 * card.uiScale
                 playRefractionBiasPx: 100 * card.uiScale
                 playMaterialBiasPx: 100 * card.uiScale
                 playDispersionIor: 0
                 playDiffusionPixels: 5 * card.uiScale
                 diagnosticMode: 0
            }

            Text {
                anchors.centerIn: parent
                text: "A  Play"
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
            font.pixelSize: card.typography
                ? card.typography.size("body", card.compactEndpointWidth > 0 ? 14 * 0.8
                    : (card.compact ? 14 * 0.8 : 16))
                : (card.compactEndpointWidth > 0 ? 14 * 0.8
                    : (card.compact ? 14 * 0.8 : 16)) * card.uiScale
            wrapMode: Text.WordWrap
            maximumLineCount: 2
            elide: Text.ElideRight
            horizontalAlignment: Text.AlignHCenter
            verticalAlignment: Text.AlignVCenter
            height: parent.height
        }
    }

}
