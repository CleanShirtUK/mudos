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
    property int desiredCategoryIndex: 3
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
    readonly property real homeHeadingCardClearance: design(12)
    readonly property real homeCompositionOffsetY: -design(36)
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
    readonly property real homeActiveContentOriginY: homeHintTopY - homeFocalCardHeight
        - headingCardGap + homeHeadingCardClearance + homeCompositionOffsetY
    readonly property real selectedDomainY: homeActiveContentOriginY - homeHeadingCardClearance
        - activeHeadingHeight - headingCardGap
    property int recentIndex: 0
    property int libraryIndex: 0
    property int collectionIndex: 0
    property string space: "home"
    property int systemCategoryIndex: 0
    property var systemHomeRailRef: null
    property int systemRowIndex: 0
    property bool systemLanding: true
    property var systemCategories: ["Display", "Audio", "Network", "Bluetooth", "Controllers", "Storage", "System", "Lulu"]
    property var systemSettings: []
    property string libraryFocus: "games"
    property int libraryFirstVisibleRow: 0
    property string libraryTransitionState: "RESTING"
    property bool libraryTransitioning: false
    property real libraryTransitionProgress: 0
    property bool libraryTransitionExpanding: true
    property bool libraryHandoffPending: false
    property real homeContentOpacity: 1
    property real libraryContentOpacity: 0
    property bool homeCategoryTransitioning: false
    property int homeCategoryFrom: 3
    property int homeCategoryTarget: 3
    property int homeCategoryDirection: 1
    property real homeCategoryProgress: 1
    property int homeCategoryHopDuration: 250
    readonly property real homeCategoryTravel: height + design(72)
    property real titleRailY: selectedDomainY - selectedCategoryIndex * homeCategoryPitch
    property bool suppressTitleRailCompletion: false
    readonly property real titleRailTargetY: selectedDomainY
        - (homeCategoryTransitioning ? homeCategoryTarget : selectedCategoryIndex)
            * homeCategoryPitch
    readonly property real titleRailActiveGap: Math.max(0,
        homeBottomBandCenterY - selectedDomainY - homeCategoryPitch)
    readonly property real libraryHomePresentationHeight: !homeCategoryTransitioning
        ? homeFocalCardHeight
        : homeCategoryTarget === 2 && homeCategoryDirection === 1
          ? homeFocalCardHeight * homeCategoryProgress
          : homeCategoryFrom === 2 && homeCategoryDirection === -1
            ? homeFocalCardHeight * (1 - homeCategoryProgress)
            : homeFocalCardHeight
    function homeCategoryRevealHeight(index) {
        if (!homeCategoryTransitioning)
            return homeFocalCardHeight
        if (homeCategoryDirection === 1 && index === homeCategoryTarget)
            return homeFocalCardHeight * homeCategoryProgress
        if (homeCategoryDirection === -1 && index === homeCategoryFrom)
            return homeFocalCardHeight * (1 - homeCategoryProgress)
        return homeFocalCardHeight
    }

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

    function refreshSystemSettings() {
        request("/settings?category=" + encodeURIComponent(systemCategories[systemCategoryIndex]),
                "GET", "", function(data) {
                    systemSettings = data
                    systemRowIndex = Math.min(systemRowIndex, Math.max(0, data.length - 1))
                })
    }

    function startNextHomeCategoryHop(chained) {
        if (selectedCategoryIndex === desiredCategoryIndex)
            return
        homeCategoryHopDuration = chained ? 100 : 250
        homeCategoryFrom = selectedCategoryIndex
        homeCategoryTarget = selectedCategoryIndex
            + (desiredCategoryIndex > selectedCategoryIndex ? 1 : -1)
        homeCategoryDirection = selectedCategoryIndex > homeCategoryTarget ? 1 : -1
        homeCategoryProgress = 0
        homeCategoryTransitioning = true
        suppressTitleRailCompletion = true
        titleRailAnimation.stop()
        suppressTitleRailCompletion = false
        titleRailAnimation.start()
        homeCategoryAnimation.start()
    }

    function moveDomain(delta) {
        if (space !== "home")
            return
        var nextIndex = Math.max(0, Math.min(domains.length - 1,
                                             desiredCategoryIndex + delta))
        if (nextIndex === desiredCategoryIndex)
            return
        desiredCategoryIndex = nextIndex
        if (homeCategoryAnimation.running)
            return
        startNextHomeCategoryHop()
        message = ""
    }

    function domainOffset(index) {
        return index - selectedCategoryIndex
    }

    function homeCategoryOffset(index) {
        if (!homeCategoryTransitioning)
            return 0
        if (index === homeCategoryFrom)
            return homeCategoryDirection * homeCategoryTravel * homeCategoryProgress
        if (index === homeCategoryTarget)
            return -homeCategoryDirection * homeCategoryTravel * (1 - homeCategoryProgress)
        return 0
    }

    function titleRailLayoutY(index, activeIndex) {
        return index * homeCategoryPitch
            + (index > activeIndex ? titleRailActiveGap : 0)
    }

    function titleRailChildY(index) {
        if (!homeCategoryTransitioning)
            return titleRailLayoutY(index, selectedCategoryIndex)
        var fromY = titleRailLayoutY(index, homeCategoryFrom)
        var targetY = titleRailLayoutY(index, homeCategoryTarget)
        return fromY + (targetY - fromY) * homeCategoryProgress
    }

    function homeCategoryChromeOpacity(index) {
        if (!homeCategoryTransitioning)
            return 1
        if (index === homeCategoryFrom && homeCategoryFrom === 2)
            return Math.max(0, 1 - homeCategoryProgress * 5)
        if (index === homeCategoryTarget && homeCategoryTarget === 2
                || index === homeCategoryTarget && homeCategoryTarget === 3)
            return Math.max(0, Math.min(1, (homeCategoryProgress - 0.72) / 0.28))
        return index === homeCategoryFrom ? 1 : 0
    }

    function moveRecent(delta) {
        if (!recentGames.length)
            return
        console.log("RECENT_NAV", "received", recentIndex, delta)
        var nextIndex = Math.max(0, Math.min(recentGames.length - 1, recentIndex + delta))
        console.log("RECENT_NAV", "requested", delta, "result", nextIndex)
        if (nextIndex === recentIndex)
            return
        recentHome.capturePresentation()
        recentIndex = nextIndex
        recentHome.beginRetarget()
        console.log("RECENT_NAV", "presentation-target", recentHome.selectedIndex)
    }

    function moveLibrary(delta) {
        if (!libraryGames.length)
            return
        libraryIndex = Math.max(0, Math.min(libraryGames.length - 1, libraryIndex + delta))
    }

    function moveLibraryLanding(delta) {
        libraryHomeLanding.moveSelection(delta)
        collectionIndex = libraryHomeLanding.selectedIndex
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
        if (space === "system") {
            return
        }
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
            libraryTransitioning = true
            libraryTransitionExpanding = true
            libraryTransitionProgress = 0
            libraryTransitionAnimation.restart()
            refreshLibrary()
            libraryContentFadeOut.stop()
            libraryContentFadeIn.restart()
            homeFadeIn.stop()
            homeFadeOut.restart()
            libraryFocus = "games"
            message = ""
        } else if (selectedCategoryIndex === 0) {
            openSystemCategory(systemHomeRailRef ? systemHomeRailRef.selectedIndex : systemCategoryIndex)
        } else if (selectedCategoryIndex === 1) {
            message = "Store space is not implemented"
        } else {
            message = "System space is not implemented"
        }
    }

    function openSystemCategory(index) {
        systemCategoryIndex = Math.max(0, Math.min(systemCategories.length - 1, index))
        systemRowIndex = 0
        systemLanding = false
        space = "system"
        console.log("SYSTEM_HOME_ACTIVATE", "category", systemCategories[systemCategoryIndex])
        refreshSystemSettings()
        console.log("SETTINGS_PAGE_OPEN", "category", systemCategories[systemCategoryIndex])
    }

    function moveSystemCategory(delta) {
        var rail = space === "home" ? systemHomeRailRef : systemLandingHome
        var oldIndex = rail.selectedIndex
        rail.moveSelection(delta)
        systemCategoryIndex = rail.selectedIndex
        if (oldIndex !== rail.selectedIndex)
            console.log("SYSTEM_HOME_NAV", "old", systemCategories[oldIndex],
                        "new", systemCategories[rail.selectedIndex])
    }

    function back() {
        if (space === "system") {
            if (systemLanding)
                space = "home"
            else {
                console.log("SETTINGS_PAGE_CLOSE", "category", systemCategories[systemCategoryIndex])
                space = "home"
                systemLanding = true
            }
            message = ""
        } else if (space === "library") {
            libraryTransitionState = "ACTIVATING"
            libraryTransitioning = true
            libraryTransitionExpanding = false
            libraryTransitionProgress = 1
            libraryTransitionAnimation.restart()
            libraryContentFadeIn.stop()
            libraryContentFadeOut.restart()
            homeFadeOut.stop()
            homeFadeIn.restart()
            libraryFocus = "games"
            message = ""
        } else {
            message = ""
        }
    }

    NumberAnimation {
        id: libraryTransitionAnimation
        target: root
        property: "libraryTransitionProgress"
        to: root.libraryTransitionExpanding ? 1 : 0
        duration: 500
        easing.type: Easing.OutQuint
        onStopped: {
            if (root.libraryTransitionExpanding) {
                root.libraryContentOpacity = 1
                root.space = "library"
                root.libraryTransitioning = false
                root.libraryTransitionState = "EXPANDED"
            } else {
                root.libraryContentOpacity = 0
                root.space = "home"
                root.libraryHandoffPending = true
                handoffTimer.restart()
            }
        }
    }

    NumberAnimation {
        id: homeCategoryAnimation
        target: root
        property: "homeCategoryProgress"
        to: 1
        duration: root.homeCategoryHopDuration
        easing.type: Easing.OutQuint
        onStopped: {
            root.homeCategoryProgress = 1
            root.homeCategoryTransitioning = false
            root.selectedCategoryIndex = root.homeCategoryTarget
            root.homeCategoryFrom = root.selectedCategoryIndex
            root.homeCategoryTarget = root.selectedCategoryIndex
            if (root.selectedCategoryIndex === root.desiredCategoryIndex)
                root.homeCategoryHopDuration = 250
            else
                root.startNextHomeCategoryHop(true)
        }
    }

    NumberAnimation {
        id: titleRailAnimation
        target: root
        property: "titleRailY"
        to: root.titleRailTargetY
        duration: root.homeCategoryHopDuration
        easing.type: Easing.OutQuint
        onStopped: {
            if (root.suppressTitleRailCompletion)
                return
            root.titleRailY = root.titleRailTargetY
        }
    }

    SequentialAnimation {
        id: homeFadeOut
        NumberAnimation {
            target: root
            property: "homeContentOpacity"
            to: 0
            duration: 100
        }
    }

    Timer {
        id: handoffTimer
        interval: 16
        repeat: false
        onTriggered: {
            root.libraryTransitioning = false
            root.libraryTransitionState = "RESTING"
            root.libraryHandoffPending = false
        }
    }

    SequentialAnimation {
        id: homeFadeIn
        PauseAnimation { duration: 400 }
        NumberAnimation {
            target: root
            property: "homeContentOpacity"
            to: 1
            duration: 100
        }
    }

    SequentialAnimation {
        id: libraryContentFadeIn
        PauseAnimation { duration: 400 }
        NumberAnimation {
            target: root
            property: "libraryContentOpacity"
            to: 1
            duration: 100
        }
    }

    SequentialAnimation {
        id: libraryContentFadeOut
        NumberAnimation {
            target: root
            property: "libraryContentOpacity"
            to: 0
            duration: 100
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
                        moveLibraryLanding(-1)
                    else if (selectedCategoryIndex === 0)
                        moveSystemCategory(-1)
                    event.accepted = true
                } else if (event.key === Qt.Key_Right) {
                    if (selectedCategoryIndex === 3)
                        moveRecent(1)
                    else if (selectedCategoryIndex === 2)
                        moveLibraryLanding(1)
                    else if (selectedCategoryIndex === 0)
                        moveSystemCategory(1)
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
            } else if (space === "system") {
                if (systemLanding && event.key === Qt.Key_Left) {
                    moveSystemCategory(-1)
                    event.accepted = true
                } else if (systemLanding && event.key === Qt.Key_Right) {
                    moveSystemCategory(1)
                    event.accepted = true
                } else if (systemLanding && event.key === Qt.Key_Up) {
                    moveSystemCategory(-4)
                    event.accepted = true
                } else if (systemLanding && event.key === Qt.Key_Down) {
                    moveSystemCategory(4)
                    event.accepted = true
                } else if (event.key === Qt.Key_Up) {
                    systemRowIndex = Math.max(0, systemRowIndex - 1)
                    event.accepted = true
                } else if (event.key === Qt.Key_Down) {
                    systemRowIndex = Math.min(Math.max(0, systemSettings.length - 1), systemRowIndex + 1)
                    event.accepted = true
                } else if (!systemLanding && event.key === Qt.Key_PageUp) {
                    systemCategoryIndex = Math.max(0, systemCategoryIndex - 1)
                    systemRowIndex = 0
                    refreshSystemSettings()
                    event.accepted = true
                } else if (!systemLanding && event.key === Qt.Key_PageDown) {
                    systemCategoryIndex = Math.min(systemCategories.length - 1, systemCategoryIndex + 1)
                    systemRowIndex = 0
                    refreshSystemSettings()
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

        LibrarySpatialSurface {
            canonicalTexture: orbitTexture
            canonicalCoordinateRoot: orbitRenderSource
            canonicalSize: Qt.size(root.width, root.height)
            progress: root.libraryTransitionProgress
            homeX: root.homeContentRailX
            homeY: root.homeActiveContentOriginY
            homeWidth: root.compactCardWidth
            homeHeight: root.libraryHomePresentationHeight
            fullscreenX: 76 * root.uiScale
            fullscreenY: 64 * root.uiScale
            fullscreenWidth: root.width - 152 * root.uiScale
            fullscreenHeight: root.height - 128 * root.uiScale
            uiScale: root.uiScale
            verticalOffset: root.homeCategoryOffset(2)
             surfaceVisible: root.space === "library" || root.libraryTransitioning
        }

        Item {
            id: homeScene
            anchors.fill: parent
            visible: root.space === "home" || root.libraryTransitioning
            opacity: root.homeContentOpacity
            Item {
                x: root.homeCategoryRailX
                y: 0
                width: root.design(250)
                height: parent.height
                clip: true
                Item {
                    id: titleRail
                    y: root.titleRailY
                    width: parent.width
                    height: parent.height

                    Repeater {
                        id: homeCategoryTitles
                        model: root.domains
                        delegate: Text {
                            required property int index
                            y: root.titleRailChildY(index)
                            visible: true
                            text: root.domains[index]
                            color: luluPalette.selectedText
                            font.family: typography.displayFamily
                            font.weight: typography.displayWeight
                            font.pixelSize: root.homeCategoryFontSize
                            font.letterSpacing: 0
                            opacity: 1
                            scale: 1
                        }
                    }
                }
            }


            Item {
                id: homeCardViewport
                x: 0
                y: root.homeActiveContentOriginY
                width: parent.width
                height: root.homeBottomBandCenterY - root.homeActiveContentOriginY
                clip: true
                // The viewport is presentation-only. Children retain full card
                // geometry so glass shaders keep their canonical scene mapping.
                Item {
                id: homeContent
                x: root.homeContentRailX
                y: 0
                width: parent.width - root.homeContentRailX - root.design(40)
                height: root.homeFocalCardHeight

                Item {
                    id: recentReveal
                    x: -root.homeContentRailX
                    y: root.homeCategoryOffset(3)
                    width: root.width
                    height: root.homeCategoryRevealHeight(3)
                    clip: true
                    visible: root.selectedCategoryIndex === 3
                        || (root.homeCategoryTransitioning
                            && (root.homeCategoryFrom === 3 || root.homeCategoryTarget === 3))
                    opacity: 1
                    RecentHome {
                        id: recentHome
                        x: root.homeContentRailX
                        y: 0
                        width: recentReveal.width
                        height: root.homeFocalCardHeight
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
                }

                Item {
                    id: libraryReveal
                    x: -root.homeContentRailX
                    y: root.homeCategoryOffset(2)
                    width: root.width
                    height: root.homeCategoryRevealHeight(2)
                    clip: true
                    visible: root.selectedCategoryIndex === 2
                        || (root.homeCategoryTransitioning
                            && (root.homeCategoryFrom === 2 || root.homeCategoryTarget === 2))
                    LibraryHome {
                        id: libraryHomeLanding
                        x: root.homeContentRailX
                        width: libraryReveal.width - root.homeContentRailX
                        height: root.homeFocalCardHeight
                        scale: libraryReveal.visible ? 1 : 0.94
                        cardHeight: root.homeFocalCardHeight
                        uiScale: root.uiScale
                        typography: typography
                        luluPalette: luluPalette
                        canonicalTexture: orbitTexture
                        canonicalCoordinateRoot: orbitRenderSource
                        canonicalSize: Qt.size(root.width, root.height)
                        compactCardWidth: root.compactCardWidth
                        transitionState: root.libraryTransitionState
                        transitionProgress: root.libraryTransitionProgress
                        transitionExpanding: root.libraryTransitionExpanding
                        contentOpacity: root.homeContentOpacity
                        selectedIndex: root.collectionIndex
                        onOpenRequested: {
                            root.collectionIndex = index
                            root.activate()
                        }
                    }
                }

                Item {
                    id: storeReveal
                    x: 0
                    y: root.homeCategoryOffset(1)
                    width: parent.width
                    height: root.homeCategoryRevealHeight(1)
                    clip: true
                    opacity: 1
                    visible: root.selectedCategoryIndex === 1
                        || (root.homeCategoryTransitioning
                            && (root.homeCategoryFrom === 1 || root.homeCategoryTarget === 1))
                    StoreHome {
                        width: storeReveal.width
                        height: root.homeFocalCardHeight
                        cardWidth: root.compactCardWidth
                        cardHeight: root.homeFocalCardHeight
                        uiScale: root.uiScale
                        typography: typography
                        luluPalette: luluPalette
                        canonicalTexture: orbitTexture
                        canonicalCoordinateRoot: orbitRenderSource
                        canonicalSize: Qt.size(root.width, root.height)
                    }
                }

                Item {
                    id: systemReveal
                    x: -root.homeContentRailX
                    y: root.homeCategoryOffset(0)
                    width: root.width
                    height: root.homeCategoryRevealHeight(0)
                    clip: true
                    opacity: 1
                    visible: root.selectedCategoryIndex === 0
                        || (root.homeCategoryTransitioning
                            && (root.homeCategoryFrom === 0 || root.homeCategoryTarget === 0))
                    SystemHome {
                        id: systemHomeRail
                        x: root.homeContentRailX
                        width: systemReveal.width - root.homeContentRailX
                        height: root.homeFocalCardHeight
                        y: 0
                        cardWidth: root.compactCardWidth
                        cardHeight: root.homeFocalCardHeight
                        categories: root.systemCategories
                        selectedIndex: root.systemCategoryIndex
                        uiScale: root.uiScale
                        typography: typography
                        luluPalette: luluPalette
                        canonicalTexture: orbitTexture
                        canonicalCoordinateRoot: orbitRenderSource
                        canonicalSize: Qt.size(root.width, root.height)
                    }
                    Component.onCompleted: root.systemHomeRailRef = systemHomeRail
                }

                }
            }
        }

        Text {
            x: root.homeCategoryRailX
            y: root.homeBottomBandCenterY - height * 0.5
            visible: false
                && root.selectedCategoryIndex < root.domains.length - 1
            text: root.domains[root.selectedCategoryIndex + 1]
            color: luluPalette.selectedText
            font.family: typography.displayFamily
            font.weight: typography.displayWeight
            font.pixelSize: root.homeCategoryFontSize
            opacity: 0.58
        }

        LibrarySpace {
            anchors.fill: parent
            visible: root.space === "library" || root.libraryTransitioning
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
             contentOpacity: root.libraryContentOpacity
            onCollectionChanged: {
                root.collectionIndex = index
                root.refreshLibrary()
            }
            onLaunchRequested: root.launchGame(game)
        }

        SystemHome {
            id: systemLandingHome
            anchors.fill: parent
            visible: root.space === "system" && root.systemLanding
            categories: root.systemCategories
            selectedIndex: root.systemCategoryIndex
            uiScale: root.uiScale
            typography: typography
            luluPalette: luluPalette
            canonicalTexture: orbitTexture
            canonicalCoordinateRoot: orbitRenderSource
            canonicalSize: Qt.size(root.width, root.height)
            onOpenRequested: root.openSystemCategory(index)
        }

        SystemSpace {
            anchors.fill: parent
            visible: root.space === "system" && !root.systemLanding
            category: root.systemCategories[root.systemCategoryIndex]
            settings: root.systemSettings
            selectedIndex: root.systemRowIndex
            uiScale: root.uiScale
            typography: typography
            luluPalette: luluPalette
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
                visible: root.space === "library" || root.libraryTransitioning
                opacity: root.libraryContentOpacity
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
                opacity: root.homeContentOpacity
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
                opacity: root.homeContentOpacity
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
