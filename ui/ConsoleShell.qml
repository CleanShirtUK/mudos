import QtQuick
import QtQuick.Window

// Provisional shell proof: cards transform in place; final visual language stays open.
Window {
    id: root
    visible: true
    visibility: Window.FullScreen
    color: "#10141c"
    title: "Lulu"
    flags: Qt.FramelessWindowHint

    property int focusedCard: 0
    property bool expanded: false
    property string expandedTitle: ""

    function cardTitle(index) {
        return index === 0 ? "Recent" : index === 1 ? "System" : "More"
    }

    function activateCard(index) {
        focusedCard = index
        expandedTitle = cardTitle(index)
        expanded = true
    }

    function moveFocus(delta) {
        if (expanded)
            return
        focusedCard = (focusedCard + delta + 3) % 3
    }

    function goBack() {
        if (expanded) {
            expanded = false
            expandedTitle = ""
        }
    }

    Rectangle {
        id: inputSurface
        anchors.fill: parent
        color: "#10141c"
        focus: true

        Keys.onPressed: function(event) {
            if (event.key === Qt.Key_Left || event.key === Qt.Key_Up) {
                moveFocus(-1)
                event.accepted = true
            } else if (event.key === Qt.Key_Right || event.key === Qt.Key_Down) {
                moveFocus(1)
                event.accepted = true
            } else if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter) {
                activateCard(focusedCard)
                event.accepted = true
            } else if (event.key === Qt.Key_Escape || event.key === Qt.Key_Backspace) {
                goBack()
                event.accepted = true
            }
        }

        Column {
            anchors {
                left: parent.left
                right: parent.right
                top: parent.top
                margins: Math.max(48, parent.width * 0.08)
            }
            spacing: 8

            Text {
                text: "Lulu"
                color: "#e6edf5"
                font.pixelSize: 34
            }
            Text {
                text: root.expanded ? root.expandedTitle : "Recent"
                color: "#93a4b8"
                font.pixelSize: 18
            }
        }

        Row {
            id: cardRow
            visible: !root.expanded
            anchors.centerIn: parent
            spacing: 24

            ShellCard {
                id: recentCard
                title: "Recent"
                subtitle: "Return to play"
                selected: root.focusedCard === 0
                onActivated: root.activateCard(0)
            }
            ShellCard {
                id: systemCard
                title: "System"
                subtitle: "Console spaces"
                selected: root.focusedCard === 1
                onActivated: root.activateCard(1)
            }
            ShellCard {
                id: moreCard
                title: "More"
                subtitle: "Provisional space"
                selected: root.focusedCard === 2
                onActivated: root.activateCard(2)
            }
        }

        Rectangle {
            visible: root.expanded
            anchors {
                left: parent.left
                right: parent.right
                top: parent.top
                bottom: parent.bottom
                margins: Math.max(48, parent.width * 0.08)
            }
            color: "#182231"
            border.color: "#50647c"
            border.width: 2
            radius: 18

            Column {
                anchors.centerIn: parent
                spacing: 14
                Text {
                    anchors.horizontalCenter: parent.horizontalCenter
                    text: root.expandedTitle
                    color: "#e6edf5"
                    font.pixelSize: 42
                }
                Text {
                    anchors.horizontalCenter: parent.horizontalCenter
                    text: "Expanded space proof"
                    color: "#93a4b8"
                    font.pixelSize: 20
                }
                Text {
                    anchors.horizontalCenter: parent.horizontalCenter
                    text: "B: back to Home"
                    color: "#71839a"
                    font.pixelSize: 16
                }
            }
        }

        Text {
            anchors.bottom: parent.bottom
            anchors.horizontalCenter: parent.horizontalCenter
            anchors.bottomMargin: 36
            text: root.expanded ? "A: select    B: back" : "D-pad: move    A: select"
            color: "#71839a"
            font.pixelSize: 16
        }
    }

    component ShellCard: Rectangle {
        id: card
        signal activated()
        property string title: ""
        property string subtitle: ""
        property bool selected: false
        width: 260
        height: 180
        radius: 18
        color: selected ? "#304967" : "#1b2635"
        border.color: selected ? "#b7d6f5" : "#3a4a5d"
        border.width: selected ? 3 : 1

        Column {
            anchors.centerIn: parent
            spacing: 10
            Text {
                anchors.horizontalCenter: parent.horizontalCenter
                text: card.title
                color: "#e6edf5"
                font.pixelSize: 28
            }
            Text {
                anchors.horizontalCenter: parent.horizontalCenter
                text: card.subtitle
                color: "#a9bbcf"
                font.pixelSize: 15
            }
        }
    }
}
