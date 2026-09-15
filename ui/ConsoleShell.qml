import QtQuick
import QtQuick.Window

Window {
    id: root
    visible: false
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

    Loader {
        id: uiAudioLoader
        active: false
        source: "UiAudioEngine.qml"
        property string pendingEvent: ""
        onLoaded: {
            if (pendingEvent) {
                var event = pendingEvent
                pendingEvent = ""
                item.play(event)
            }
        }
    }

    function audioEventForAction(action) {
        if (action === "up" || action === "down" || action === "left"
                || action === "right" || action === "leftShoulder"
                || action === "rightShoulder")
            return "navigate"
        if (action === "confirm" || action === "options")
            return "confirm"
        if (action === "back")
            return "back"
        return ""
    }

    function playAudioEvent(event) {
        if (!event)
            return
        if (!uiAudioLoader.active) {
            uiAudioLoader.pendingEvent = event
            uiAudioLoader.active = true
        } else if (uiAudioLoader.item) {
            uiAudioLoader.item.play(event)
        } else {
            uiAudioLoader.pendingEvent = event
        }
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
    readonly property real homeCompactCardWidth: compactCardWidth
    readonly property real homeInterCardGap: design(24)
    readonly property real compactCardWidth: Math.min(design(220), acceptedRecentCardHeight * 0.62)
    readonly property real compactCardHeight: acceptedRecentCardHeight
    readonly property real homeContentOriginY: homeHintTopY - acceptedRecentCardHeight - headingCardGap
    readonly property real homeActiveContentOriginY: homeHintTopY - homeFocalCardHeight
        - headingCardGap + homeHeadingCardClearance + homeCompositionOffsetY
    readonly property real selectedDomainY: homeActiveContentOriginY - homeHeadingCardClearance
        - activeHeadingHeight - headingCardGap
    property int recentIndex: 0
    property int libraryIndex: 0
    property int collectionIndex: 0
    property var libraryCollections: [{"label": "All Games", "scope": "all"}, {"label": "PC Games", "scope": "pc"}]
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
    property bool storeTransitioning: false
    property string presentationTarget: "library"
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
    property var storeAvailableGames: []
    property var storeCategories: [{"label": "All Available", "scope": "all"}]
    property var storeHomeRef: null
    property string storeError: ""
    property string message: ""
    property string launchStatus: "idle"
    property string launchTitle: ""
    property string launchGameId: ""
    property string launchToken: ""
    property bool launchOverlayVisible: false
    property bool launchOverlayRetired: false
    property bool shellWasLeft: false
    property bool gamePresentationObserved: false
    property var launchLogLines: []
    property bool gameOptionsOpen: false
    property string gameOptionsView: "menu"
    property int gameOptionsIndex: 0
    property string gameOptionsGameId: ""
    property var gameOptionsGame: null
    property var metadataResults: []
    property string metadataQuery: ""
    property string metadataTitleDraft: ""
    property string metadataError: ""
    property bool metadataBusy: false
    property int launchGeneration: 0
    property int launchStateSerial: 0
    property int launchStateApplied: 0
    property int launchStateRank: 0
    property var launchTracePrevious: ({})

    function traceLaunchMutation(name, value, reason) {
        var oldValue = launchTracePrevious[name]
        console.log("LAUNCH_TRACE", JSON.stringify({event: "MUTATION", name: name, old: oldValue, new: value, generation: launchGeneration, token: launchToken, reason: reason || "property-change"}))
        launchTracePrevious[name] = value
    }

    function traceLaunchEvent(event, details) {
        console.log("LAUNCH_TRACE", JSON.stringify({event: event, generation: launchGeneration, token: launchToken, details: details || {}}))
    }

    function traceLaunchResponse(endpoint, response, responseGeneration, responseToken, accepted, reason) {
        console.log("LAUNCH_TRACE", JSON.stringify({event: "RESPONSE", endpoint: endpoint, current_generation: launchGeneration, response_generation: responseGeneration, current_token: launchToken, response_token: responseToken || "", lifecycle: response.lifecycle || "", presentation: response.presentation || "", active: response.active === undefined ? null : response.active, game_id: response.game_id || "", appid: response.appid || "", provider: response.provider || "", active_identity: response.active_identity || null, accepted: accepted, reason: reason}))
    }

    onLaunchOverlayVisibleChanged: traceLaunchMutation("launchOverlayVisible", launchOverlayVisible)
    onLaunchOverlayRetiredChanged: traceLaunchMutation("launchOverlayRetired", launchOverlayRetired)
    onLaunchStatusChanged: traceLaunchMutation("launchStatus", launchStatus)
    onLaunchTokenChanged: traceLaunchMutation("launchToken", launchToken)
    onLaunchGenerationChanged: traceLaunchMutation("launchGeneration", launchGeneration)
    onLaunchStateSerialChanged: traceLaunchMutation("launchStateSerial", launchStateSerial)
    onLaunchStateAppliedChanged: traceLaunchMutation("launchStateApplied", launchStateApplied)
    onLaunchLogLinesChanged: traceLaunchMutation("launchLogLines", {length: launchLogLines.length}, "property-change")

    readonly property string apiUrl: "http://127.0.0.1:38123"
    readonly property var visibleRecentGame: recentGames.length ? recentGames[recentIndex] : null
    readonly property var visibleLibraryGame: libraryGames.length ? libraryGames[libraryIndex] : null
    readonly property var selectedGameForOptions: {
        if (space === "library" && libraryFocus === "games")
            return visibleLibraryGame
        if (space === "home" && selectedCategoryIndex === 3)
            return visibleRecentGame
        return null
    }
    readonly property string libraryScope: libraryCollections.length > collectionIndex
        ? libraryCollections[collectionIndex].scope : "all"

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
            syncGameOptionsGame()
        })
        refreshLibrary()
        request("/platforms", "GET", "", function(data) {
            var collections = [{"label": "All Games", "scope": "all"}, {"label": "PC Games", "scope": "pc"}]
            for (var index = 0; index < data.length; index++)
                collections.push(data[index])
            libraryCollections = collections
            if (collectionIndex >= libraryCollections.length)
                collectionIndex = 0
        })
    }

    function refreshStore() {
        var request = new XMLHttpRequest()
        request.onreadystatechange = function() {
            if (request.readyState !== XMLHttpRequest.DONE)
                return
            if (request.status !== 200) {
                storeAvailableGames = []
                storeCategories = [{"label": "All Available", "scope": "all"}]
                storeError = "Available titles unavailable"
                return
            }
            try {
                var rows = JSON.parse(request.responseText)
                var games = []
                var categories = [{"label": "All Available", "scope": "all"}]
                var categorySeen = ({})
                var seen = ({})
                for (var index = 0; index < rows.length; index++) {
                    var game = rows[index]
                    if (!game || game.availability_state !== "available"
                            || game.install_state !== "available")
                        continue
                    var gameId = String(game.game_id)
                    if (seen[gameId])
                        continue
                    seen[gameId] = true
                    games.push(game)
                    var scope = String(game.platform || "")
                    var label = String(game.platform_label || scope)
                    if (scope && !categorySeen[scope]) {
                        categorySeen[scope] = true
                        categories.push({"label": label, "scope": scope})
                    }
                }
                storeAvailableGames = games
                storeCategories = categories
                storeError = ""
            } catch (error) {
                storeAvailableGames = []
                storeCategories = [{"label": "All Available", "scope": "all"}]
                storeError = "Available titles unavailable"
            }
        }
        request.open("GET", apiUrl + "/available?provider=romm")
        request.send()
    }

    function applyLaunchState(state, generation) {
        if (generation !== launchGeneration)
            return
        var stateToken = state.launch_token || (state.last_result ? state.last_result.token : "")
        if (launchToken && stateToken !== launchToken)
            return
        var stateRank = state.lifecycle === "launch_requested" || state.lifecycle === "starting" ? 1
                      : state.lifecycle === "game" ? 2
                      : state.lifecycle === "returning" ? 3
                      : 4
        if (stateRank < launchStateRank) {
            traceLaunchEvent("STATE_DISCARDED", {lifecycle: state.lifecycle, state_rank: stateRank, current_rank: launchStateRank})
            return
        }
        launchStateRank = stateRank
        if (state.lifecycle === "launch_requested" || state.lifecycle === "starting"
                || state.lifecycle === "presentation_pending") {
            launchStatus = "launching"
            message = "Launching " + launchTitle
        } else if (state.lifecycle === "game") {
            traceLaunchEvent("TARGET_READY", {lifecycle: state.lifecycle, presentation: state.presentation || ""})
            launchStatus = "running"
            message = "Running " + launchTitle
            retireLaunchOverlay(generation)
        } else if (state.lifecycle === "returning") {
            traceLaunchEvent("GAME_EXITED", {lifecycle: state.lifecycle, presentation: state.presentation || ""})
            traceLaunchEvent("SHELL_RETURN_STARTED", {})
            launchStatus = "returning"
            message = "Returning"
        } else if (state.lifecycle === "shell") {
            launchStatus = state.last_failure_reason && stateToken === launchToken ? "failed" : "idle"
            message = launchStatus === "failed" ? "Launch failed" : ""
            launchStatusTimer.stop()
            if (launchOverlayRetired)
                launchOverlayVisible = false
        }
    }

    function retireLaunchOverlay(generation) {
        if (generation !== launchGeneration)
            return
        traceLaunchEvent("OVERLAY_RETIRED", {})
        launchOverlayRetired = true
        launchOverlayVisible = false
        launchStatusTimer.stop()
        launchLogTimer.stop()
    }

    function finishLaunchOnShellReturn() {
        traceLaunchEvent("RETURN_FAILSAFE_FIRED", {luluPresented: controllerBridge.luluPresented, gamePresentationObserved: gamePresentationObserved, launchOverlayVisible: launchOverlayVisible, launchOverlayRetired: launchOverlayRetired})
        launchStatusTimer.stop()
        launchLogTimer.stop()
        launchOverlayRetired = true
        launchOverlayVisible = false
        launchStatus = "idle"
        launchToken = ""
        launchGameId = ""
        launchLogLines = []
        shellWasLeft = false
        gamePresentationObserved = false
        launchGeneration++
    }

    function observeGamePresentation(state, generation) {
        if (generation !== launchGeneration || launchGameId.indexOf("steam:") !== 0)
            return
        if (state.lifecycle === "game" && state.presentation === "game") {
            gamePresentationObserved = true
            traceLaunchEvent("GAME_PRESENTATION_OBSERVED", {lifecycle: state.lifecycle, presentation: state.presentation, shellWasLeft: shellWasLeft})
            if (shellWasLeft && controllerBridge.luluPresented)
                finishLaunchOnShellReturn()
        }
    }

    function refreshLaunchState(generation) {
        var serial = ++launchStateSerial
        request("/state", "GET", "", function(state) {
            if (generation !== launchGeneration) {
                traceLaunchResponse("/state", state, generation, state.launch_token || (state.last_result ? state.last_result.token : ""), false, "generation-mismatch")
                return
            }
            if (serial < launchStateApplied) {
                traceLaunchResponse("/state", state, generation, state.launch_token || (state.last_result ? state.last_result.token : ""), false, "serial-regression")
                return
            }
            var responseToken = state.launch_token || (state.last_result ? state.last_result.token : "")
            observeGamePresentation(state, generation)
            if (launchToken && responseToken !== launchToken) {
                traceLaunchResponse("/state", state, generation, responseToken, false, "token-mismatch")
                return
            }
            launchStateApplied = serial
            traceLaunchResponse("/state", state, generation, responseToken, true, "apply")
            applyLaunchState(state, generation)
        }, "", generation)
    }

    function refreshLaunchLog(generation) {
        request("/launch-log", "GET", "", function(data) {
            var accepted = generation === launchGeneration && !launchOverlayRetired && data.active && data.game_id === launchGameId
            traceLaunchResponse("/launch-log", data, generation, data.token || "", accepted, accepted ? "apply" : "ignored")

            if (generation !== launchGeneration || launchOverlayRetired)
                return
            if (data.active && data.game_id === launchGameId)
                launchLogLines = data.lines
        }, "", generation)
    }

    function refreshLibrary() {
        request("/?scope=" + libraryScope, "GET", "", function(data) {
            libraryGames = data
            if (libraryIndex >= libraryGames.length)
                libraryIndex = Math.max(0, libraryGames.length - 1)
            libraryFirstVisibleRow = Math.min(libraryFirstVisibleRow,
                                               Math.max(0, Math.floor(Math.max(0, libraryGames.length - 1) / 6) - 1))
            syncGameOptionsGame()
        })
    }

    function syncGameOptionsGame() {
        if (!gameOptionsOpen || gameOptionsGameId === "")
            return
        var games = recentGames.concat(libraryGames)
        for (var index = 0; index < games.length; index++) {
            if (String(games[index].game_id) === gameOptionsGameId) {
                gameOptionsGame = games[index]
                return
            }
        }
    }

    function openSelectedGameOptions() {
        if (gameOptionsOpen)
            return
        if (selectedGameForOptions)
            openGameOptions(selectedGameForOptions)
    }

    function openGameOptions(game) {
        if (!game)
            return
        gameOptionsGame = game
        gameOptionsGameId = String(game.game_id)
        gameOptionsView = "menu"
        gameOptionsIndex = 0
        metadataError = ""
        gameOptionsOpen = true
    }

    function closeGameOptions() {
        gameOptionsOpen = false
        gameOptionsGame = null
        gameOptionsGameId = ""
        metadataResults = []
        metadataError = ""
    }

    function metadataSearch() {
        if (!gameOptionsGame)
            return
        metadataBusy = true
        metadataError = ""
        request("/metadata/search?game_id=" + encodeURIComponent(gameOptionsGameId)
                + "&query=" + encodeURIComponent(metadataQuery), "GET", "", function(data) {
            metadataBusy = false
            metadataResults = data
            gameOptionsIndex = 0
            if (!data.length)
                metadataError = "No metadata results"
        }, "Metadata search unavailable")
    }

    function metadataMutation(path, body, callback) {
        request(path, "POST", JSON.stringify(body || {}), function(data) {
            refreshCatalogue()
            if (callback)
                callback(data)
        }, "Metadata update failed")
    }

    function activateGameOptions() {
        if (!gameOptionsGame)
            return
        if (gameOptionsView === "menu") {
            if (gameOptionsIndex === 0) {
                metadataQuery = gameOptionsGame.canonical_title || gameOptionsGame.normalized_search_title
                    || gameOptionsGame.title
                metadataResults = []
                gameOptionsView = "search"
                gameOptionsIndex = 0
                metadataSearch()
            } else {
                metadataTitleDraft = gameOptionsGame.display_title_override || gameOptionsGame.title
                gameOptionsView = "edit"
                gameOptionsIndex = 0
            }
        } else if (gameOptionsView === "edit") {
            if (gameOptionsIndex === 0) {
                metadataTitleDraft = gameOptionsGame.display_title_override || gameOptionsGame.title
                gameOptionsView = "title"
            } else if (gameOptionsIndex === 1) {
                metadataMutation("/metadata/title/clear/" + encodeURIComponent(gameOptionsGameId), {}, function() {
                    gameOptionsView = "edit"
                    gameOptionsIndex = 0
                })
            } else {
                metadataMutation("/metadata/artwork/" + encodeURIComponent(gameOptionsGameId), {
                    suppressed: !Boolean(gameOptionsGame.artwork_suppressed)
                }, function() {
                    gameOptionsView = "edit"
                    gameOptionsIndex = 0
                })
            }
        } else if (gameOptionsView === "title") {
            var title = metadataTitleDraft.trim()
            if (!title)
                return
            metadataMutation("/metadata/title/" + encodeURIComponent(gameOptionsGameId), {title: title}, function() {
                gameOptionsView = "edit"
                gameOptionsIndex = 0
            })
        } else if (gameOptionsView === "search") {
            if (!metadataResults.length || !metadataResults[gameOptionsIndex])
                return
            var result = metadataResults[gameOptionsIndex]
            metadataMutation("/metadata/match/" + encodeURIComponent(gameOptionsGameId), {
                provider: "steamgriddb",
                metadata_game_id: String(result.id),
                canonical_title: String(result.title)
            }, function() {
                gameOptionsView = "menu"
                gameOptionsIndex = 0
            })
        }
    }

    function moveGameOptions(delta) {
        var count = gameOptionsView === "menu" ? 2
            : gameOptionsView === "edit" ? 3 : metadataResults.length
        if (gameOptionsView === "title")
            return
        if (count > 0)
            gameOptionsIndex = Math.max(0, Math.min(count - 1, gameOptionsIndex + delta))
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
        var column = libraryIndex % 6
        var row = Math.floor(libraryIndex / 6) + delta
        if (row < 0)
            return
        var target = row * 6 + column
        var rowStart = row * 6
        if (rowStart >= libraryGames.length)
            return
        libraryIndex = Math.min(target, libraryGames.length - 1)
        if (row >= libraryFirstVisibleRow + 2)
            libraryFirstVisibleRow = row - 1
        else if (row < libraryFirstVisibleRow)
            libraryFirstVisibleRow = row
    }

    function moveLibraryCollection(delta) {
        collectionIndex = Math.max(0, Math.min(libraryCollections.length - 1, collectionIndex + delta))
    }

    function moveStoreCategory(delta) {
        if (storeHomeRef)
            storeHomeRef.moveCategory(delta)
    }

    function moveStoreGame(delta) {
        if (storeHomeRef)
            storeHomeRef.moveGame(delta)
    }

    function moveStoreGameVertical(delta) {
        if (storeHomeRef)
            storeHomeRef.moveVertical(delta)
    }

    function launchGame(game) {
        if (!game)
            return
        var generation = ++launchGeneration
        traceLaunchEvent("LAUNCH_REQUESTED", {game_id: String(game.game_id), title: game.title})
        launchTitle = game.title
        launchGameId = String(game.game_id)
        launchToken = ""
        launchOverlayVisible = true
        traceLaunchEvent("OVERLAY_SHOWN", {game_id: launchGameId})
        launchOverlayRetired = false
        shellWasLeft = false
        gamePresentationObserved = false
        launchLogLines = ["[Lulu] Play requested: " + game.title + " / " + game.game_id]
        launchLogTimer.start()
        launchStatus = "launching"
        launchStateRank = 1
        message = "Launching " + game.title
        request("/launch/" + encodeURIComponent(game.game_id), "POST", "", function(data) {
            if (generation !== launchGeneration)
                return
            launchToken = data.token
            if (data.navigation_only) {
                launchStatusTimer.stop()
                launchStatus = "idle"
                message = ""
                return
            }
            refreshLaunchState(generation)
            launchStatusTimer.start()
            refreshCatalogue()
        }, "Launch failed", generation)
    }

    function installGame(game) {
        if (!game || launchOverlayVisible)
            return
        var generation = ++launchGeneration
        launchTitle = game.title
        launchGameId = String(game.game_id)
        launchToken = ""
        launchOverlayVisible = true
        launchOverlayRetired = false
        shellWasLeft = false
        gamePresentationObserved = false
        launchLogLines = ["[Lulu] Download requested: " + game.title + " / " + game.game_id]
        launchLogTimer.start()
        launchStatus = "installing"
        launchStateRank = 1
        message = "Opening Steam install"
        request("/install/" + encodeURIComponent(launchGameId), "POST", "", function(data) {
            if (generation !== launchGeneration)
                return
            launchToken = data.token
            refreshLaunchState(generation)
        }, "Install failed", generation)
    }

    function openSteamStore() {
        var generation = ++launchGeneration
        launchTitle = "Steam Store"
        launchGameId = "steam-store"
        launchToken = ""
        launchOverlayVisible = true
        launchOverlayRetired = false
        launchLogLines = ["[Lulu] Store requested"]
        launchLogTimer.start()
        launchStatusTimer.start()
        launchStatus = "launching"
        launchStateRank = 1
        message = "Launching Steam Store"
        request("/store/steam", "POST", "", function(data) {
            if (generation !== launchGeneration)
                return
            launchToken = data.token
            refreshLaunchState(generation)
        }, "Steam Store launch failed", generation)
    }

    function cancelLaunch() {
        if (!launchOverlayVisible)
            return
        request("/cancel", "POST", "", function(data) {
            launchStatusTimer.stop()
            launchLogLines.push("[Lulu] Launch cancelled")
            launchOverlayRetired = true
            launchOverlayVisible = false
            message = ""
        }, "Launch cancellation failed", launchGeneration)
    }

    Connections {
        target: controllerBridge
        function onValueChanged(key, value) {
            if (key === "luluPresented") {
                traceLaunchEvent(value ? "SHELL_PRESENTED" : "GAME_PRESENTED", {luluPresented: value})
                if (root.launchGameId.indexOf("steam:") === 0) {
                    if (!value) {
                        root.shellWasLeft = true
                        root.traceLaunchEvent("SHELL_LEFT_OBSERVED", {luluPresented: value})
                    } else if (root.shellWasLeft && root.gamePresentationObserved) {
                        root.finishLaunchOnShellReturn()
                    }
                }
            }
            if (key === "action" && value === "back" && root.launchOverlayVisible)
                root.cancelLaunch()
            if (key === "action")
                root.playAudioEvent(root.audioEventForAction(value))
        }
    }

    function resetMudos() {
        message = "Resetting Mudos"
        request("/reset", "POST", "", function(data) {
            message = ""
        }, "Mudos reset failed")
    }

    function activate() {
        if (gameOptionsOpen) {
            activateGameOptions()
            return
        }
        if (space === "system") {
            if (!systemLanding && systemSettings[systemRowIndex]
                    && systemSettings[systemRowIndex].key === "lulu.reset")
                resetMudos()
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
        if (space === "store") {
            if (storeHomeRef)
                storeHomeRef.activateSelected()
            return
        }

        if (selectedCategoryIndex === 3) {
            launchGame(visibleRecentGame)
        } else if (selectedCategoryIndex === 2) {
            presentationTarget = "library"
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
            presentationTarget = "store"
            storeTransitioning = true
            libraryTransitionExpanding = true
            libraryTransitionProgress = 0
            libraryContentOpacity = 0
            libraryTransitionAnimation.restart()
            libraryContentFadeOut.stop()
            libraryContentFadeIn.restart()
            homeFadeIn.stop()
            homeFadeOut.restart()
            storeHomeRef.categoryIndex = 0
            storeHomeRef.selectedIndex = 0
            refreshStore()
            message = ""
        } else {
            // Store space is not implemented for unknown future domains: message = "Store space is not implemented"
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
        if (launchOverlayVisible) {
            cancelLaunch()
            return
        }
        if (gameOptionsOpen) {
            if (gameOptionsView === "menu")
                closeGameOptions()
            else {
                gameOptionsView = "menu"
                gameOptionsIndex = 0
                metadataError = ""
            }
            return
        }
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
        } else if (space === "store") {
            presentationTarget = "store"
            storeTransitioning = true
            libraryTransitionExpanding = false
            libraryTransitionProgress = 1
            libraryTransitionAnimation.restart()
            libraryContentFadeOut.restart()
            homeFadeIn.restart()
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
                root.space = root.presentationTarget
                root.libraryTransitioning = false
                root.storeTransitioning = false
                root.libraryTransitionState = "EXPANDED"
            } else {
                root.libraryContentOpacity = 0
                root.space = "home"
                root.libraryTransitioning = false
                root.storeTransitioning = false
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
        refreshStore()
    }

    function controllerUp() {
            if (root.gameOptionsOpen) root.moveGameOptions(-1)
            else if (root.space === "home") root.moveDomain(-1)
            else if (root.space === "library") root.moveLibraryVertical(-1)
            else if (root.space === "store") root.moveStoreGameVertical(-1)
            else if (root.space === "system") {
                if (root.systemLanding) root.moveSystemCategory(-4)
                else root.systemRowIndex = Math.max(0, root.systemRowIndex - 1)
            }
    }
    function controllerDown() {
            if (root.gameOptionsOpen) root.moveGameOptions(1)
            else if (root.space === "home") root.moveDomain(1)
            else if (root.space === "library") root.moveLibraryVertical(1)
            else if (root.space === "store") root.moveStoreGameVertical(1)
            else if (root.space === "system") {
                if (root.systemLanding) root.moveSystemCategory(4)
                else root.systemRowIndex = Math.min(Math.max(0, root.systemSettings.length - 1), root.systemRowIndex + 1)
            }
    }
    function controllerLeft() {
            if (root.gameOptionsOpen) root.moveGameOptions(-1)
            else if (root.space === "home") {
                if (root.selectedCategoryIndex === 3) root.moveRecent(-1)
                else if (root.selectedCategoryIndex === 2) root.moveLibraryLanding(-1)
                else if (root.selectedCategoryIndex === 0) root.moveSystemCategory(-1)
            } else if (root.space === "library") {
                root.moveLibrary(-1)
            } else if (root.space === "store") {
                root.moveStoreGame(-1)
            } else if (root.space === "system") {
                if (root.systemLanding) root.moveSystemCategory(-1)
                else root.systemRowIndex = Math.max(0, root.systemRowIndex - 1)
            }
    }
    function controllerRight() {
            if (root.gameOptionsOpen) root.moveGameOptions(1)
            else if (root.space === "home") {
                if (root.selectedCategoryIndex === 3) root.moveRecent(1)
                else if (root.selectedCategoryIndex === 2) root.moveLibraryLanding(1)
                else if (root.selectedCategoryIndex === 0) root.moveSystemCategory(1)
            } else if (root.space === "library") {
                root.moveLibrary(1)
            } else if (root.space === "store") {
                root.moveStoreGame(1)
            } else if (root.space === "system") {
                if (root.systemLanding) root.moveSystemCategory(1)
                else root.systemRowIndex = Math.min(Math.max(0, root.systemSettings.length - 1), root.systemRowIndex + 1)
            }
    }
    function controllerShoulder(delta) {
        if (root.space === "library") root.moveLibraryCollection(delta)
        else if (root.space === "store") root.moveStoreCategory(delta)
        else if (root.space === "system" && !root.systemLanding) {
            root.systemCategoryIndex = Math.max(0, Math.min(root.systemCategories.length - 1,
                root.systemCategoryIndex + delta))
            root.systemRowIndex = 0
            root.refreshSystemSettings()
        }
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
            if (event.key === Qt.Key_X) {
                if (selectedGameForOptions)
                    openGameOptions(selectedGameForOptions)
                event.accepted = true
                return
            }
            if (gameOptionsOpen) {
                if (event.key === Qt.Key_Up || event.key === Qt.Key_Left) {
                    moveGameOptions(-1)
                    event.accepted = true
                } else if (event.key === Qt.Key_Down || event.key === Qt.Key_Right) {
                    moveGameOptions(1)
                    event.accepted = true
                } else if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter) {
                    activateGameOptions()
                    event.accepted = true
                } else if (event.key === Qt.Key_Escape || event.key === Qt.Key_Backspace) {
                    back()
                    event.accepted = true
                }
                return
            }
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
            } else if (space === "store") {
                if (event.key === Qt.Key_Up) {
                    moveStoreGameVertical(-1)
                    event.accepted = true
                } else if (event.key === Qt.Key_Down) {
                    moveStoreGameVertical(1)
                    event.accepted = true
                } else if (event.key === Qt.Key_Left) {
                    moveStoreGame(-1)
                    event.accepted = true
                } else if (event.key === Qt.Key_Right) {
                    moveStoreGame(1)
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
            fullscreenY: 32 * root.uiScale
            fullscreenWidth: root.width - 152 * root.uiScale
            fullscreenHeight: root.height - 48 * root.uiScale
            uiScale: root.uiScale
            verticalOffset: root.homeCategoryOffset(2)
             surfaceVisible: root.space === "library" || root.space === "store"
                 || root.libraryTransitioning || root.storeTransitioning
        }

        Item {
            id: homeScene
            anchors.fill: parent
            visible: root.space === "home" || root.libraryTransitioning || root.storeTransitioning
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
                         cardHeight: root.compactCardHeight
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
                         categories: root.libraryCollections
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
                        cardHeight: root.compactCardHeight
                        uiScale: root.uiScale
                        typography: typography
                        luluPalette: luluPalette
                        canonicalTexture: orbitTexture
                        canonicalCoordinateRoot: orbitRenderSource
                        canonicalSize: Qt.size(root.width, root.height)
                        onSteamStoreRequested: root.openSteamStore()
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
                        cardHeight: root.compactCardHeight
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
             collections: root.libraryCollections
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
             }
             onCategoryContentHidden: root.refreshLibrary()
             onLaunchRequested: root.launchGame(game)
         }

        StoreHome {
            id: storeHome
            anchors.fill: parent
            visible: root.space === "store" || root.storeTransitioning
            availableGames: root.storeAvailableGames
            categories: root.storeCategories
            focalCardWidth: root.homeFocalCardWidth
            focalCardHeight: root.homeFocalCardHeight
            compactCardWidth: root.compactCardWidth
            uiScale: root.uiScale
            typography: typography
            luluPalette: luluPalette
            canonicalTexture: orbitTexture
            canonicalCoordinateRoot: orbitRenderSource
            canonicalSize: Qt.size(root.width, root.height)
            errorMessage: root.storeError
            contentOpacity: root.libraryContentOpacity
            onSteamStoreRequested: root.openSteamStore()
            onInstallGameRequested: root.installGame(game)
            Component.onCompleted: root.storeHomeRef = storeHome
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
            onActionRequested: if (key === "lulu.reset") root.resetMudos()
        }

        GameOptions {
            game: root.gameOptionsGame
            view: root.gameOptionsView
            selectedIndex: root.gameOptionsIndex
            results: root.metadataResults
            query: root.metadataQuery
            titleDraft: root.metadataTitleDraft
            errorMessage: root.metadataError
            busy: root.metadataBusy
            uiScale: root.uiScale
            typography: typography
            luluPalette: luluPalette
            onActivated: root.activateGameOptions()
            onBacked: root.back()
            onQueryEdited: root.metadataQuery = value
            onTitleEdited: root.metadataTitleDraft = value
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
                    visible: root.space === "library" && root.libraryFocus === "games" && root.visibleLibraryGame !== null
                    action: "options"
                    label: "Game Options"
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
                     label: root.space === "store" ? "Download"
                           : root.selectedCategoryIndex === 3 ? "Launch"
                           : root.selectedCategoryIndex === 2 ? "Open Library" : "Select"
                    uiScale: root.uiScale
                    typography: typography
                    luluPalette: luluPalette
                }
                ControllerHint {
                    visible: root.selectedGameForOptions !== null
                    action: "options"
                    label: "Game Options"
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
        id: launchLogTimer
        interval: 500
        repeat: true
        onTriggered: root.refreshLaunchLog(root.launchGeneration)
    }

    Rectangle {
        id: launchLogOverlay
        visible: root.launchOverlayVisible && !root.launchOverlayRetired
        z: 100
        anchors.fill: parent
        clip: true
        color: Qt.rgba(0.03, 0.04, 0.07, 0.96)
        border.color: luluPalette.accent
        border.width: 1
        Text {
            x: root.design(12)
            y: root.design(8)
            width: parent.width - root.design(24)
            text: "Launching " + root.launchTitle + " (" + root.launchGameId + ")\n\nB  Cancel"
            color: luluPalette.primaryText
            font.family: typography.interfaceFamily
            font.pixelSize: typography.size("secondary", 16)
            elide: Text.ElideRight
        }
        ListView {
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.top: parent.top
            anchors.bottom: parent.bottom
            anchors.margins: root.design(32)
            anchors.topMargin: root.design(72)
            model: root.launchLogLines
            interactive: false
            clip: true
            onCountChanged: positionViewAtEnd()
            delegate: Text {
                width: launchLogOverlay.width - root.design(24)
                height: implicitHeight
                text: modelData
                color: luluPalette.secondaryText
                font.family: "monospace"
                font.pixelSize: typography.size("secondary", 10)
                wrapMode: Text.Wrap
                elide: Text.ElideRight
            }
        }
    }

    Timer {
        interval: 2000
        running: true
        repeat: true
        onTriggered: root.refreshCatalogue()
    }
}
