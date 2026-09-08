import QtQuick

Rectangle {
    id: card

    required property var game
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
    readonly property bool recentFocal: homeCard && focused
    readonly property string presentationGameId: String(game.game_id)
    readonly property real focalMargin: 30 * focalScale * uiScale
    readonly property real artworkHeight: height - 2 * focalMargin
    readonly property real artworkWidth: artworkHeight / 1.5
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
    color: recentFocal ? "#1d2a49" : (focused ? "#283761" : "#182540")
    border.color: focused ? "#e0c5ff" : "#455274"
    border.width: (focused ? 3 : 1) * uiScale
    clip: true

    GlassSurface {
        anchors.fill: parent
        visible: card.homeCard
        canonicalTexture: card.canonicalTexture
        canonicalSize: card.canonicalSize
        cornerRadius: card.radius
        useExplicitSceneGeometry: card.presentationState === "COMPACT"
        sceneOriginOverride: card.canonicalSceneOrigin
        sceneSizeOverride: Qt.size(card.width, card.height)
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

    Rectangle {
        id: artworkFrame
        x: recentFocal ? focalMargin : 14 * uiScale
        y: recentFocal ? focalMargin : 14 * uiScale
        width: recentFocal ? artworkWidth : parent.width - 28 * uiScale
        height: recentFocal ? artworkHeight : width * 1.5
        property real artworkRadius: recentFocal ? 18 * focalScale * uiScale : 10 * uiScale
        property real artworkBorderAlpha: 0.15
        radius: artworkRadius
        color: recentFocal ? "transparent" : "#10182b"
        clip: true

        Image {
            id: artworkSource
            anchors.fill: parent
            source: card.game.artwork_url
            fillMode: Image.PreserveAspectFit
            asynchronous: true
            visible: true
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
            property int diagnosticMode: 0
            opacity: card.focused ? 1 : 0.68
            fragmentShader: "shaders/card-rounded.frag.qsb"
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
            text: card.game.title
            color: "#f1f3fb"
            font.pixelSize: 34 * focalScale * card.uiScale
            wrapMode: Text.WordWrap
            maximumLineCount: 3
            elide: Text.ElideRight
        }

        Text {
            id: focalHistory
            visible: Number(card.game.last_played) > 0
            width: parent.width
            y: focalTitle.height + 22 * focalScale * card.uiScale
            text: "Last played " + Qt.formatDateTime(new Date(Number(card.game.last_played) * 1000), "d MMM yyyy")
            color: "#c5cee2"
            font.pixelSize: 17 * focalScale * card.uiScale
            elide: Text.ElideRight
        }

        Rectangle {
            id: playButton
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.bottom: parent.bottom
            height: 82 * focalScale * card.uiScale
            radius: 20 * focalScale * card.uiScale
            color: "#394b78"
            border.color: "#e0c5ff"
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
                color: "#f1e7ff"
                font.pixelSize: 28 * focalScale * card.uiScale
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
            text: card.game.title
            color: "#f1f3fb"
            font.pixelSize: (card.compact ? 14 : 16) * card.uiScale
            wrapMode: Text.WordWrap
            maximumLineCount: 2
            elide: Text.ElideRight
            horizontalAlignment: Text.AlignHCenter
            verticalAlignment: Text.AlignVCenter
            height: parent.height
        }
    }
}
