pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Controls

Window {
    id: root
    visible: true
    visibility: Window.FullScreen
    color: luluPalette.backdrop
    flags: Qt.FramelessWindowHint

    LuluPalette { id: luluPalette }
    Typography { id: typography }

    property var snapshot: ({})
    property var actions: []
    property var componentIds: []
    property int selected: 0
    property bool detailsOpen: false
    property bool confirmOpen: false
    property int confirmChoice: 1
    property var pendingAction: null
    property string message: "Connecting to the independent Recovery service…"
    property string requestState: "loading"

    readonly property string apiBase: "http://127.0.0.1:38124/v1"
    readonly property int menuLength: actions.length + 1

    function getStatus() {
        var xhr = new XMLHttpRequest()
        xhr.open("GET", apiBase + "/status")
        xhr.onreadystatechange = function() {
            if (xhr.readyState !== XMLHttpRequest.DONE) return
            if (xhr.status < 200 || xhr.status >= 300) {
                requestState = "unavailable"
                message = "The independent Recovery control plane is not responding."
                return
            }
            try {
                snapshot = JSON.parse(xhr.responseText)
                actions = snapshot.actions || []
                componentIds = Object.keys(snapshot.components || {}).sort()
                requestState = "ready"
                message = "Status checked " + (snapshot.checked_at || "recently")
                if (selected >= menuLength) selected = Math.max(0, menuLength - 1)
            } catch (error) {
                requestState = "unavailable"
                message = "Recovery returned status that could not be read."
            }
        }
        xhr.send()
    }

    function currentEntry() {
        return selected < actions.length ? actions[selected] : null
    }

    function activate() {
        if (confirmOpen) {
            if (confirmChoice === 0) submitAction()
            else confirmOpen = false
            return
        }
        if (detailsOpen) return
        if (selected === actions.length) {
            detailsOpen = true
            detailsScroll.contentY = 0
            selected = 0
            return
        }
        pendingAction = currentEntry()
        if (pendingAction) {
            confirmChoice = 1
            confirmOpen = true
        }
    }

    function submitAction() {
        if (!pendingAction) return
        var xhr = new XMLHttpRequest()
        xhr.open("POST", apiBase + "/action")
        xhr.setRequestHeader("Content-Type", "application/json")
        xhr.setRequestHeader("Authorization", "Bearer " + controllerBridge.recoveryToken)
        xhr.onreadystatechange = function() {
            if (xhr.readyState !== XMLHttpRequest.DONE) return
            confirmOpen = false
            if (xhr.status >= 200 && xhr.status < 300) {
                message = (pendingAction.label || "Recovery action") + " requested."
                requestState = "recovering"
                refreshTimer.restart()
            } else {
                try { message = JSON.parse(xhr.responseText).error || "The action was rejected." }
                catch (error) { message = "The recovery action could not be completed." }
            }
            pendingAction = null
        }
        xhr.send(JSON.stringify({action_id: pendingAction.action_id, confirmed: true}))
    }

    function controllerUp() {
        if (confirmOpen) confirmChoice = Math.max(0, confirmChoice - 1)
        else if (detailsOpen) detailsScroll.contentY = Math.max(0, detailsScroll.contentY - 72)
        else selected = (selected + menuLength - 1) % menuLength
    }
    function controllerDown() {
        if (confirmOpen) confirmChoice = Math.min(1, confirmChoice + 1)
        else if (detailsOpen) detailsScroll.contentY = Math.min(
                    Math.max(0, detailsScroll.contentHeight - detailsScroll.height),
                    detailsScroll.contentY + 72)
        else selected = (selected + 1) % menuLength
    }
    function controllerLeft() { back() }
    function controllerRight() { activate() }
    function back() {
        if (confirmOpen) confirmOpen = false
        else if (detailsOpen) detailsOpen = false
    }

    Timer {
        id: refreshTimer
        interval: 1000
        repeat: false
        onTriggered: root.getStatus()
    }

    Rectangle {
        anchors.fill: parent
        color: luluPalette.backdrop
    }

    Column {
        id: recoveryRoot
        anchors.fill: parent
        anchors.margins: 44
        spacing: 18
        focus: true
        Keys.onPressed: function(event) {
            if (event.key === Qt.Key_Up) root.controllerUp()
            else if (event.key === Qt.Key_Down) root.controllerDown()
            else if (event.key === Qt.Key_Left || event.key === Qt.Key_Escape || event.key === Qt.Key_Backspace) root.back()
            else if (event.key === Qt.Key_Right || event.key === Qt.Key_Return
                     || event.key === Qt.Key_Enter || event.key === Qt.Key_Space) root.activate()
            else { event.accepted = false; return }
            event.accepted = true
        }

        Row {
            width: parent.width
            spacing: 20
            Column {
                width: parent.width - 250
                spacing: 8
                Text { text: "MUDOS RECOVERY"; color: luluPalette.headingAccent; font.family: typography.majorHeadingFamily; font.pixelSize: 17; font.bold: true; font.letterSpacing: 3 }
                Text {
                    text: root.detailsOpen ? "System status" : "What needs attention?"
                    color: luluPalette.primaryText; font.family: typography.displayFamily; font.pixelSize: 38; font.bold: true
                }
                Text {
                    text: root.snapshot.overall_state
                          ? "Overall state: " + root.snapshot.overall_state.replaceAll("_", " ")
                          : "Independent recovery is starting"
                    color: root.snapshot.overall_state === "healthy" ? luluPalette.accent : luluPalette.warning
                    font.family: typography.interfaceFamily
                    font.pixelSize: 19
                }
            }
            Text {
                width: 230
                text: controllerBridge.controllerConnected
                      ? "Controller connected" : "Reconnect your controller to navigate"
                color: controllerBridge.controllerConnected ? luluPalette.accent : luluPalette.secondaryText
                font.family: typography.interfaceFamily
                font.pixelSize: 15
                horizontalAlignment: Text.AlignRight
                wrapMode: Text.WordWrap
            }
        }

        Text {
            text: root.message
            color: luluPalette.secondaryText
            font.family: typography.interfaceFamily
            font.pixelSize: 16
            wrapMode: Text.WordWrap
            width: parent.width
        }

        Row {
            visible: !root.detailsOpen
            width: parent.width
            height: parent.height - 210
            spacing: 28

            Column {
                width: Math.min(590, parent.width * 0.55)
                height: parent.height
                spacing: 10
                Repeater {
                    model: root.actions
                    delegate: Button {
                        id: recoveryActionButton
                        required property int index
                        required property var modelData
                        width: parent.width
                        height: 58
                        text: modelData.label
                        focus: root.selected === index
                        activeFocusOnTab: true
                        highlighted: root.selected === index
                        background: Rectangle {
                            radius: luluPalette.radius("row", 8)
                            color: root.selected === index ? luluPalette.selectionSurface : luluPalette.cardSurface
                            border.width: root.selected === index ? 3 : 1
                            border.color: root.selected === index ? luluPalette.focusIndicator : luluPalette.glassBorder
                            MudosChromeFrame { anchors.fill: parent; luluPalette: root.luluPalette; cornerRadius: parent.radius; raised: root.selected !== index }
                        }
                        contentItem: Text {
                            text: recoveryActionButton.text
                            color: root.selected === index ? luluPalette.selectedText : luluPalette.primaryText
                            font.family: typography.interfaceFamily
                            font.pixelSize: 17
                            font.bold: root.selected === index
                            horizontalAlignment: Text.AlignHCenter
                            verticalAlignment: Text.AlignVCenter
                            elide: Text.ElideRight
                        }
                        onClicked: { root.selected = index; root.activate() }
                    }
                }
                Button {
                    id: recoveryDetailsButton
                    width: parent.width
                    height: 58
                    text: "Diagnostics and component details"
                    focus: root.selected === root.actions.length
                    activeFocusOnTab: true
                    highlighted: root.selected === root.actions.length
                    background: Rectangle {
                        radius: luluPalette.radius("row", 8)
                        color: root.selected === root.actions.length ? luluPalette.selectionSurface : luluPalette.cardSurface
                        border.width: root.selected === root.actions.length ? 3 : 1
                        border.color: root.selected === root.actions.length ? luluPalette.focusIndicator : luluPalette.glassBorder
                        MudosChromeFrame { anchors.fill: parent; luluPalette: root.luluPalette; cornerRadius: parent.radius; raised: root.selected !== root.actions.length }
                    }
                    contentItem: Text {
                        text: recoveryDetailsButton.text
                        color: root.selected === root.actions.length ? luluPalette.selectedText : luluPalette.primaryText
                        font.family: typography.interfaceFamily
                        font.pixelSize: 16
                        font.bold: root.selected === root.actions.length
                        horizontalAlignment: Text.AlignHCenter
                        verticalAlignment: Text.AlignVCenter
                        elide: Text.ElideRight
                    }
                    onClicked: { root.selected = root.actions.length; root.activate() }
                }
            }

            Flickable {
                width: parent.width - Math.min(590, parent.width * 0.55) - 28
                height: parent.height
                contentHeight: summaryColumn.implicitHeight
                clip: true
                Column {
                    id: summaryColumn
                    width: parent.width
                    spacing: 12
                    Repeater {
                        model: root.componentIds.slice(0, 6)
                        delegate: Rectangle {
                            required property string modelData
                            property var item: root.snapshot.components[modelData] || ({})
                            width: parent.width
                            height: summaryText.implicitHeight + 26
                            radius: luluPalette.radius("panel", 12)
                            color: luluPalette.cardSurface
                            border.color: item.state === "failed" ? luluPalette.warning : luluPalette.glassBorder
                            MudosChromeFrame { anchors.fill: parent; luluPalette: root.luluPalette; cornerRadius: parent.radius }
                            Column {
                                id: summaryText
                                anchors.fill: parent
                                anchors.margins: 13
                                spacing: 4
                                Text {
                                    text: modelData.replaceAll("_", " ").toUpperCase()
                                    color: luluPalette.headingAccent; font.family: typography.interfaceFamily; font.pixelSize: 12; font.bold: true
                                }
                                Text {
                                    text: item.summary || "Evidence unavailable"
                                    color: luluPalette.primaryText; font.family: typography.interfaceFamily; font.pixelSize: 15; wrapMode: Text.WordWrap
                                    width: parent.width
                                }
                                Text {
                                    text: (item.state || "unknown").replaceAll("_", " ")
                                          + " · " + (item.freshness || "unknown")
                                    color: luluPalette.secondaryText; font.family: typography.interfaceFamily; font.pixelSize: 12
                                }
                            }
                        }
                    }
                }
            }
        }

        Flickable {
            id: detailsScroll
            visible: root.detailsOpen
            width: parent.width
            height: parent.height - 250
            contentHeight: detailsColumn.implicitHeight
            clip: true
            Column {
                id: detailsColumn
                width: parent.width - 18
                spacing: 12
                Repeater {
                    model: root.componentIds
                    delegate: Rectangle {
                        required property string modelData
                        property var item: root.snapshot.components[modelData] || ({})
                        width: detailsColumn.width
                        height: detailsText.implicitHeight + 28
                        radius: luluPalette.radius("panel", 10)
                        color: luluPalette.cardSurface
                        border.color: luluPalette.glassBorder
                        MudosChromeFrame { anchors.fill: parent; luluPalette: root.luluPalette; cornerRadius: parent.radius }
                        Column {
                            id: detailsText
                            anchors.fill: parent
                            anchors.margins: 14
                            spacing: 6
                            Text { text: modelData.replaceAll("_", " ").toUpperCase() + " · " + (item.state || "unknown").replaceAll("_", " "); color: luluPalette.headingAccent; font.family: typography.interfaceFamily; font.bold: true; font.pixelSize: 14 }
                            Text { text: item.summary || "Evidence unavailable"; color: luluPalette.primaryText; font.family: typography.interfaceFamily; wrapMode: Text.WordWrap; width: parent.width }
                            Text { text: "Checked: " + (item.checked_at || "unavailable") + " · evidence: " + (item.freshness || "unknown"); color: luluPalette.secondaryText; font.family: typography.interfaceFamily; font.pixelSize: 12; wrapMode: Text.WordWrap; width: parent.width }
                            Text { visible: !!item.last_error; text: "Detail: " + (item.last_error || ""); color: luluPalette.warning; font.family: typography.interfaceFamily; wrapMode: Text.WordWrap; width: parent.width }
                            Text { text: "Evidence: " + JSON.stringify(item.evidence || ({})); color: luluPalette.mutedText; font.family: typography.interfaceFamily; font.pixelSize: 11; wrapMode: Text.WrapAnywhere; width: parent.width }
                        }
                    }
                }
            }
        }

        Text {
            width: parent.width
            text: "D-pad / arrows: move   A / Enter: select   B / Esc: back   ·   Status refreshes automatically"
            color: luluPalette.mutedText
            font.family: typography.interfaceFamily
            font.pixelSize: 13
        }
    }

    Rectangle {
        visible: root.confirmOpen
        anchors.fill: parent
            color: luluPalette.overlayBackdrop
        MouseArea { anchors.fill: parent }
        Rectangle {
            anchors.centerIn: parent
            width: Math.min(parent.width - 48, 700)
            height: Math.min(parent.height - 48, confirmColumn.implicitHeight + 56)
            radius: luluPalette.radius("overlay", 18)
            color: luluPalette.overlaySurface
            border.color: luluPalette.glassBorder
            MudosChromeFrame { anchors.fill: parent; luluPalette: root.luluPalette; cornerRadius: parent.radius }
            Column {
                id: confirmColumn
                anchors.fill: parent
                anchors.margins: 26
                spacing: 14
                Text { text: "Confirm action"; color: luluPalette.primaryText; font.family: typography.majorHeadingFamily; font.pixelSize: 27; font.bold: true }
                Text { text: root.pendingAction ? root.pendingAction.label : "Recovery action"; color: luluPalette.headingAccent; font.family: typography.interfaceFamily; font.pixelSize: 19; font.bold: true }
                Repeater {
                    model: root.pendingAction ? root.pendingAction.impact : []
                    delegate: Text {
                        required property string modelData
                        text: "• " + modelData
                        color: luluPalette.secondaryText; font.family: typography.interfaceFamily; font.pixelSize: 15; wrapMode: Text.WordWrap
                        width: confirmColumn.width
                    }
                }
                Row {
                    spacing: 12
                    Button {
                        text: "Confirm"
                        focus: root.confirmChoice === 0
                        activeFocusOnTab: true
                        highlighted: root.confirmChoice === 0
                        background: Rectangle {
                            radius: luluPalette.radius("row", 8)
                            color: root.confirmChoice === 0 ? luluPalette.selectionSurface : luluPalette.actionSurface
                            border.color: root.confirmChoice === 0 ? luluPalette.focusIndicator : luluPalette.glassBorder
                            MudosChromeFrame { anchors.fill: parent; luluPalette: root.luluPalette; cornerRadius: parent.radius; raised: root.confirmChoice !== 0 }
                        }
                        contentItem: Text {
                            text: parent.text
                            color: root.confirmChoice === 0 ? luluPalette.selectedText : luluPalette.actionText
                            font.family: typography.interfaceFamily
                            horizontalAlignment: Text.AlignHCenter
                            verticalAlignment: Text.AlignVCenter
                        }
                        onClicked: { root.confirmChoice = 0; root.activate() }
                    }
                    Button {
                        text: "Cancel"
                        focus: root.confirmChoice === 1
                        activeFocusOnTab: true
                        highlighted: root.confirmChoice === 1
                        background: Rectangle {
                            radius: luluPalette.radius("row", 8)
                            color: root.confirmChoice === 1 ? luluPalette.selectionSurface : luluPalette.actionSurface
                            border.color: root.confirmChoice === 1 ? luluPalette.focusIndicator : luluPalette.glassBorder
                            MudosChromeFrame { anchors.fill: parent; luluPalette: root.luluPalette; cornerRadius: parent.radius; raised: root.confirmChoice !== 1 }
                        }
                        contentItem: Text {
                            text: parent.text
                            color: root.confirmChoice === 1 ? luluPalette.selectedText : luluPalette.actionText
                            font.family: typography.interfaceFamily
                            horizontalAlignment: Text.AlignHCenter
                            verticalAlignment: Text.AlignVCenter
                        }
                        onClicked: root.confirmOpen = false
                    }
                }
            }
        }
    }

    Component.onCompleted: {
        recoveryRoot.forceActiveFocus()
        getStatus()
    }
}
