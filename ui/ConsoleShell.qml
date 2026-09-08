import QtQuick
import QtQuick.Window

Window {
    id: root
    visible: true
    visibility: Window.FullScreen
    color: luluPalette.backdrop
    flags: Qt.FramelessWindowHint

    property var domains: ["System", "Store", "Library", "Recent"]
    property int selectedCategoryIndex: 3
    readonly property real referenceWidth: 1280
    readonly property real referenceHeight: 720
    readonly property real uiScale: Math.min(width / referenceWidth, height / referenceHeight)
    function design(value) { return value * uiScale }

    Typography {
        id: typography
        uiScale: root.uiScale
    }

    LuluPalette {
        id: luluPalette
    }

    readonly property real activeHeadingHeight: design(37)
    readonly property real headingCardGap: design(21)
    readonly property real homeCategoryRailX: design(52)
    readonly property real homeCategoryFontSize: typography.size("display", 48)
    readonly property real homeCategoryGap: design(25)
    readonly property real homeCategoryPitch: homeCategoryFontSize + homeCategoryGap
    readonly property real homeHintTopY: height - design(45)
    readonly property real homeBottomBandCenterY: height - design(36)
    readonly property real acceptedRecentCardHeight: Math.min(design(375), (height - design(248 + 88)) * 0.67)
    readonly property real homeFocalCardHeight: Math.min(design(500), (height - design(248 + 88)) * 0.82)
    readonly property real homeContentRailX: design(52)
    readonly property real homeFocalCardWidth: Math.min(design(900), width - homeContentRailX - design(40), homeFocalCardHeight * 1.9)
    readonly property real homeCompactCardWidth: Math.min(design(220), homeFocalCardHeight * 0.62)
    readonly property real homeInterCardGap: design(24)
    readonly property real compactCardWidth: Math.min(design(160), acceptedRecentCardHeight * 0.62)
    readonly property real homeContentOriginY: homeHintTopY - acceptedRecentCardHeight - headingCardGap
    readonly property real homeActiveContentOriginY: homeHintTopY - homeFocalCardHeight - headingCardGap
    readonly property real selectedDomainY: homeActiveContentOriginY - activeHeadingHeight - headingCardGap
    property int recentIndex: 0
    property int libraryIndex: 0
    property int collectionIndex: 0
    property string space: "home"
    property string libraryFocus: "games"
    property int libraryFirstVisibleRow: 0
    property string libraryTransitionState: "RESTING"
    readonly property string libraryNavigationObject: "library"
    property var recentGames: []
    property var libraryGames: []
    property string message: ""
    property string launchStatus: "idle"
    property string launchTitle: ""
    property string launchToken: ""
    property int launchGeneration: 0
    property int launchStateSerial: 0
    property int launchStateApplied: 0
    property int launchStateRank: 0
    readonly property string apiUrl: "http://127.0.0.1:38123"
    readonly property var visibleRecentGame: recentGames.length ? recentGames[recentIndex] : null
    readonly property var visibleLibraryGame: libraryGames.length ? libraryGames[libraryIndex] : null
    readonly property string libraryScope: collectionIndex === 0 ? "all" : "steam"

    function request(path, method, body, callback, failureMessage, generation) {
        var request = new XMLHttpRequest()
        request.onreadystatechange = function() {
            if (request.readyState !== XMLHttpRequest.DONE)
                return
            if (request.status === 200)
                callback(JSON.parse(request.responseText))
            else if (failureMessage && (generation === undefined || generation === launchGeneration)) {
                message = failureMessage || "Catalogue unavailable"
                if (generation !== undefined) {
                    launchStatus = "failed"
                    launchStatusTimer.stop()
                }
            }
        }
        request.open(method, apiUrl + path)
        request.send(body || "")
    }

    function refreshCatalogue() {
        request("/?scope=recent", "GET", "", function(data) {
            var selectedId = visibleRecentGame ? visibleRecentGame.game_id : ""
            recentGames = data
            var selectedIndex = -1
            for (var index = 0; index < recentGames.length; index++) {
                if (recentGames[index].game_id === selectedId) {
                    selectedIndex = index
                    break
                }
            }
            if (selectedIndex >= 0)
                recentIndex = selectedIndex
            else if (recentIndex >= recentGames.length)
                recentIndex = Math.max(0, recentGames.length - 1)
        })
        refreshLibrary()
    }

    function applyLaunchState(state, generation) {
        if (generation !== launchGeneration)
            return
        var stateToken = state.launch_token || (state.last_result ? state.last_result.token : "")
        if (launchToken && stateToken && stateToken !== launchToken)
            return
        var stateRank = state.lifecycle === "launch_requested" || state.lifecycle === "starting" ? 1
                      : state.lifecycle === "game" ? 2
                      : state.lifecycle === "returning" ? 3
                      : 4
        if (stateRank < launchStateRank)
            return
        launchStateRank = stateRank
        if (state.lifecycle === "launch_requested" || state.lifecycle === "starting"
                || state.lifecycle === "presentation_pending") {
            launchStatus = "launching"
            message = "Launching " + launchTitle
        } else if (state.lifecycle === "game") {
            launchStatus = "running"
            message = "Running " + launchTitle
        } else if (state.lifecycle === "returning") {
            launchStatus = "returning"
            message = "Returning"
        } else if (state.lifecycle === "shell") {
            launchStatus = state.last_failure_reason && stateToken === launchToken ? "failed" : "idle"
            message = launchStatus === "failed" ? "Launch failed" : ""
            launchStatusTimer.stop()
        }
    }

    function refreshLaunchState(generation) {
        var serial = ++launchStateSerial
        request("/state", "GET", "", function(state) {
            if (serial < launchStateApplied)
                return
            launchStateApplied = serial
            applyLaunchState(state, generation)
        }, "", generation)
    }

    function refreshLibrary() {
        request("/?scope=" + libraryScope, "GET", "", function(data) {
            libraryGames = data
            if (libraryIndex >= libraryGames.length)
                libraryIndex = Math.max(0, libraryGames.length - 1)
            libraryFirstVisibleRow = Math.min(libraryFirstVisibleRow,
                                              Math.max(0, Math.floor(Math.max(0, libraryGames.length - 1) / 7) - 1))
        })
    }

    function moveDomain(delta) {
        if (space !== "home")
            return
        selectedCategoryIndex = Math.max(0, Math.min(domains.length - 1,
                                                     selectedCategoryIndex + delta))
        message = ""
    }

    function domainOffset(index) {
        return index - selectedCategoryIndex
    }

    function moveRecent(delta) {
        if (!recentGames.length)
            return
        recentIndex = Math.max(0, Math.min(recentGames.length - 1, recentIndex + delta))
    }

    function moveLibrary(delta) {
        if (!libraryGames.length)
            return
        libraryIndex = Math.max(0, Math.min(libraryGames.length - 1, libraryIndex + delta))
    }

    function moveLibraryVertical(delta) {
        if (!libraryGames.length)
            return
        var column = libraryIndex % 7
        var row = Math.floor(libraryIndex / 7) + delta
        if (row < 0)
            return
        var target = row * 7 + column
        var rowStart = row * 7
        if (rowStart >= libraryGames.length)
            return
        libraryIndex = Math.min(target, libraryGames.length - 1)
        if (row >= libraryFirstVisibleRow + 2)
            libraryFirstVisibleRow = row - 1
        else if (row < libraryFirstVisibleRow)
            libraryFirstVisibleRow = row
    }

    function moveLibraryCollection(delta) {
        collectionIndex = Math.max(0, Math.min(1, collectionIndex + delta))
        refreshLibrary()
    }

    function launchGame(game) {
        if (!game)
            return
        if (launchStatus === "launching" || launchStatus === "running" || launchStatus === "returning")
            return
        var generation = ++launchGeneration
        launchTitle = game.title
        launchToken = ""
        launchStatus = "launching"
        launchStateRank = 1
        message = "Launching " + game.title
        request("/launch/" + encodeURIComponent(game.game_id), "POST", "", function(data) {
            if (generation !== launchGeneration)
                return
            launchToken = data.token
            refreshLaunchState(generation)
            launchStatusTimer.start()
            refreshCatalogue()
        }, "Launch failed", generation)
    }

    function activate() {
        if (space === "library") {
            if (libraryFocus === "collection") {
                refreshLibrary()
                libraryFocus = "games"
            } else {
                launchGame(visibleLibraryGame)
            }
            return
        }

        if (selectedCategoryIndex === 3) {
            launchGame(visibleRecentGame)
        } else if (selectedCategoryIndex === 2) {
            libraryTransitionState = "ACTIVATING"
            space = "library"
            libraryFocus = "games"
            libraryIndex = 0
            libraryFirstVisibleRow = 0
            libraryTransitionState = "EXPANDED"
            message = ""
        } else if (selectedCategoryIndex === 1) {
            message = "Store space is not implemented"
        } else {
            message = "System space is not implemented"
        }
    }

    function back() {
        if (space === "library") {
            libraryTransitionState = "ACTIVATING"
            space = "home"
            libraryFocus = "games"
            libraryTransitionState = "RESTING"
            message = ""
        } else {
            message = ""
        }
    }

    Component.onCompleted: {
        inputSurface.forceActiveFocus()
        refreshCatalogue()
    }

    OrbitRenderSource {
        id: orbitRenderSource
        anchors.fill: parent
        visible: false
    }

    ShaderEffectSource {
        id: orbitTexture
        anchors.fill: parent
        sourceItem: orbitRenderSource
        sourceRect: Qt.rect(0, 0, root.width, root.height)
        textureSize: Qt.size(root.width, root.height)
        live: true
        hideSource: true
        visible: false
    }

    OrbitBackdropView {
        id: orbitBackdropView
        texture: orbitTexture
        z: 0
    }

    Rectangle {
        id: inputSurface
        anchors.fill: parent
        z: 10
        color: luluPalette.transparent
        focus: true

        Keys.onPressed: function(event) {
            if (space === "home") {
                if (event.key === Qt.Key_Up) {
                    moveDomain(-1)
                    event.accepted = true
                } else if (event.key === Qt.Key_Down) {
                    moveDomain(1)
                    event.accepted = true
                } else if (event.key === Qt.Key_Left) {
                    if (selectedCategoryIndex === 3)
                        moveRecent(-1)
                    else if (selectedCategoryIndex === 2)
                        moveLibrary(-1)
                    event.accepted = true
                } else if (event.key === Qt.Key_Right) {
                    if (selectedCategoryIndex === 3)
                        moveRecent(1)
                    else if (selectedCategoryIndex === 2)
                        moveLibrary(1)
                    event.accepted = true
                }
            } else if (space === "library") {
                if (event.key === Qt.Key_Up) {
                    moveLibraryVertical(-1)
                    event.accepted = true
                } else if (event.key === Qt.Key_Down) {
                    moveLibraryVertical(1)
                    event.accepted = true
                } else if (event.key === Qt.Key_Left) {
                    moveLibrary(-1)
                    event.accepted = true
                } else if (event.key === Qt.Key_Right) {
                    moveLibrary(1)
                    event.accepted = true
                } else if (event.key === Qt.Key_PageUp) {
                    moveLibraryCollection(-1)
                    event.accepted = true
                } else if (event.key === Qt.Key_PageDown) {
                    moveLibraryCollection(1)
                    event.accepted = true
                }
            }

            if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter) {
                activate()
                event.accepted = true
            } else if (event.key === Qt.Key_Escape || event.key === Qt.Key_Backspace) {
                back()
                event.accepted = true
            }
        }

        Item {
            id: homeScene
            anchors.fill: parent
            visible: root.space === "home"

            Item {
                x: root.homeCategoryRailX
                y: 0
                width: root.design(250)
                height: parent.height

                Repeater {
                    model: root.domains
                    delegate: Text {
                        required property int index
                        readonly property int relativeCategoryIndex: index - root.selectedCategoryIndex
                        readonly property bool isPreview: relativeCategoryIndex === 1
                        y: isPreview
                           ? root.homeBottomBandCenterY - height * 0.5
                           : root.selectedDomainY + root.domainOffset(index) * root.homeCategoryPitch
                        visible: relativeCategoryIndex <= 1
                        text: root.domains[index]
                        color: luluPalette.selectedText
                        font.family: typography.displayFamily
                        font.weight: typography.displayWeight
                        font.pixelSize: root.homeCategoryFontSize
                        font.letterSpacing: 0
                        opacity: relativeCategoryIndex === 0 ? 1 : 0.58
                        scale: relativeCategoryIndex === 0 ? 1.05 : 1
                    }
                }
            }

            Item {
                id: homeContent
                x: root.homeContentRailX
                y: root.homeActiveContentOriginY
                width: parent.width - root.homeContentRailX - root.design(40)
                height: root.homeFocalCardHeight

                RecentHome {
                    anchors.fill: parent
                    visible: root.selectedCategoryIndex === 3
                    opacity: visible ? 1 : 0
                    scale: visible ? 1 : 0.94
                    recentGames: root.recentGames
                    selectedIndex: root.recentIndex
                    focalCardWidth: root.homeFocalCardWidth
                    focalCardHeight: root.homeFocalCardHeight
                    compactCardWidth: root.homeCompactCardWidth
                    railGap: root.homeInterCardGap
                     focalScale: 0.67
                     uiScale: root.uiScale
                     typography: typography
                     luluPalette: luluPalette
                     canonicalTexture: orbitTexture
                     canonicalCoordinateRoot: orbitRenderSource
                     canonicalSize: Qt.size(root.width, root.height)
                    onLaunchRequested: root.launchGame(game)
                }

                LibraryHome {
                    anchors.fill: parent
                    visible: root.selectedCategoryIndex === 2
                    opacity: visible ? 1 : 0
                    scale: visible ? 1 : 0.94
                     cardHeight: root.acceptedRecentCardHeight
                     uiScale: root.uiScale
                     typography: typography
                     luluPalette: luluPalette
                     canonicalTexture: orbitTexture
                     canonicalCoordinateRoot: orbitRenderSource
                     canonicalSize: Qt.size(root.width, root.height)
                     compactCardWidth: root.compactCardWidth
                    transitionState: root.libraryTransitionState
                    onOpenRequested: root.activate()
                }

                PlaceholderHome {
                    anchors.fill: parent
                    visible: root.selectedCategoryIndex === 1 || root.selectedCategoryIndex === 0
                    opacity: visible ? 1 : 0
                    scale: visible ? 1 : 0.94
                     title: root.domains[root.selectedCategoryIndex]
                     uiScale: root.uiScale
                     typography: typography
                     luluPalette: luluPalette
                    description: root.selectedCategoryIndex === 1 ? "Acquisition space is not implemented" : "Platform controls are not implemented"
                }
            }
        }

        LibrarySpace {
            anchors.fill: parent
            visible: root.space === "library"
            libraryGames: root.libraryGames
            selectedIndex: root.libraryIndex
            collectionIndex: root.collectionIndex
            collectionFocus: root.libraryFocus === "collection"
             transitionState: root.libraryTransitionState
             returnState: root.space === "library" ? "EXPANDED" : "RESTING"
             uiScale: root.uiScale
             typography: typography
             luluPalette: luluPalette
             canonicalTexture: orbitTexture
             canonicalCoordinateRoot: orbitRenderSource
             canonicalSize: Qt.size(root.width, root.height)
             firstVisibleRow: root.libraryFirstVisibleRow
            onCollectionChanged: {
                root.collectionIndex = index
                root.refreshLibrary()
            }
            onLaunchRequested: root.launchGame(game)
        }

        Item {
            id: interactionRail
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.bottom: parent.bottom
            height: root.design(72)

            Row {
                x: root.design(76)
                width: parent.width * 0.54
                anchors.verticalCenter: parent.verticalCenter
                visible: root.space === "library"
                spacing: root.design(14)

                ControllerHint {
                    action: "navigation"
                    label: "Games"
                    uiScale: root.uiScale
                    typography: typography
                    luluPalette: luluPalette
                }
                ControllerHint {
                    action: "previousCollection"
                    label: "Prev"
                    uiScale: root.uiScale
                    typography: typography
                    luluPalette: luluPalette
                }
                ControllerHint {
                    action: "nextCollection"
                    label: "Next"
                    uiScale: root.uiScale
                    typography: typography
                    luluPalette: luluPalette
                }
                ControllerHint {
                    action: "confirm"
                    label: root.space === "library" ? "Launch" : "Select"
                    uiScale: root.uiScale
                    typography: typography
                    luluPalette: luluPalette
                }
                ControllerHint {
                    action: "back"
                    label: "Back"
                    uiScale: root.uiScale
                    typography: typography
                    luluPalette: luluPalette
                }
            }

            Row {
                width: parent.width * 0.54
                anchors.right: parent.right
                anchors.rightMargin: root.design(76)
                anchors.verticalCenter: parent.verticalCenter
                visible: root.space !== "library"
                spacing: root.design(14)

                ControllerHint {
                    action: "navigation"
                     label: root.selectedCategoryIndex === 3 ? "Navigate / Games" : "Navigate"
                    uiScale: root.uiScale
                    typography: typography
                    luluPalette: luluPalette
                }
                ControllerHint {
                    action: "confirm"
                     label: root.selectedCategoryIndex === 3 ? "Launch"
                           : root.selectedCategoryIndex === 2 ? "Open Library" : "Select"
                    uiScale: root.uiScale
                    typography: typography
                    luluPalette: luluPalette
                }
            }

            Text {
                x: parent.width * 0.58
                width: parent.width * 0.36
                anchors.verticalCenter: parent.verticalCenter
                text: root.message
                color: luluPalette.accent
                font.family: typography.interfaceFamily
                font.pixelSize: typography.size("secondary", 16)
                horizontalAlignment: Text.AlignRight
                elide: Text.ElideRight
            }
        }
    }

    Timer {
        id: launchStatusTimer
        interval: 150
        repeat: true
        onTriggered: root.refreshLaunchState(root.launchGeneration)
    }

    Timer {
        interval: 2000
        running: true
        repeat: true
        onTriggered: root.refreshCatalogue()
    }
}
