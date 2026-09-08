import QtQuick

Rectangle {
    id: card

    required property var game
    property bool focused: false
    property bool compact: false
    property bool showAction: false
    property bool homeCard: false
    property real focalScale: 1
    readonly property bool recentFocal: homeCard && focused
    readonly property real focalMargin: 30 * focalScale
    readonly property real artworkHeight: height - 2 * focalMargin
    readonly property real artworkWidth: artworkHeight / 1.5

    implicitWidth: recentFocal ? 1100 : (compact ? 260 : 210)
    implicitHeight: recentFocal ? 560 : (compact ? 430 : 330)
    radius: recentFocal ? 28 * focalScale : (compact ? 16 : 18)
    color: recentFocal ? "#1d2a49" : (focused ? "#283761" : "#182540")
    border.color: focused ? "#e0c5ff" : "#455274"
    border.width: focused ? 3 : 1
    clip: true

    Rectangle {
        x: recentFocal ? focalMargin : 14
        y: recentFocal ? focalMargin : 14
        width: recentFocal ? artworkWidth : parent.width - 28
        height: recentFocal ? artworkHeight : width * 1.5
        radius: recentFocal ? 18 * focalScale : 0
        color: "#10182b"
        clip: recentFocal

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
        }

        ShaderEffect {
            anchors.fill: parent
            property var source: artworkTexture
            property real cornerRadius: recentFocal ? 18 * focalScale / Math.min(width, height) : 0
            opacity: card.focused ? 1 : 0.68
            fragmentShader: "\n                uniform sampler2D source;\n                uniform lowp float qt_Opacity;\n                uniform highp float cornerRadius;\n                varying highp vec2 qt_TexCoord0;\n                void main() {\n                    highp vec2 q = abs(qt_TexCoord0 - vec2(0.5)) - vec2(0.5 - cornerRadius);\n                    highp float distance = length(max(q, 0.0)) + min(max(q.x, q.y), 0.0) - cornerRadius;\n                    lowp float alpha = 1.0 - smoothstep(0.0, 0.002, distance);\n                    gl_FragColor = texture2D(source, qt_TexCoord0) * alpha * qt_Opacity;\n                }\n            "
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
            font.pixelSize: 34 * focalScale
            wrapMode: Text.WordWrap
            maximumLineCount: 3
            elide: Text.ElideRight
        }

        Text {
            id: focalHistory
            visible: Number(card.game.last_played) > 0
            width: parent.width
            y: focalTitle.height + 22 * focalScale
            text: "Last played " + Qt.formatDateTime(new Date(Number(card.game.last_played) * 1000), "d MMM yyyy")
            color: "#c5cee2"
            font.pixelSize: 17 * focalScale
            elide: Text.ElideRight
        }

        Rectangle {
            id: playButton
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.bottom: parent.bottom
            height: 82 * focalScale
            radius: 20 * focalScale
            color: "#394b78"
            border.color: "#e0c5ff"
            border.width: 2

            Text {
                anchors.centerIn: parent
                text: "A  Play"
                color: "#f1e7ff"
                font.pixelSize: 28 * focalScale
            }
        }
    }

    Column {
        visible: !recentFocal
        x: 14
        y: 14 + (parent.width - 28) * 1.5
        width: parent.width - 28
        height: parent.height - y

        Text {
            width: parent.width
            text: card.game.title
            color: "#f1f3fb"
            font.pixelSize: card.compact ? 14 : 16
            wrapMode: Text.WordWrap
            maximumLineCount: 2
            elide: card.compact ? Text.ElideNone : Text.ElideRight
            horizontalAlignment: Text.AlignHCenter
            verticalAlignment: Text.AlignVCenter
            height: parent.height
        }
    }
}
