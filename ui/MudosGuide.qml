import QtQuick
import QtQuick.Window

Window {
    id: root
    objectName: "mudosGuide"
    visible: true
    title: "Mudos Guide"
    flags: Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
    color: "transparent"
    width: 1920
    height: 1080

    LuluPalette {
        id: luluPalette
    }
    Typography {
        id: typography
    }

    MudosGuidePanel {
        anchors.fill: parent
        guideModel: guideModel
        luluPalette: luluPalette
        typography: typography
        uiScale: 1
    }
}
