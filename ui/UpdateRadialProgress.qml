import QtQuick

Item {
    id: root
    property var luluPalette
    property var typography
    property real uiScale: 1
    property real progress: 0
    property bool progressKnown: false
    property bool indeterminate: !progressKnown
    property string stage: "Updating"
    property bool animationEnabled: true
    readonly property real ringWidth: Math.max(3 * uiScale, width * 0.065)

    function stageLabel(value) {
        var text = String(value || "").toLowerCase()
        if (text.indexOf("verif") >= 0) return "Verifying"
        if (text.indexOf("apply") >= 0 || text.indexOf("install") >= 0 || text.indexOf("moving") >= 0)
            return "Applying"
        if (text.indexOf("final") >= 0) return "Finalising"
        if (text.indexOf("download") >= 0) return "Downloading"
        if (text.indexOf("queued") >= 0) return "Queued"
        return "Updating"
    }

    NumberAnimation on rotation {
        from: 0
        to: 360
        duration: 1400
        loops: Animation.Infinite
        running: root.visible && root.indeterminate && root.animationEnabled
    }

    Canvas {
        id: ring
        anchors.fill: parent
        onPaint: {
            var ctx = getContext("2d")
            ctx.reset()
            var side = Math.min(width, height)
            var radius = side * 0.39
            var line = root.ringWidth
            var cx = width / 2
            var cy = height / 2
            ctx.lineWidth = line
            ctx.lineCap = "round"
            ctx.strokeStyle = root.luluPalette ? root.luluPalette.glassBorder : "#ffffff55"
            ctx.beginPath()
            ctx.arc(cx, cy, radius, 0, Math.PI * 2)
            ctx.stroke()
            ctx.strokeStyle = root.luluPalette ? root.luluPalette.focusIndicator : "#8fcfff"
            ctx.beginPath()
            var sweep = root.indeterminate ? Math.PI * 0.78
                : Math.PI * 2 * Math.max(0, Math.min(1, root.progress))
            ctx.arc(cx, cy, radius, -Math.PI / 2, -Math.PI / 2 + sweep)
            ctx.stroke()
        }
    }

    Text {
        anchors.centerIn: parent
        visible: root.progressKnown && !root.indeterminate
        text: Math.round(Math.max(0, Math.min(1, root.progress)) * 100) + "%"
        color: root.luluPalette ? root.luluPalette.primaryText : "white"
        font.family: root.typography ? root.typography.interfaceFamily : "sans-serif"
        font.pixelSize: root.typography ? root.typography.size("control", 15 * root.uiScale) : 15 * root.uiScale
        font.bold: true
    }

    Rectangle {
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.top: parent.bottom
        anchors.topMargin: 5 * root.uiScale
        width: Math.min(parent.width * 1.6, label.implicitWidth + 16 * root.uiScale)
        height: label.implicitHeight + 8 * root.uiScale
        radius: root.luluPalette ? root.luluPalette.radius("row", height / 2, root.uiScale) : height / 2
        color: root.luluPalette ? root.luluPalette.launchOverlaySurface : "#cc101018"
        Text {
            id: label
            anchors.centerIn: parent
            text: root.stageLabel(root.stage)
            color: root.luluPalette ? root.luluPalette.primaryText : "white"
            font.family: root.typography ? root.typography.interfaceFamily : "sans-serif"
            font.pixelSize: root.typography ? root.typography.size("hint", 11 * root.uiScale) : 11 * root.uiScale
            elide: Text.ElideRight
        }
    }

    onProgressChanged: ring.requestPaint()
    onProgressKnownChanged: ring.requestPaint()
    onIndeterminateChanged: ring.requestPaint()
    onRingWidthChanged: ring.requestPaint()
    Component.onCompleted: ring.requestPaint()
}
