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

    QtObject {
        id: standaloneGuideModel
        property var guideActions: guideModel.actions
        property int guideSelection: guideModel.selection
        property bool guideConfirmationPending: guideModel.confirmationPending
        property string guideConfirmationAction: guideModel.confirmationAction
    }

    MudosGuidePanel {
        anchors.fill: parent
        guideModel: standaloneGuideModel
        luluPalette: luluPalette
        typography: typography
        uiScale: 1
        Component.onCompleted: console.info("GUIDE_MODEL_RENDER rows="
                                         + standaloneGuideModel.guideActions.length)
    }
}
