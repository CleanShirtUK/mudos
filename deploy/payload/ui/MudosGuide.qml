import QtQuick
import QtQuick.Window

Window {
    objectName: "mudosGuide"
    visible: false
    title: "Mudos Guide"
    flags: Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
    color: "transparent"
    width: 1920
    height: 1080

    Rectangle {
        anchors.centerIn: parent
        width: 520
        height: 310
        color: "#f70b1018"
        border.color: "#ff7e87ff"
        border.width: 2

        Text {
            x: 24
            y: 18
            text: "Guide"
            color: "#ffffffff"
            font.pixelSize: 28
        }

        Column {
            x: 24
            y: 76
            spacing: 12
            Repeater {
                model: {
                    var actions = ["Reset Mudos"]
                    if (guideModel.providerMenuAvailable)
                        actions.push(guideModel.providerMenuLabel)
                    if (guideModel.compatibilityModeAvailable)
                        actions.push(guideModel.compatibilityMode
                            ? "Switch to Gamepad Mode" : "Switch to Compatibility Mode")
                    actions.push("Quit Current Application")
                    return actions
                }
                delegate: Rectangle {
                    width: 472
                    height: 48
                    color: index === guideModel.selection ? "#ff7e87ff" : "#1affffff"
                    Text {
                        anchors.fill: parent
                        anchors.leftMargin: 14
                        text: modelData
                        color: index === guideModel.selection ? "#ff0b1018" : "#ffffffff"
                        font.pixelSize: 18
                        verticalAlignment: Text.AlignVCenter
                    }
                }
            }
        }
    }
}
