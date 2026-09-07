import QtQuick
import QtQuick.Window

Window {
    id: root
    visible: true
    visibility: Window.FullScreen
    color: "#060b16"
    flags: Qt.FramelessWindowHint

    property var domains: ["Recent", "Library", "Store", "System"]
    property int domainIndex: 0
    property int gameIndex: 0
    property bool storeFilterSteam: false
    property var recentGames: []
    property var libraryGames: []
    property string message: ""
    readonly property string apiUrl: "http://127.0.0.1:38123"
    readonly property var visibleGames: domainIndex === 0 ? recentGames : libraryGames

    function request(path, method, body, callback) {
        var request = new XMLHttpRequest()
        request.onreadystatechange = function() {
            if (request.readyState !== XMLHttpRequest.DONE)
                return
            if (request.status === 200)
                callback(JSON.parse(request.responseText))
            else
                message = "Catalogue unavailable"
        }
        request.open(method, apiUrl + path)
        request.send(body || "")
    }

    function refreshCatalogue() {
        request("/games?scope=recent", "GET", "", function(data) {
            recentGames = data
            if (gameIndex >= recentGames.length)
                gameIndex = Math.max(0, recentGames.length - 1)
        })
        request("/games?scope=" + (storeFilterSteam ? "steam" : "all"), "GET", "", function(data) {
            libraryGames = data
            if (gameIndex >= libraryGames.length)
                gameIndex = Math.max(0, libraryGames.length - 1)
        })
    }

    function moveDomain(delta) {
        domainIndex = (domainIndex + delta + domains.length) % domains.length
        gameIndex = 0
        message = ""
    }

    function moveGame(delta) {
        if (visibleGames.length === 0)
            return
        gameIndex = (gameIndex + delta + visibleGames.length) % visibleGames.length
    }

    function activate() {
        if ((domainIndex !== 0 && domainIndex !== 1) || visibleGames.length === 0) {
            message = domainIndex === 2 ? "Store is unavailable" : "System space is not implemented"
            return
        }
        var game = visibleGames[gameIndex]
        message = "Launching " + game.title
        request("/launch/" + encodeURIComponent(game.game_id), "POST", "", function(data) {
            message = "Launch requested"
            refreshCatalogue()
        })
    }

    function back() {
        message = ""
    }

    Component.onCompleted: {
        inputSurface.forceActiveFocus()
        refreshCatalogue()
    }

    Rectangle {
        anchors.fill: parent
        color: "#060b16"
        gradient: Gradient {
            GradientStop { position: 0.0; color: "#111d38" }
            GradientStop { position: 0.52; color: "#07101f" }
            GradientStop { position: 1.0; color: "#160d2a" }
        }
    }

    Rectangle {
        width: parent.width * 0.58
        height: parent.height * 0.8
        x: parent.width * 0.42
        y: parent.height * 0.08
        radius: width / 2
        color: "#263e72"
        opacity: 0.16
    }

    Rectangle {
        id: inputSurface
        anchors.fill: parent
        color: "transparent"
        focus: true

        Keys.onPressed: function(event) {
            if (event.key === Qt.Key_Up) {
                moveDomain(-1)
                event.accepted = true
            } else if (event.key === Qt.Key_Down) {
                moveDomain(1)
                event.accepted = true
            } else if (event.key === Qt.Key_Left) {
                moveGame(-1)
                event.accepted = true
            } else if (event.key === Qt.Key_Right) {
                moveGame(1)
                event.accepted = true
            } else if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter) {
                activate()
                event.accepted = true
            } else if (event.key === Qt.Key_Escape || event.key === Qt.Key_Backspace) {
                back()
                event.accepted = true
            }
        }

        Column {
            id: domainColumn
            x: 72
            y: 172
            spacing: 22

            Repeater {
                model: root.domains
                delegate: Text {
                    required property int index
                    text: modelData
                    color: index === root.domainIndex ? "#f0dcff" : "#8290aa"
                    font.pixelSize: index === root.domainIndex ? 30 : 22
                    font.letterSpacing: 3
                    opacity: index === root.domainIndex ? 1 : 0.68
                }
            }
        }

        Rectangle {
            x: 300
            y: 72
            width: parent.width - 380
            height: parent.height - 144
            radius: 28
            color: "#14213b"
            opacity: 0.76
            border.color: "#7884c6"
            border.width: 1

            Text {
                x: 44
                y: 34
                text: root.domains[root.domainIndex].toUpperCase()
                color: "#eadcff"
                font.pixelSize: 28
                font.letterSpacing: 5
            }

            Text {
                x: 46
                y: 76
                visible: root.domainIndex === 0
                text: "Return to play"
                color: "#90a0bd"
                font.pixelSize: 17
            }

            Row {
                x: 44
                y: 118
                spacing: 36
                visible: root.domainIndex === 1

                Text {
                    text: "All Games"
                    color: root.storeFilterSteam ? "#8c98b6" : "#f0dcff"
                    font.pixelSize: 19
                }
                Text {
                    text: "Steam"
                    color: root.storeFilterSteam ? "#f0dcff" : "#8c98b6"
                    font.pixelSize: 19
                }
                MouseArea {
                    width: 100
                    height: 32
                    onClicked: {
                        root.storeFilterSteam = !root.storeFilterSteam
                        root.refreshCatalogue()
                    }
                }
            }

            Text {
                anchors.centerIn: parent
                visible: root.visibleGames.length === 0 && (root.domainIndex === 0 || root.domainIndex === 1)
                text: root.domainIndex === 0 ? "No recent games yet" : "No installed launchable games"
                color: "#9aa8c2"
                font.pixelSize: 24
            }

            Text {
                anchors.centerIn: parent
                visible: root.domainIndex === 2
                text: "Store is unavailable"
                color: "#9aa8c2"
                font.pixelSize: 24
            }

            Text {
                anchors.centerIn: parent
                visible: root.domainIndex === 3
                text: "System space is not implemented"
                color: "#9aa8c2"
                font.pixelSize: 24
            }

            Row {
                id: gameRail
                x: 44
                y: 164
                spacing: 18
                visible: root.visibleGames.length > 0 && (root.domainIndex === 0 || root.domainIndex === 1)

                Repeater {
                    model: root.visibleGames
                    delegate: Rectangle {
                        required property int index
                        required property var modelData
                        width: root.domainIndex === 0 && index === root.gameIndex ? 560 : 212
                        height: root.domainIndex === 0 && index === root.gameIndex ? 430 : 350
                        radius: 22
                        color: index === root.gameIndex ? "#283761" : "#182540"
                        border.color: index === root.gameIndex ? "#e0c5ff" : "#455274"
                        border.width: index === root.gameIndex ? 3 : 1
                        clip: true

                        Image {
                            x: 14
                            y: 14
                            width: parent.width - 28
                            height: parent.height * 0.64
                            source: modelData.artwork_url
                            fillMode: Image.PreserveAspectCrop
                            asynchronous: true
                            opacity: index === root.gameIndex ? 1 : 0.68
                        }

                        Rectangle {
                            anchors.fill: parent
                            color: "#10182b"
                            opacity: 0.35
                        }

                        Column {
                            x: 22
                            y: parent.height * 0.68
                            width: parent.width - 44
                            spacing: 8
                            Text {
                                text: modelData.title
                                color: "#f1f3fb"
                                font.pixelSize: index === root.gameIndex ? 27 : 19
                                elide: Text.ElideRight
                                width: parent.width
                            }
                            Text {
                                text: modelData.provider.toUpperCase() + "  |  " + modelData.platform
                                color: "#aab7d0"
                                font.pixelSize: 14
                            }
                            Text {
                                visible: index === root.gameIndex
                                text: "A  Launch"
                                color: "#e0c5ff"
                                font.pixelSize: 17
                            }
                        }
                    }
                }
            }

            Text {
                x: 44
                anchors.bottom: parent.bottom
                anchors.bottomMargin: 30
                text: root.message
                color: "#e0c5ff"
                font.pixelSize: 17
            }
        }

        Text {
            anchors.right: parent.right
            anchors.rightMargin: 54
            anchors.top: parent.top
            anchors.topMargin: 36
            text: "A  Select     B  Back"
            color: "#b6bfd2"
            font.pixelSize: 17
        }

        Text {
            anchors.left: parent.left
            anchors.leftMargin: 72
            anchors.bottom: parent.bottom
            anchors.bottomMargin: 36
            text: "UP / DOWN  DOMAIN       LEFT / RIGHT  CONTENT"
            color: "#8492ad"
            font.pixelSize: 14
            font.letterSpacing: 1
        }
    }

    Timer {
        interval: 2000
        running: true
        repeat: true
        onTriggered: root.refreshCatalogue()
    }
}
