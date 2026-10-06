import QtQuick
import QtQuick.Controls

Item {
    id: root
    property bool online: false
    property bool setupCompleted: false
    property bool networkAdapterAvailable: true
    property real uiScale: 1
    property var typography
    property var luluPalette
    property int selectedAction: 0
    readonly property int actionCount: online ? 2 : (networkAdapterAvailable ? 3 : 2)
    onOnlineChanged: selectedAction = 0
    onNetworkAdapterAvailableChanged: selectedAction = 0
    signal openNetworkSettings()
    signal continueToHome()
    signal setUpLocally()

    function move(delta) {
        selectedAction = Math.max(0, Math.min(actionCount - 1, selectedAction + delta))
    }

    function activate() {
        if (online) {
            if (selectedAction === 0) setUpLocally()
            else continueToHome()
        } else if (networkAdapterAvailable) {
            if (selectedAction === 0) openNetworkSettings()
            else if (selectedAction === 1) setUpLocally()
            else continueToHome()
        } else if (selectedAction === 0) {
            setUpLocally()
        } else {
            continueToHome()
        }
    }

    function actionLabel(index) {
        if (online)
            return index === 0 ? "Set Up Locally" : "Continue to Home"
        if (networkAdapterAvailable)
            return ["Open Wi-Fi Settings", "Continue to Setup", "Continue to Home"][index]
        return ["Continue to Setup", "Continue to Home"][index]
    }

    anchors.fill: parent
    Rectangle {
        anchors.fill: parent
        color: root.luluPalette ? root.luluPalette.backdrop : "#10131a"
    }
    Column {
        anchors.centerIn: parent
        width: Math.min(parent.width - 2 * 56 * root.uiScale, 1040 * root.uiScale)
        spacing: 22 * root.uiScale
        Text {
            text: root.online ? "Welcome to Mudos" : "Connect to the internet"
            color: root.luluPalette ? root.luluPalette.primaryText : "white"
            font.family: root.typography ? root.typography.displayFamily : "sans-serif"
            font.pixelSize: 42 * root.uiScale
            font.weight: Font.Bold
        }
        Text {
            width: parent.width
            wrapMode: Text.WordWrap
            color: root.luluPalette ? root.luluPalette.secondaryText : "#cbd2df"
            font.pixelSize: 20 * root.uiScale
            text: root.online
                ? "Scan the QR code or open http://mudos.local/setup to choose providers and configure Mudos. You can also continue on this device."
                : root.networkAdapterAvailable
                    ? "Mudos needs a network connection to download providers and validate online integrations. Connect using Wi-Fi, then return here."
                    : "No usable Wi-Fi adapter is available. Connect Ethernet or another network interface, or continue offline and configure Mudos later at http://mudos.local/setup."
        }
        Row {
            visible: root.online
            spacing: 32 * root.uiScale
            Image {
                width: 228 * root.uiScale
                height: width
                source: "http://127.0.0.1/setup/qr.png"
                cache: false
                fillMode: Image.PreserveAspectFit
                Rectangle { anchors.fill: parent; z: -1; color: "white"; radius: root.luluPalette ? root.luluPalette.radius("media", 8 * root.uiScale) : 8 * root.uiScale }
            }
            Column {
                anchors.verticalCenter: parent.verticalCenter
                spacing: 18 * root.uiScale
                Text {
                    text: "http://mudos.local/setup"
                    color: root.luluPalette ? root.luluPalette.primaryText : "white"
                    font.pixelSize: 30 * root.uiScale
                    font.bold: true
                }
                Text { text: "A: " + root.actionLabel(root.selectedAction) + "    D-pad: Choose action"; color: root.luluPalette ? root.luluPalette.secondaryText : "#cbd2df"; font.pixelSize: 16 * root.uiScale }
                Repeater {
                    model: root.actionCount
                    delegate: Button {
                        required property int index
                        objectName: "onboardingOnlineAction" + index
                        text: root.actionLabel(index)
                        highlighted: index === root.selectedAction
                        implicitWidth: 310 * root.uiScale
                        implicitHeight: 58 * root.uiScale
                        leftPadding: 22 * root.uiScale
                        rightPadding: 22 * root.uiScale
                        font.family: root.typography ? root.typography.interfaceFamily : "sans-serif"
                        font.pixelSize: 20 * root.uiScale
                        font.bold: true
                    background: Rectangle {
                            radius: root.luluPalette ? root.luluPalette.radius("row", 12 * root.uiScale) : 12 * root.uiScale
                            color: index === root.selectedAction
                                ? (root.luluPalette ? root.luluPalette.focusedCardSurface : "#8ab4ff")
                                : (root.luluPalette ? root.luluPalette.cardSurface : "#242d3a")
                            border.width: index === root.selectedAction ? 3 : 1
                            border.color: root.luluPalette ? root.luluPalette.focusIndicator : "#8ab4ff"
                            MudosChromeFrame { anchors.fill: parent; luluPalette: root.luluPalette; uiScale: root.uiScale; cornerRadius: parent.radius; raised: index !== root.selectedAction }
                        }
                        contentItem: Text {
                            text: parent.text
                            color: index === root.selectedAction && root.luluPalette ? root.luluPalette.selectedText : root.luluPalette ? root.luluPalette.primaryText : "white"
                            font: parent.font
                            verticalAlignment: Text.AlignVCenter
                            horizontalAlignment: Text.AlignHCenter
                        }
                        onClicked: { root.selectedAction = index; root.activate() }
                    }
                }
            }
        }
        Column {
            visible: !root.online
            spacing: 12 * root.uiScale
            Repeater {
                model: root.actionCount
                delegate: Button {
                    required property int index
                    objectName: "onboardingOfflineAction" + index
                    text: root.actionLabel(index)
                    highlighted: index === root.selectedAction
                    implicitWidth: 360 * root.uiScale
                    implicitHeight: 58 * root.uiScale
                    font.pixelSize: 20 * root.uiScale
                    font.bold: true
                    background: Rectangle {
                        radius: root.luluPalette ? root.luluPalette.radius("row", 12 * root.uiScale) : 12 * root.uiScale
                        color: index === root.selectedAction
                            ? (root.luluPalette ? root.luluPalette.focusedCardSurface : "#8ab4ff")
                            : (root.luluPalette ? root.luluPalette.cardSurface : "#242d3a")
                        border.width: index === root.selectedAction ? 3 : 1
                        border.color: root.luluPalette ? root.luluPalette.focusIndicator : "#8ab4ff"
                        MudosChromeFrame { anchors.fill: parent; luluPalette: root.luluPalette; uiScale: root.uiScale; cornerRadius: parent.radius; raised: index !== root.selectedAction }
                    }
                    contentItem: Text {
                        text: parent.text
                        color: index === root.selectedAction && root.luluPalette ? root.luluPalette.selectedText : root.luluPalette ? root.luluPalette.primaryText : "white"
                        font: parent.font
                        verticalAlignment: Text.AlignVCenter
                        horizontalAlignment: Text.AlignHCenter
                    }
                    onClicked: { root.selectedAction = index; root.activate() }
                }
            }
        }
    }
}
