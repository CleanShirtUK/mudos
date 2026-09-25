import QtQuick

Item {
    id: root
    property var networkData: ({available: false, wifi_enabled: false, state: "unavailable",
                          current: null, networks: [], error: ""})
    property int selectedIndex: 0
    property bool credentialView: false
    property string selectedSsid: ""
    property string password: ""
    property string message: ""
    property bool onboardingMode: false
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
    signal operationRequested(string action, string ssid, string password)
    signal backRequested()

    function rows() {
        var result = [{label: "Wi-Fi", value: networkData.wifi_enabled ? "On" : "Off", action: "toggle"}]
        result.push({label: "Current connection", value: networkData.current ? networkData.current.ssid : "None", action: "current"})
        for (var network of (networkData.networks || []))
            result.push({label: network.ssid, value: (network.secured ? "Secured" : "Open")
                         + " · " + network.strength + "%"
                         + (network.connected ? " · Connected" : ""), action: "network", network: network})
        for (var saved of (networkData.known || []))
            result.push({label: "Forget " + saved, value: "Saved", action: "forget", ssid: saved})
        if (!onboardingMode)
            result.push({label: "Back", value: "", action: "back"})
        return result
    }

    function activate() {
        if (credentialView) {
            if (password.length > 0)
                operationRequested("connect", selectedSsid, password)
            return
        }
        var row = rows()[selectedIndex]
        if (!row) return
        if (row.action === "toggle")
            operationRequested("wifi", "", networkData.wifi_enabled ? "false" : "true")
        else if (row.action === "current" && networkData.current)
            operationRequested("disconnect", "", "")
        else if (row.action === "network") {
            selectedSsid = row.network.ssid
            if (row.network.secured && !row.network.known) {
                credentialView = true
                password = ""
                passwordInput.forceActiveFocus()
                operationRequested("keyboard-show", "", "")
            } else {
                operationRequested("connect", selectedSsid, "")
            }
        } else if (row.action === "forget")
            operationRequested("forget", row.ssid, "")
        else if (row.action === "back")
            backRequested()
    }

    function move(delta) {
        if (credentialView) return
        selectedIndex = Math.max(0, Math.min(rows().length - 1, selectedIndex + delta))
    }

    // Showing the separate OSK overlay can temporarily take X focus. Reclaim
    // the text target after the overlay has appeared so its injected keys land
    // in this password field without a mouse click on the shell.
    Timer {
        interval: 300
        repeat: true
        running: root.credentialView
        onTriggered: passwordInput.forceActiveFocus()
    }

    MudosSettingsPage {
        anchors.fill: parent
        title: root.onboardingMode ? "CONNECT TO WI-FI" : "INTERNET"
        rows: root.rows()
        selectedIndex: root.selectedIndex
        rowsVisible: !root.credentialView
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
        footerText: root.message || (root.onboardingMode
                                     ? "Choose a network and press A to connect. Back stays in required onboarding."
                                     : root.networkData.error)
        onRowActivated: {
            root.selectedIndex = index
            root.activate()
        }
    }
    Rectangle {
        visible: root.credentialView
        x: root.expandedShellX + 44 * root.uiScale
        y: root.expandedShellY + 110 * root.uiScale
        width: root.expandedShellWidth - 88 * root.uiScale
        height: 220 * root.uiScale
        color: luluPalette.cardSurface; radius: 10 * root.uiScale
        Text { x: 18 * root.uiScale; y: 18 * root.uiScale; text: "Password for " + root.selectedSsid
            color: luluPalette.primaryText; font.family: typography.interfaceFamily
            font.pixelSize: typography.size("body", 18) }
        TextInput { id: passwordInput; x: 18 * root.uiScale; y: 72 * root.uiScale
            width: parent.width - 36 * root.uiScale; height: 54 * root.uiScale
            echoMode: TextInput.Password; text: root.password
            onTextChanged: root.password = text
            color: luluPalette.primaryText; font.family: typography.interfaceFamily
            font.pixelSize: typography.size("body", 22)
            Keys.onReturnPressed: root.activate() }
        Text { x: 18 * root.uiScale; y: 145 * root.uiScale; text: "A: Connect   B: Cancel"
            color: luluPalette.secondaryText; font.family: typography.interfaceFamily
            font.pixelSize: typography.size("body", 16) }
    }
}
