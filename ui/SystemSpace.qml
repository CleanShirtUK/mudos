import QtQuick

Item {
    id: root
    property string category: "System"
    property var settings: []
    property int selectedIndex: 0
    property real uiScale: 1
    property var typography
    property var luluPalette
    property var canonicalTexture
    property var canonicalCoordinateRoot
    property size canonicalSize: Qt.size(1280, 720)
    property real expandedShellX: 0
    property real expandedShellY: 0
    property real expandedShellWidth: 0
    property real expandedShellHeight: 0
    property real expandedShellBottom: 0
    signal actionRequested(string key)
    signal interactionRequested()
    signal textInputRequested()
    property alias bluetoothInputValue: settingsPage.bluetoothInputValue
    property int visibleRows: 7
    property bool embedded: false
    property bool textInputFocusEnabled: true

    MudosSettingsPage {
        id: settingsPage
        anchors.fill: parent
        title: root.category
        rows: root.settings
        embedded: root.embedded
        textInputFocusEnabled: root.textInputFocusEnabled
        selectedIndex: root.selectedIndex
        uiScale: root.uiScale
        typography: root.typography
        luluPalette: root.luluPalette
        canonicalTexture: root.canonicalTexture
        canonicalCoordinateRoot: root.canonicalCoordinateRoot
        canonicalSize: root.canonicalSize
        expandedShellX: root.expandedShellX
        expandedShellY: root.expandedShellY
        expandedShellWidth: root.expandedShellWidth
        expandedShellHeight: root.expandedShellHeight
        expandedShellBottom: root.expandedShellBottom
        onRowActivated: {
            root.interactionRequested()
            root.actionRequested(root.settings[index].key)
        }
        onTextInputRequested: root.textInputRequested()
    }
}
