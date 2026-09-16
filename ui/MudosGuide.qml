import QtQuick
import QtQuick.Window

Window {
    id: root
    objectName: "mudosGuide"
    visible: false
    title: "Mudos Guide"
    flags: Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
    color: "transparent"
    width: 1920
    height: 1080

    property bool shellContext: guideModel.shellContext
    property bool confirmationPending: guideModel.confirmationPending
    property string confirmationAction: guideModel.confirmationAction
    property int delegateCreationCount: 0

    function resolvedGuideActions() {
        if (confirmationPending)
            return ["Cancel", confirmationAction]
        if (shellContext) {
            return ["Restart Mudos", "Reboot System", "Shut Down System"]
        }
        var actions = ["Reset Mudos"]
        if (guideModel.providerMenuAvailable)
            actions.push(guideModel.providerMenuLabel)
        if (guideModel.compatibilityModeAvailable)
            actions.push(guideModel.compatibilityMode
                ? "Switch to Gamepad Mode" : "Switch to Compatibility Mode")
        actions.push("Quit Current Application")
        return actions
    }

    LuluPalette {
        id: luluPalette
    }

    Loader {
        id: uiAudioLoader
        active: false
        source: "UiAudioEngine.qml"
        property string pendingEvent: ""
        onLoaded: {
            if (pendingEvent) {
                var event = pendingEvent
                pendingEvent = ""
                item.play(event)
            }
        }
    }

    Connections {
        target: guideModel
        function onAudioEventSerialChanged() {
            if (!uiAudioLoader.active) {
                uiAudioLoader.pendingEvent = guideModel.audioEvent
                uiAudioLoader.active = true
            } else if (uiAudioLoader.item) {
                uiAudioLoader.item.play(guideModel.audioEvent)
            } else {
                uiAudioLoader.pendingEvent = guideModel.audioEvent
            }
        }
    }

    Rectangle {
        anchors.centerIn: parent
        width: 520
        height: confirmationPending ? 250 : shellContext ? 250 : 310
        color: luluPalette.guideSurface
        border.color: luluPalette.guideBorder
        border.width: 2

        Text {
            x: 24
            y: 18
            text: confirmationPending ? "Confirm" : "Guide"
            color: luluPalette.primaryText
            font.pixelSize: 28
        }

        Column {
            x: 24
            y: 76
            spacing: 12
            Repeater {
                model: root.resolvedGuideActions()
                onCountChanged: console.log("MUDOS_GUIDE_VISIBLE_MODEL",
                                            "count", count,
                                            "delegateCreationCount", root.delegateCreationCount)
                onItemAdded: function(index, item) {
                    root.delegateCreationCount += 1
                    console.log("MUDOS_GUIDE_DELEGATE_CREATED",
                                "index", index,
                                "label", item ? item.children[0].text : "unknown",
                                "delegateCreationCount", root.delegateCreationCount)
                }
                delegate: Rectangle {
                    width: 472
                    height: 48
                    color: index === guideModel.selection ? luluPalette.guideBorder : luluPalette.guideItemSurface
                    Text {
                        anchors.fill: parent
                        anchors.leftMargin: 14
                        text: modelData
                        color: index === guideModel.selection ? luluPalette.guideSelectedText : luluPalette.primaryText
                        font.pixelSize: 18
                        verticalAlignment: Text.AlignVCenter
                    }
                    Component.onCompleted: console.log("MUDOS_GUIDE_DELEGATE_COMPONENT",
                                                       "index", index,
                                                       "label", modelData)
                }
            }
        }
    }
}
