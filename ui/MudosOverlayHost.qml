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

    Timer {
        interval: 1200
        running: root.visible
        repeat: false
        onTriggered: root.saveDiagnosticFrame(
            "/tmp/guide-" + displayUnderlay.glassMode + ".png")
    }

    MudosDisplayUnderlay {
        id: displayUnderlay
        width: frameSize.width > 0 ? frameSize.width : root.width
        height: frameSize.height > 0 ? frameSize.height : root.height
        // The provider is also a scene-graph item.  A nearly-zero item
        // opacity made its texture sample transparent in the external
        // window, even though the raw node itself was valid.
        opacity: 1
    }

    MudosSeparableBlur {
        id: separableBlur
        width: displayUnderlay.width
        height: displayUnderlay.height
        sourceItem: displayUnderlay
        sourceTextureSize: displayUnderlay.frameSize
        blurRadius: 1.5 * root.uiScale
        stage: displayUnderlay.glassMode === "horizontal" ? 1 : 2
        visible: displayUnderlay.glassMode !== "raw"
        opacity: 1
    }

    ShaderEffectSource {
        id: blurredUnderlay
        width: separableBlur.width
        height: separableBlur.height
        sourceItem: separableBlur
        textureSize: displayUnderlay.frameSize
        live: true
        visible: false
    }

    MudosGuidePanel {
        visible: root.guideModel.guideVisible && displayUnderlay.glassMode !== "raw"
        anchors.fill: parent
        guideModel: root.guideModel
        luluPalette: root.luluPalette
        displayUnderlay: displayUnderlay
        blurredUnderlay: blurredUnderlay
        glassMode: displayUnderlay.glassMode
        uiScale: root.uiScale
    }

    GameOptions {
        visible: root.game !== null && !root.guideModel.guideVisible
            && displayUnderlay.glassMode !== "raw"
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
