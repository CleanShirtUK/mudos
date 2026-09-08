import QtQuick

Rectangle {
    id: card

    property var game: null
    property bool focused: false
    property bool compact: false
    property bool showAction: false
    property bool homeCard: false
    property string presentationState: "COMPACT"
    property var canonicalTexture
    property var canonicalCoordinateRoot
    property size canonicalSize: Qt.size(1280, 720)
    property real focalScale: 1
    property real uiScale: 1
    property var typography
    property var luluPalette
    property string displayTitle: ""
    property string presentationId: ""
    property string symbolicArtwork: ""
    property bool identitySampling: false
    property point sceneOriginOverride: canonicalSceneOrigin
    property size sceneSizeOverride: Qt.size(width, height)
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
    readonly property real focalMargin: 30 * focalScale * uiScale
    readonly property real artworkHeight: height - 2 * focalMargin
    readonly property real artworkWidth: artworkHeight / 1.5
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
    color: card.stackedGlass ? luluPalette.transparent
        : (recentFocal ? luluPalette.glassTint : (focused ? luluPalette.focusedCardSurface : luluPalette.cardSurface))
    border.color: focused ? luluPalette.focusIndicator : luluPalette.glassBorder
    border.width: (focused ? 3 : 1) * uiScale
    clip: true

    GlassSurface {
        id: glassSurface
        anchors.fill: parent
        visible: card.homeCard
        canonicalTexture: card.canonicalTexture
        canonicalSize: card.canonicalSize
        cornerRadius: card.radius
        useExplicitSceneGeometry: card.presentationState === "COMPACT"
        sceneOriginOverride: card.sceneOriginOverride
        sceneSizeOverride: card.sceneSizeOverride
        identitySampling: card.identitySampling
        refractionPixels: 80 * card.uiScale
        dispersionIor: 0.0175
        diffusionPixels: 5 * card.uiScale
        transmission: 0.75
        bevelWidthPx: 3 * card.uiScale
        bulgeStrength: 100.0
        // Retained as a disabled experiment; scene-derived illumination is not material.
        sceneLightStrength: 0
        sceneLightPixels: 24
        edgeLightStrength: 0.10
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
        running: card.stackedGlass && card.stackedCoordinateRoot
        repeat: true
        onTriggered: {
            var origin = card.mapToItem(card.stackedCoordinateRoot, 0, 0)
            card.stackedPlayOrigin = Qt.vector2d(origin.x, origin.y)
        }
    }


    Rectangle {
        id: artworkFrame
        x: recentFocal ? focalMargin : 14 * uiScale
        y: recentFocal ? focalMargin : 14 * uiScale
        width: recentFocal ? artworkWidth : parent.width - 28 * uiScale
        height: recentFocal ? artworkHeight : width * 1.5
        property real artworkRadius: recentFocal ? 18 * focalScale * uiScale : 10 * uiScale
        property real artworkBorderAlpha: 0.15
        radius: artworkRadius
            color: recentFocal || card.symbolicArtwork || card.stackedGlass
                ? luluPalette.transparent : luluPalette.artworkSurface
        clip: true

        Image {
            id: artworkSource
            anchors.fill: parent
            source: card.game ? card.game.artwork_url : ""
            fillMode: Image.PreserveAspectFit
            asynchronous: true
            visible: !card.symbolicArtwork
        }

        ShaderEffectSource {
            id: artworkTexture
            anchors.fill: parent
            sourceItem: artworkSource
            hideSource: true
            visible: false
        }

        ShaderEffect {
            anchors.fill: parent
            property var source: artworkTexture
            property real cornerRadius: artworkFrame.artworkRadius / Math.min(width, height)
            property vector2d artworkSize: Qt.vector2d(width, height)
            property real borderWidthPx: card.uiScale
            property real borderAlpha: artworkFrame.artworkBorderAlpha
            property real focusBrightness: card.focusBrightness
            property int diagnosticMode: 0
            opacity: card.stackedGlass ? 1 : (card.focused ? 1 : 0.68)
            visible: !card.symbolicArtwork
            fragmentShader: "shaders/card-rounded.frag.qsb"
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
        visible: recentFocal
        x: focalMargin + artworkWidth + focalMargin
        y: focalMargin
        width: parent.width - x - focalMargin
        height: artworkHeight

        Text {
            id: focalTitle
            width: parent.width
            text: card.displayTitle || (card.game ? card.game.title : "")
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
            color: card.luluPalette.actionSurface
            border.color: card.luluPalette.focusIndicator
            border.width: 2 * card.uiScale

            PlayGlassSurface {
                anchors.fill: parent
                visible: card.recentFocal
                canonicalTexture: card.canonicalTexture
                canonicalSize: card.canonicalSize
                cardOrigin: card.canonicalTexture
                    ? Qt.vector2d(card.mapToItem(card.canonicalTexture, 0, 0).x,
                                  card.mapToItem(card.canonicalTexture, 0, 0).y)
                    : Qt.vector2d(0, 0)
                cardSize: Qt.size(card.width, card.height)
                cardRadius: card.radius
                playOrigin: Qt.vector2d(playButton.mapToItem(card, 0, 0).x,
                                        playButton.mapToItem(card, 0, 0).y)
                cardRefractionPixels: 80 * card.uiScale
                cardDiffusionPixels: 5 * card.uiScale
                cardBevelWidth: 3 * card.uiScale
                playRefractionPixels: 40 * card.uiScale
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
        visible: !recentFocal
        x: 14 * uiScale
        y: 14 * uiScale + (parent.width - 28 * uiScale) * 1.5
        width: parent.width - 28 * uiScale
        height: parent.height - y

        Text {
            width: parent.width
            text: card.displayTitle || (card.game ? card.game.title : "")
            color: card.focusedColor(card.luluPalette.primaryText)
            font.family: card.typography ? card.typography.interfaceFamily : "JetBrains Mono"
            font.pixelSize: card.typography
                ? card.typography.size("body", card.compact ? 14 * 0.8 : 16)
                : (card.compact ? 14 * 0.8 : 16) * card.uiScale
            wrapMode: Text.WordWrap
            maximumLineCount: 2
            elide: Text.ElideRight
            horizontalAlignment: Text.AlignHCenter
            verticalAlignment: Text.AlignVCenter
            height: parent.height
        }
    }

}
