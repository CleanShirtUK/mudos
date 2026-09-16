import QtQuick
import QtQuick.Window
import Mudos.Poc 1.0

Window {
    id: root
    visible: true
    width: 1920
    height: 1080
    color: "#090d18"
    title: "Mudos native glass POC"
    property int stateIndex: 0
    property var names: ["stationary", "translate X/Y", "animated translation", "resize width", "resize while moving", "translated parent", "nested translated parents", "scaled ancestor", "clipped ancestor", "64 px capture padding", "composed-pane capture", "directional motion blur", "focal interpolation"]
    property rect canonicalRect: Qt.rect(190, 140, 1540, 800)
    property size canonicalSize: Qt.size(1920, 1080)

    function controllerLeft() {
        stateIndex = (stateIndex + names.length - 1) % names.length
    }
    function controllerRight() {
        stateIndex = (stateIndex + 1) % names.length
    }
    function activate() {
        stateIndex = stateIndex === 2 ? 0 : 2
    }
    function openSelectedGameOptions() {
        newGlass.dumpMapping()
        console.log("MUDOS_GLASS_POC", names[stateIndex], "pane", pane.x, pane.y, pane.width, pane.height)
    }

    OrbitBackdrop { id: orbit; anchors.fill: parent; shaderCanvas: Qt.vector2d(1920, 1080) }
    ShaderEffectSource {
        id: orbitTexture
        sourceItem: orbit
        sourceRect: Qt.rect(0, 0, 1920, 1080)
        textureSize: Qt.size(1920, 1080)
        live: true
        visible: false
    }

    Item {
        id: ancestor
        anchors.fill: parent
        x: root.stateIndex === 5 ? 90 : 0
        y: root.stateIndex === 5 ? 40 : 0
        scale: root.stateIndex === 7 ? 0.9 : 1
        clip: root.stateIndex >= 8
        Item {
            id: nested
            x: root.stateIndex === 6 ? 120 : 0
            y: root.stateIndex === 6 ? 70 : 0
            Rectangle {
                id: pane
                x: root.stateIndex >= 1 && root.stateIndex <= 4 ? 120 : 0
                y: root.stateIndex >= 1 && root.stateIndex <= 4 ? 50 : 0
                width: root.stateIndex === 3 || root.stateIndex === 4 || root.stateIndex === 12 ? 1100 : 1280
                height: 500
                color: "#14203a"
                radius: 24
                border.color: "#7189d6"
                border.width: 2
                Row {
                    anchors.centerIn: parent
                    spacing: 36
                    GlassSurface {
                        id: oldGlass
                        width: 540; height: 300
                        canonicalTexture: orbitTexture
                        canonicalSize: root.canonicalSize
                        useExplicitSceneGeometry: true
                        sceneOriginOverride: Qt.point(root.canonicalRect.x, root.canonicalRect.y)
                        sceneSizeOverride: Qt.size(root.canonicalRect.width, root.canonicalRect.height)
                        cornerRadius: 28
                        transparentOutsideMask: true
                    }
                    MudosGlassItem {
                        id: newGlass
                        width: 540; height: 300
                        backdrop: orbitTexture
                        canonicalSize: root.canonicalSize
                        canonicalRect: root.canonicalRect
                        cornerRadius: 28
                        transparentOutsideMask: true
                    }
                }
            }
            DirectionalMotionBlur {
                id: directionalBlur
                x: pane.x - 64
                y: pane.y - 64
                width: pane.width + 128
                height: pane.height + 128
                sourceItem: pane
                sourceRect: Qt.rect(0, 0, pane.width, pane.height)
                blurPixels: 18
                active: root.stateIndex === 11
                visible: active
            }
        }
    }

    // Capture boundaries used by the composition states. They are deliberately
    // outside both glass items; canonicalRect remains unchanged.
    ShaderEffectSource {
        id: composedPaneCapture
        sourceItem: pane
        sourceRect: root.stateIndex >= 9
            ? Qt.rect(-64, -64, pane.width + 128, pane.height + 128)
            : Qt.rect(0, 0, pane.width, pane.height)
        textureSize: root.stateIndex >= 9
            ? Qt.size(Math.max(1, pane.width + 128), Math.max(1, pane.height + 128))
            : Qt.size(Math.max(1, pane.width), Math.max(1, pane.height))
        live: root.stateIndex >= 9
        visible: false
    }

    Text {
        anchors.left: parent.left; anchors.top: parent.top; anchors.margins: 28
        color: "white"; font.pixelSize: 22
        text: "GLASS POC  " + (root.stateIndex + 1) + "/" + root.names.length + "  " + root.names[root.stateIndex]
    }
    NumberAnimation {
        target: pane; property: "x"
        from: 20; to: 420; duration: 2600; loops: Animation.Infinite
        running: root.stateIndex === 2 || root.stateIndex === 4 || root.stateIndex === 12
        easing.type: Easing.InOutSine
    }
    NumberAnimation {
        target: pane; property: "width"
        from: 900; to: 1320; duration: 2600; loops: Animation.Infinite
        running: root.stateIndex === 4 || root.stateIndex === 12
        easing.type: Easing.InOutSine
    }
    Text {
        anchors.right: parent.right; anchors.top: parent.top; anchors.margins: 28
        color: "#cbd7ff"; font.pixelSize: 17; horizontalAlignment: Text.AlignRight
        text: "OLD GlassSurface       NEW MudosGlassItem\nD-pad ◀/▶ state   A animated   X diagnostics\ncanonical UV: (0.099,0.130)  (0.500,0.500)  (0.901,0.870)"
    }
    FocusScope {
        id: keys
        anchors.fill: parent
        focus: true
        Keys.onLeftPressed: root.stateIndex = (root.stateIndex + root.names.length - 1) % root.names.length
        Keys.onRightPressed: root.stateIndex = (root.stateIndex + 1) % root.names.length
        Keys.onSpacePressed: root.stateIndex = root.stateIndex === 6 ? 0 : 6
        Keys.onPressed: function(event) {
            if (event.key === Qt.Key_D) {
                newGlass.dumpMapping()
                console.log("MUDOS_GLASS_POC", root.names[root.stateIndex], "pane", pane.x, pane.y, pane.width, pane.height)
                event.accepted = true
            }
        }
    }

    Connections {
        target: controllerBridge
        function onValueChanged(key, value) {
            if (key === "action" && value === "left")
                root.stateIndex = (root.stateIndex + root.names.length - 1) % root.names.length
            else if (key === "action" && value === "right")
                root.stateIndex = (root.stateIndex + 1) % root.names.length
            else if (key === "action" && value === "confirm")
                root.stateIndex = root.stateIndex === 2 ? 0 : 2
            else if (key === "action" && value === "options") {
                newGlass.dumpMapping()
                console.log("MUDOS_GLASS_POC", root.names[root.stateIndex],
                            "pane", pane.x, pane.y, pane.width, pane.height)
            }
        }
    }
}
