import QtQuick
import QtQuick.Window
import Mudos.Poc 1.0

MudosOverlayWindow {
    id: root
    visible: guideModel.guideVisible || game !== null
    property var guideModel
    property var game: null
    property string view: "menu"
    property int selectedIndex: 0
    property var results: []
    property string query: ""
    property string titleDraft: ""
    property string errorMessage: ""
    property bool busy: false
    property real uiScale: 1
    property var typography
    property var luluPalette
    signal gameActivated()
    signal gameBacked()
    signal gameMoved(int delta)
    signal queryEdited(string value)
    signal titleEdited(string value)

    MudosDisplayUnderlay {
        id: displayUnderlay
        width: frameSize.width > 0 ? frameSize.width : root.width
        height: frameSize.height > 0 ? frameSize.height : root.height
        opacity: displayUnderlay.diagnosticMode ? 1 : 0.0001
    }

    MudosGuidePanel {
        visible: root.guideModel.guideVisible && !displayUnderlay.diagnosticMode
        anchors.fill: parent
        guideModel: root.guideModel
        luluPalette: root.luluPalette
        displayUnderlay: displayUnderlay
        uiScale: root.uiScale
    }

    GameOptions {
        visible: root.game !== null && !root.guideModel.guideVisible
            && !displayUnderlay.diagnosticMode
        anchors.fill: parent
        game: root.game
        view: root.view
        selectedIndex: root.selectedIndex
        results: root.results
        query: root.query
        titleDraft: root.titleDraft
        errorMessage: root.errorMessage
        busy: root.busy
        uiScale: root.uiScale
        typography: root.typography
        luluPalette: root.luluPalette
        displayUnderlay: displayUnderlay
        onActivated: root.gameActivated()
        onBacked: root.gameBacked()
        onQueryEdited: root.queryEdited(value)
        onTitleEdited: root.titleEdited(value)
    }
}
