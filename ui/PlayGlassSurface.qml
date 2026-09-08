import QtQuick

Item {
    id: root

    property vector2d cardOrigin
    property var canonicalTexture
    property size canonicalSize: Qt.size(1280, 720)
    property size cardSize: Qt.size(1280, 720)
    property real cardRadius: 0
    property real cardIor: 1.08
    property real cardDepth: 0.32
    property real cardRefractionPixels: 80
    property real cardDispersionIor: 0.0175
    property real cardDiffusionPixels: 5
    property real cardTransmission: 0.75
    property real cardBevelWidth: 10
    property real cardBulgeStrength: 100
    property real cardEdgeLightStrength: 0.10
    property vector2d cardEdgeLightDirection: Qt.vector2d(1, -1)

    property vector2d playOrigin
    property real playIor: 1.08
    property real playDepth: 0.18
    property real playRefractionPixels: 40
    property real playRefractionBiasPx: 0
    property real playMaterialBiasPx: 0
    property real playDispersionIor: 0.0175
    property real playDiffusionPixels: 5
    property real playTransmission: 0.82
    property real playBulgeStrength: 20
    property real playBevelWidth: 0
    property real playEdgeLightStrength: 0
    property real focusBrightness: 1
    property int diagnosticMode: 0
    property string debugLabel: ""
    property var debugCoordinateRoot

    ShaderEffect {
        anchors.fill: parent
        fragmentShader: "shaders/play-stacked-glass.frag.qsb"
        property var source: root.canonicalTexture
        property vector2d u_canonicalSize: Qt.vector2d(root.canonicalSize.width, root.canonicalSize.height)
        property vector2d u_cardOrigin: root.cardOrigin
        property vector2d u_cardSize: Qt.vector2d(root.cardSize.width, root.cardSize.height)
        property real u_cardRadius: root.cardRadius
        property real u_cardIor: root.cardIor
        property real u_cardDepth: root.cardDepth
        property real u_cardRefractionPixels: root.cardRefractionPixels
        property real u_cardDispersionIor: root.cardDispersionIor
        property real u_cardDiffusionPixels: root.cardDiffusionPixels
        property real u_cardTransmission: root.cardTransmission
        property real u_cardBevelWidth: root.cardBevelWidth
        property real u_cardBulgeStrength: root.cardBulgeStrength
        property real u_cardEdgeLightStrength: root.cardEdgeLightStrength
        property vector2d u_cardEdgeLightDirection: root.cardEdgeLightDirection
        property vector2d u_playOrigin: root.playOrigin
        property vector2d u_playSize: Qt.vector2d(root.width, root.height)
        property real u_playRadius: root.parent ? root.parent.radius : 0
        property real u_playIor: root.playIor
        property real u_playDepth: root.playDepth
        property real u_playRefractionPixels: root.playRefractionPixels
        property real u_playRefractionBiasPx: root.playRefractionBiasPx
        property real u_playMaterialBiasPx: root.playMaterialBiasPx
        property real u_playDispersionIor: root.playDispersionIor
        property real u_playDiffusionPixels: root.playDiffusionPixels
        property real u_playTransmission: root.playTransmission
        property real u_playBulgeStrength: root.playBulgeStrength
        property real u_playBevelWidth: root.playBevelWidth
        property real u_playEdgeLightStrength: root.playEdgeLightStrength
        property real u_focusBrightness: root.focusBrightness
        property int u_diagnostic: root.diagnosticMode
    }

    Timer {
        interval: 1500
        running: root.debugLabel !== ""
        repeat: false
        onTriggered: {
            var origin = root.cardOrigin
            var p = root.playOrigin
            var w = root.width
            var h = root.height
            console.log("PLAY_MAPPING_PROBE", root.debugLabel,
                        "playOrigin", p.x, p.y, "playSize", w, h,
                        "cardOrigin", origin.x, origin.y,
                        "cardSize", root.cardSize.width, root.cardSize.height,
                        "underlayTL", origin.x + p.x, origin.y + p.y,
                        "underlayC", origin.x + p.x + w * 0.5, origin.y + p.y + h * 0.5,
                        "underlayTR", origin.x + p.x + w, origin.y + p.y,
                        "underlayBL", origin.x + p.x, origin.y + p.y + h,
                        "underlayBR", origin.x + p.x + w, origin.y + p.y + h)
        }
    }

}
