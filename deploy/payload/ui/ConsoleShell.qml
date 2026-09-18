import QtQuick
import QtQuick.Window

Window {
    id: root
    visible: false
    visibility: Window.FullScreen
    color: luluPalette.backdrop
    flags: Qt.FramelessWindowHint

    onVisibleChanged: {
        if (visible && presentationCoordinator.contentState
                === presentationCoordinator.hiddenState)
            presentationCoordinator.beginStartup()
    }

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
    // Persistent status chrome is positioned in root screen space. These
    // values match the settled Recent composition's System-title reference,
    // without following the animated title rail or its presentation offset.
    readonly property real statusStripRightMargin: homeCategoryRailX
    readonly property real statusStripTop: selectedDomainY
        - (domains.length - 1) * homeCategoryPitch
    readonly property real expandedContentSideMargin: design(120)
    // Frame the actual six-card visual envelope, using the same inter-card
    // gap as the backing clearance on both sides.
    readonly property real expandedGridGap: design(14)
    readonly property real expandedGridCardWidth:
        ((width - 2 * expandedContentSideMargin
            - 5 * expandedGridGap) / 6) * 0.92
    readonly property real expandedGridSlotWidth:
        6 * expandedGridCardWidth + 5 * expandedGridGap
    readonly property real expandedGridVisualWidth:
        expandedGridSlotWidth
        + (1.05 - 1.0) * expandedGridCardWidth
    readonly property real expandedShellSideMargin:
        (width - expandedGridVisualWidth) / 2 - expandedGridGap
    readonly property real expandedSurfaceChromeGap: design(18)
    readonly property real statusStripBottom: statusStripTop + systemStatusStrip.height
    readonly property real expandedHintRowTop: interactionRail.y + expandedHintRow.y
    readonly property real expandedShellTop: statusStripBottom
        + expandedSurfaceChromeGap
    readonly property real expandedShellBottom: expandedHintRowTop
        - expandedSurfaceChromeGap
    readonly property real expandedContentBottom: expandedShellBottom
    readonly property real expandedShellX: expandedShellSideMargin
    readonly property real expandedShellY: expandedShellTop
    readonly property real expandedShellWidth: width - 2 * expandedShellSideMargin
    readonly property real expandedShellHeight: expandedShellBottom - expandedShellTop
    readonly property real homeHeadingCardClearance: design(12)
    readonly property real homeCompositionOffsetY: -design(36)
    readonly property real homeHintTopY: height - design(45)
    readonly property real homeBottomBandCenterY: height - design(36)
    readonly property real acceptedRecentCardHeight: Math.min(design(375), (height - design(248 + 88)) * 0.67)
    readonly property real homeFocalCardHeight: Math.min(design(500), (height - design(248 + 88)) * 0.82)
    readonly property real homeContentRailX: design(52)
    readonly property real homeFocalCardWidth: Math.min(design(900), width - homeContentRailX - design(40), homeFocalCardHeight * 1.9)
    // Home navigation cards keep their established portrait proportion, but
    // no longer borrow the compact game-card height.
    readonly property real homeNavigationCardAspect: 0.62
    readonly property real homeNavigationCardWidth: Math.min(design(220),
        homeFocalCardHeight * homeNavigationCardAspect)
    readonly property real homeNavigationCardHeight: homeNavigationCardWidth
        / homeNavigationCardAspect
    readonly property real homeCompactCardWidth: homeNavigationCardWidth
    readonly property real homeInterCardGap: design(24)
    // Compact games use the Home navigation card geometry as their sole
    // physical footprint contract. Content and interaction remain separate.
    readonly property real compactCardWidth: homeNavigationCardWidth
    readonly property real compactCardHeight: homeNavigationCardHeight
    readonly property real compactGameCardWidth: compactCardWidth
    readonly property real homeContentOriginY: homeHintTopY - acceptedRecentCardHeight - headingCardGap
    readonly property real homeActiveContentOriginY: homeHintTopY - homeFocalCardHeight
        - headingCardGap + homeHeadingCardClearance + homeCompositionOffsetY
    readonly property real selectedDomainY: homeActiveContentOriginY - homeHeadingCardClearance
        - activeHeadingHeight - headingCardGap
    property int recentIndex: 0
    readonly property string recentSelectedGameId: recentModel && recentIndex >= 0
        && recentHome && recentIndex < recentHome.itemCount
        ? String(recentModel.gameIdAt(recentIndex)) : ""
    property int playActivationSerial: 0
    property int libraryIndex: 0
    property int collectionIndex: 0
    property var libraryCollections: [{"label": "All Games", "scope": "all"}, {"label": "PC Games", "scope": "pc"}]
    property string space: "home"
    property string downloadsReturnSpace: "home"
    property var downloadsHomeRef: null
    property int systemCategoryIndex: 0
    property var systemHomeRailRef: null
    property int systemRowIndex: 0
    property bool systemLanding: true
    property var systemCategories: ["Mudos Menu", "Plugins", "Display", "Audio", "Network", "Bluetooth", "Controllers", "Storage", "System", "Lulu"]
    property var systemSettings: []
    property string pendingMudosAction: ""
    property var standaloneProviderModes: ({})
    property var networkState: ({available: false, wifi_enabled: false, state: "unavailable",
                                 current: null, networks: [], known: [], error: ""})
    property var internetSettingsRef: null
    property var audioState: ({available: false, outputs: [], inputs: [], current_output: null,
                               current_input: null, error: ""})
    property var audioSettingsRef: null
    property var storageState: ({available: false, devices: [], targets: {game: null, emulation: null}, error: ""})
    property var storageSettingsRef: null
    property var displayState: ({available: false, displays: [], requested: {}, known_good: {}, selected: null, error: ""})
    property var displaySettingsRef: null
    property var controllerState: ({controllers: {}, navigation_controller_id: ""})
    property var controllerSettingsRef: null
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
        homeBottomBandCenterY - selectedDomainY - homeCategoryPitch
            - activeHeadingHeight * 0.5)
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
    property var libraryGames: []
    property var storeAvailableGames: []
    property var acquisitionJobs: ({})
    property var acquisitionCompletionSeen: ({})
    property var storeCategories: [{"label": "All Available", "scope": "all"}]
    property var storeHomeRef: null
    property string storeError: ""
    property string message: ""
    property var credentialRequest: ({status: "idle"})
    property string credentialValue: ""
    property var credentialTarget: ({kind: "", plugin: "", name: ""})
    property bool credentialKeyboardShown: false
    property bool credentialKeyboardShowAttempted: false
    property string pluginDetailId: ""
    property string launchStatus: "idle"
    property string launchTitle: ""
    property string launchGameId: ""
    property string launchToken: ""
    property bool launchOverlayEnabled: controllerBridge.launchOverlayEnabled === true
    // Development-only parity switch for the stationary landing-card specimen.
    property bool catalogueRefreshTimerDisabled: true
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
    property var pendingHomeLaunch: null
    property string pendingHomeLaunchPhase: "idle"
    property string launchLifecycle: "shell"
    property bool returnPreparationStarted: false
    property bool returnPresentationPending: false
    property bool returnWatchActive: false
    property bool returnAlreadyHandled: false
    property bool returnStateObserved: false
    property bool returnPresentationObserved: false
    property bool returnStateRequestInFlight: false
    property bool returnAwayObserved: false
    readonly property bool homeLaunchGated: pendingHomeLaunch !== null
        || returnPresentationPending
        || returnPreparationStarted
        || presentationCoordinator.contentState !== presentationCoordinator.presentedState
    readonly property bool launchOverlayEffectiveVisible: launchOverlayVisible
        && launchOverlayEnabled && !launchOverlayRetired

    PresentationCoordinator {
        id: presentationCoordinator
        titleCount: root.domains.length
    }

    Connections {
        target: presentationCoordinator
        function onContentHiddenReached() {
            root.finishHiddenHomeLaunch()
        }
        function onContentPresentedReached() {
            root.traceLaunchEvent("COORDINATOR_PRESENTED", {})
            if (root.returnPresentationPending) {
                root.traceLaunchEvent("RECENT_RECONCILE_BEGIN", {})
                recentHome.reconcilePresentation()
                root.traceLaunchEvent("RECENT_PRESENTATION_RELEASED", {})
                root.returnPresentationPending = false
            }
            root.returnPreparationStarted = false
            console.log("HOME_INPUT_UNLOCK_ATTEMPT", JSON.stringify({
                homeLaunchGated: root.homeLaunchGated,
                coordinatorState: root.presentationCoordinator.contentState,
                returnPresentationPending: root.returnPresentationPending
            }))
            root.traceLaunchEvent("HOME_INPUT_UNLOCKED", {})
        }
    }

    Connections {
        target: systemStatus
        function onAcquisitionSnapshotChanged() {
            root.applyAcquisitionSnapshot(systemStatus.acquisitionSnapshot)
        }
        function onAcquisitionAvailabilityChanged() {
            if (!systemStatus.acquisitionAvailable)
                root.applyAcquisitionSnapshot("{\"jobs\":[],\"activeDownloadCount\":0}")
        }
    }

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
    readonly property var catalogueRecentModel: recentModel
    readonly property var visibleRecentGame: recentSelectedGameId !== ""
        ? catalogueModel.game(recentSelectedGameId) : null
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

    function request(path, method, body, callback, failureMessage, generation, failureCallback) {
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
                    if (failureCallback)
                        failureCallback()
                }
            }
        }
        request.open(method, apiUrl + path)
        request.send(body || "")
    }

    function catalogueContentsEqual(current, incoming) {
        if (current.length !== incoming.length)
            return false
        for (var index = 0; index < current.length; index++) {
            if (JSON.stringify(current[index]) !== JSON.stringify(incoming[index]))
                return false
        }
        return true
    }

    function refreshRecentCatalogue(done) {
        // Legacy request("/?scope=recent"...) remains available to tools,
        // but production Recent updates now come from recentModel.
        if (done)
            done()
    }

    function refreshPlatformsCatalogue(done) {
        request("/platforms", "GET", "", function(data) {
            var collections = [{"label": "All Games", "scope": "all"}, {"label": "PC Games", "scope": "pc"}]
            for (var index = 0; index < data.length; index++)
                collections.push(data[index])
            libraryCollections = collections
            if (collectionIndex >= libraryCollections.length)
                collectionIndex = 0
            if (done)
                done()
        })
    }

    function refreshCatalogue() {
        refreshLibrary()
        refreshPlatformsCatalogue()
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

    function applyAcquisitionSnapshot(snapshot) {
        try {
            var parsed = typeof snapshot === "string" ? JSON.parse(snapshot) : snapshot
            var jobs = ({})
            var rows = parsed.jobs || []
            for (var index = 0; index < rows.length; index++) {
                var job = rows[index]
                if (String(job.provider || "") === "steam"
                        || String(job.provider || "") === "romm")
                    jobs[String(job.content_identity || "")] = job
                if (String(job.state || "") === "completed"
                        && !acquisitionCompletionSeen[String(job.job_id || "")]) {
                    acquisitionCompletionSeen[String(job.job_id || "")] = true
                    refreshStore()
                    refreshCatalogue()
                }
            }
            acquisitionJobs = jobs
        } catch (error) {
            acquisitionJobs = ({})
        }
    }

    // Compatibility/reconnect resynchronization only. Live updates arrive via
    // SystemStatusBridge.acquisitionSnapshotChanged.
    function refreshAcquisitionJobs() {
        request("/acquisition", "GET", "", function(snapshot) {
            root.applyAcquisitionSnapshot(snapshot)
        })
    }

    Timer {
        id: acquisitionJobsTimer
        interval: 30000
        repeat: true
        running: true
        onTriggered: root.refreshAcquisitionJobs()
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
        launchLifecycle = state.lifecycle
        if (returnWatchActive)
            traceLaunchEvent("RETURN_STATE_OBSERVED", {
                source: "state", lifecycle: state.lifecycle,
                luluPresented: controllerBridge.luluPresented === true
            })
        if (state.lifecycle !== "shell")
            returnAwayObserved = true
        if (state.lifecycle === "shell"
                && (returnAwayObserved || (launchToken && stateToken === launchToken)))
            returnStateObserved = true
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
            traceLaunchEvent("GAME_EXIT_OBSERVED", {lifecycle: state.lifecycle, presentation: state.presentation || ""})
            traceLaunchEvent("SHELL_RETURN_STARTED", {})
            launchStatus = "returning"
            message = "Returning"
        } else if (state.lifecycle === "shell") {
            launchStatus = state.last_failure_reason && stateToken === launchToken ? "failed" : "idle"
            message = launchStatus === "failed" ? "Launch failed" : ""
            launchStatusTimer.stop()
            if (launchOverlayRetired)
                launchOverlayVisible = false
            evaluateReturnReadiness("state")
        }
    }

    function startReturnWatch() {
        returnWatchActive = true
        returnAlreadyHandled = false
        returnStateObserved = false
        returnPresentationObserved = false
        returnAwayObserved = false
        traceLaunchEvent("RETURN_WATCH_STARTED", {})
        returnObserverTimer.start()
    }

    function stopReturnWatch(reason) {
        if (!returnWatchActive)
            return
        returnWatchActive = false
        returnObserverTimer.stop()
        traceLaunchEvent("RETURN_WATCH_STOPPED", {reason: reason || "complete"})
    }

    function evaluateReturnReadiness(source) {
        if (!returnWatchActive || returnAlreadyHandled)
            return false
        var presented = controllerBridge.luluPresented === true
        if (presented && returnStateObserved && !returnPresentationObserved) {
            returnPresentationObserved = true
            traceLaunchEvent("RETURN_PRESENTATION_OBSERVED", {source: source})
        }
        if (launchLifecycle === "shell" && returnStateObserved && presented) {
            returnAlreadyHandled = true
            traceLaunchEvent("RETURN_READY", {source: source})
            return stopAndPrepareHome()
        }
        return false
    }

    function stopAndPrepareHome() {
        stopReturnWatch("ready")
        return prepareAndPresentHome()
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
        stopAndPrepareHome()
    }

    function prepareAndPresentHome() {
        if (returnPreparationStarted || launchLifecycle !== "shell"
                || controllerBridge.luluPresented !== true)
            return false
        stopReturnWatch("prepare")
        returnPreparationStarted = true
        returnPresentationPending = true
        traceLaunchEvent("RETURN_PREPARE", {})
        pendingHomeLaunch = null
        pendingHomeLaunchPhase = "idle"
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
        libraryTransitioning = false
        storeTransitioning = false
        libraryTransitionState = "RESTING"
        if (presentationCoordinator.contentHidden) {
            traceLaunchEvent("ENTRANCE_REQUESTED", {})
            presentationCoordinator.beginStartup()
        }
        return true
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
            evaluateReturnReadiness("state")
        }, "", generation)
    }

    function refreshReturnState(generation) {
        if (!returnWatchActive || returnStateRequestInFlight)
            return
        returnStateRequestInFlight = true
        request("/state", "GET", "", function(state) {
            returnStateRequestInFlight = false
            if (generation !== launchGeneration || !returnWatchActive)
                return
            launchLifecycle = state.lifecycle || launchLifecycle
            traceLaunchEvent("RETURN_STATE_OBSERVED", {
                source: "poll", lifecycle: launchLifecycle,
                luluPresented: controllerBridge.luluPresented === true
            })
            var stateToken = state.launch_token || (state.last_result
                    ? state.last_result.token : "")
            if (launchLifecycle !== "shell")
                returnAwayObserved = true
            if (launchLifecycle === "shell"
                    && (returnAwayObserved || (launchToken && stateToken === launchToken)))
                returnStateObserved = true
            evaluateReturnReadiness("poll")
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

    function refreshLibrary(done) {
        request("/?scope=" + libraryScope, "GET", "", function(data) {
            libraryGames = data
            if (libraryIndex >= libraryGames.length)
                libraryIndex = Math.max(0, libraryGames.length - 1)
            libraryFirstVisibleRow = Math.min(libraryFirstVisibleRow,
                                               Math.max(0, Math.floor(Math.max(0, libraryGames.length - 1) / 6) - 1))
            syncGameOptionsGame()
            if (done)
                done()
        })
    }

    function refreshCataloguePair(group) {
        if (group === "recent-library") {
            refreshLibrary()
        } else if (group === "recent-platforms") {
            refreshPlatformsCatalogue()
        } else if (group === "library-platforms") {
            refreshLibrary()
            refreshPlatformsCatalogue()
        }
    }

    function refreshCatalogueSerial() {
        refreshLibrary(function() {
            refreshPlatformsCatalogue()
        })
    }

    function syncGameOptionsGame() {
        if (!gameOptionsOpen || gameOptionsGameId === "")
            return
        var games = []
        if (visibleRecentGame)
            games.push(visibleRecentGame)
        games = games.concat(libraryGames)
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
        if (systemCategories[systemCategoryIndex] === "Mudos Menu") {
            refreshMudosMenu()
            return
        }
        if (systemCategories[systemCategoryIndex] === "Plugins") {
            if (root.pluginDetailId !== "") {
                request("/plugins/" + root.pluginDetailId, "GET", "", function(data) {
                    systemSettings = data.options
                    systemRowIndex = Math.min(systemRowIndex, Math.max(0, systemSettings.length - 1))
                }, "Plugin unavailable")
                return
            }
            request("/plugins", "GET", "", function(data) {
                var rows = []
                for (var i = 0; i < data.length; i++) {
                    rows.push({key: "plugin.open:" + data[i].id, label: data[i].name,
                               kind: "action", value: data[i].health, writable: true})
                }
                systemSettings = rows
                systemRowIndex = Math.min(systemRowIndex, Math.max(0, rows.length - 1))
            }, "Plugins unavailable")
            return
        }
        request("/settings?category=" + encodeURIComponent(systemCategories[systemCategoryIndex]),
                "GET", "", function(data) {
                    systemSettings = data
                    systemRowIndex = Math.min(systemRowIndex, Math.max(0, data.length - 1))
                })
    }

    function refreshNetworkState() {
        request("/network", "GET", "", function(data) {
            root.networkState = data
            if (root.internetSettingsRef)
                root.internetSettingsRef.networkData = data
        })
    }

    function refreshAudioState() {
        request("/audio", "GET", "", function(data) {
            root.audioState = data
            if (root.audioSettingsRef) root.audioSettingsRef.audioData = data
        })
    }

    Timer {
        id: networkRefreshTimer
        interval: 2000
        repeat: true
        running: root.space === "system" && !root.systemLanding
            && root.systemCategories[root.systemCategoryIndex] === "Network"
        onTriggered: root.refreshNetworkState()
    }

    Timer {
        id: audioRefreshTimer
        interval: 1000
        repeat: true
        running: root.space === "system" && !root.systemLanding
            && root.systemCategories[root.systemCategoryIndex] === "Audio"
        onTriggered: root.refreshAudioState()
    }

    Timer {
        id: credentialTimer
        interval: 500
        repeat: true
        // This must remain active while idle so a backend-created request can
        // wake the UI. OSK activation itself is separately single-flight.
        running: true
        onTriggered: root.request("/credential", "GET", "", function(data) {
            root.credentialRequest = data
        })
    }

    Timer {
        id: credentialFocusTimer
        interval: 300
        repeat: true
        running: root.credentialRequest.status === "requested" || root.credentialRequest.status === "waiting"
        onTriggered: {
            credentialInput.forceActiveFocus()
            if (!root.credentialKeyboardShown && !root.credentialKeyboardShowAttempted) {
                root.credentialKeyboardShowAttempted = true
                root.request("/keyboard/show", "POST", "", function() {
                    root.credentialKeyboardShown = true
                }, "Keyboard unavailable", undefined, function() {
                    root.credentialKeyboardShowAttempted = false
                })
            }
        }
    }

    Rectangle {
        anchors.fill: parent
        visible: root.credentialRequest.status === "requested" || root.credentialRequest.status === "waiting"
        z: 1000
        color: luluPalette.backdrop
        Text {
            anchors.centerIn: parent
            anchors.verticalCenterOffset: -150
            text: root.credentialRequest.title + "\n" + root.credentialRequest.prompt
                  + (root.credentialRequest.help_text ? "\n" + root.credentialRequest.help_text : "")
            color: luluPalette.primaryText
            font.pixelSize: 30
            horizontalAlignment: Text.AlignHCenter
        }
        TextInput {
            id: credentialInput
            anchors.centerIn: parent
            width: 700
            height: 70
            focus: parent.visible
            echoMode: root.credentialRequest.secret ? TextInput.Password : TextInput.Normal
            text: root.credentialValue
            color: luluPalette.primaryText
            font.pixelSize: 28
            horizontalAlignment: TextInput.AlignHCenter
            onTextChanged: root.credentialValue = text
        }
        Text {
            anchors.centerIn: parent
            anchors.verticalCenterOffset: 100
            text: root.credentialRequest.status === "waiting" ? "Waiting…  A: continue   B: cancel" : "A: submit   B: cancel"
            color: luluPalette.secondaryText
            font.pixelSize: 20
        }
    }

    Timer {
        id: storageRefreshTimer
        interval: 2000
        repeat: true
        running: root.space === "system" && !root.systemLanding
            && root.systemCategories[root.systemCategoryIndex] === "Storage"
        onTriggered: root.refreshStorageState()
    }

    function audioOperation(action, deviceId, volume, inputDevice, muted) {
        request("/audio/" + action, "POST",
                JSON.stringify({id: deviceId, volume: volume, input: inputDevice, muted: muted}),
                function(data) {
                    root.audioState = data
                    if (root.audioSettingsRef) root.audioSettingsRef.audioData = data
                }, "Audio operation failed")
    }

    function refreshStorageState() {
        request("/storage", "GET", "", function(data) {
            root.storageState = data
            if (root.storageSettingsRef) root.storageSettingsRef.storageData = data
        })
    }

    function refreshDisplayState() {
        request("/display", "GET", "", function(data) {
            root.displayState = data
            if (root.displaySettingsRef) root.displaySettingsRef.displayData = data
        })
    }

    function refreshControllerState() {
        request("/state", "GET", "", function(data) {
            root.controllerState = data.controller || ({controllers: {}, navigation_controller_id: ""})
            if (root.controllerSettingsRef) root.controllerSettingsRef.controllerData = root.controllerState
        })
    }

    function controllerOperation(action, id, player) {
        request("/controller/" + action, "POST", JSON.stringify({id: id, player: player}),
                function(data) {
                    root.controllerState = data.controller || ({controllers: {}, navigation_controller_id: ""})
                    if (root.controllerSettingsRef) root.controllerSettingsRef.controllerData = root.controllerState
                }, "Controller policy update failed")
    }

    function applyDisplay(output, width, height, refresh) {
        request("/display/apply", "POST", JSON.stringify({output: output, width: width, height: height, refresh: refresh}),
                function(data) {
                    root.displayState = data
                    if (root.displaySettingsRef) root.displaySettingsRef.displayData = data
                    if (root.displaySettingsRef) root.displaySettingsRef.message = "Display saved; restarting session"
                    request("/reset", "POST", "", function(ignored) {}, "Display session restart failed")
                }, "Display mode is unavailable")
    }

    function storageOperation(action, deviceId, kind) {
        request("/storage/" + action, "POST", JSON.stringify({id: deviceId, kind: kind}),
                function(data) {
                    root.storageState = data
                    if (root.storageSettingsRef) root.storageSettingsRef.storageData = data
                    if (root.storageSettingsRef && action === "target")
                        root.storageSettingsRef.message = kind === "game" ? "Game Install Storage selected" : "Emulation Storage selected"
                    if (root.storageSettingsRef && action === "target-default") {
                        root.storageSettingsRef.message = kind === "game" ? "Game Install Storage reset" : "Emulation Storage reset"
                        // Restore discovery from the existing internal library;
                        // selecting a removable target never silently migrates
                        // or invalidates the existing catalogue.
                        request("/refresh", "POST", "", function(data) {
                            // Reconcile every provider after restoring the
                            // internal policy, including the Steam library.
                            root.refreshCatalogue()
                        })
                    }
                }, "Storage operation failed")
    }

    function networkOperation(action, ssid, password) {
        if (action === "keyboard-show") {
            request("/keyboard/show", "POST", "", function(data) {})
            return
        }
        var payload = {}
        var endpoint = "/network/" + action
        if (action === "wifi") payload.enabled = password === "true"
        if (action === "connect") {
            payload.ssid = ssid
            payload.password = password
        }
        if (action === "forget") payload.ssid = ssid
        request(endpoint, "POST", JSON.stringify(payload), function(data) {
            root.networkState = data
            if (root.internetSettingsRef) root.internetSettingsRef.networkData = data
            if (action === "connect" && root.internetSettingsRef) {
                root.internetSettingsRef.credentialView = false
                request("/keyboard/hide", "POST", "", function(hidden) {})
            }
        }, "Network operation failed")
    }

    function startNextHomeCategoryHop(chained) {
        if (selectedCategoryIndex === desiredCategoryIndex)
            return
        homeCategoryHopDuration = chained ? 100 : 250
        homeCategoryFrom = selectedCategoryIndex
        homeCategoryTarget = selectedCategoryIndex
            + (desiredCategoryIndex > selectedCategoryIndex ? 1 : -1)
        homeCategoryDirection = selectedCategoryIndex > homeCategoryTarget ? 1 : -1
        homeCategoryTransitioning = true
        homeCategoryProgress = 0
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

    function homeCategoryPresentationVelocity(index) {
        if (!homeCategoryTransitioning
                || (homeCategoryFrom !== index && homeCategoryTarget !== index))
            return 0
        return presentationCoordinator.categoryPresentationVelocity(
            homeCategoryProgress, homeCategoryDirection,
            homeCategoryTravel, homeCategoryHopDuration)
    }

    function titleRailLayoutY(index, activeIndex) {
        var titleItem = homeCategoryTitles.itemAt(index)
        var titleHeight = titleItem ? titleItem.height : activeHeadingHeight
        var activeGap = Math.max(0, homeBottomBandCenterY - selectedDomainY
            - homeCategoryPitch - titleHeight * 0.5)
        return index * homeCategoryPitch
            + (index > activeIndex ? activeGap : 0)
    }

    function titleRailChildY(index) {
        if (!homeCategoryTransitioning)
            return titleRailLayoutY(index, selectedCategoryIndex)

        var fromY = titleRailLayoutY(index, homeCategoryFrom)
        var targetY = titleRailLayoutY(index, homeCategoryTarget)
        return fromY + (targetY - fromY) * homeCategoryProgress
    }

    function homeCategoryTitleSelectedProgress(index) {
        if (!homeCategoryTransitioning)
            return index === selectedCategoryIndex ? 1 : 0
        if (index === homeCategoryFrom)
            return 1 - homeCategoryProgress
        if (index === homeCategoryTarget)
            return homeCategoryProgress
        return 0
    }

    function homeCategoryTitleColor(index) {
        var progress = homeCategoryTitleSelectedProgress(index)
        return Qt.rgba(
            luluPalette.navigationText.r
                + (luluPalette.headingAccent.r - luluPalette.navigationText.r) * progress,
            luluPalette.navigationText.g
                + (luluPalette.headingAccent.g - luluPalette.navigationText.g) * progress,
            luluPalette.navigationText.b
                + (luluPalette.headingAccent.b - luluPalette.navigationText.b) * progress,
            1)
    }

    function homeCategoryTitleOpacityForSelection(index, selectedIndex) {
        var distance = Math.abs(index - selectedIndex)
        var minimumOpacity = 0.30
        var maximumDistance = 3.0
        return Math.max(minimumOpacity,
            1.0 - distance * ((1.0 - minimumOpacity) / maximumDistance))
    }

    function homeCategoryTitleOpacity(index) {
        var fromIndex = homeCategoryTransitioning
            ? homeCategoryFrom : selectedCategoryIndex
        var targetIndex = homeCategoryTransitioning
            ? homeCategoryTarget : selectedCategoryIndex
        var progress = homeCategoryTransitioning ? homeCategoryProgress : 1
        var fromOpacity = homeCategoryTitleOpacityForSelection(index, fromIndex)
        var targetOpacity = homeCategoryTitleOpacityForSelection(index, targetIndex)
        return fromOpacity + (targetOpacity - fromOpacity) * progress
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
        if (!recentHome || !recentHome.itemCount)
            return
        console.log("RECENT_NAV", "received", recentIndex, delta)
        var nextIndex = Math.max(0, Math.min(recentHome.itemCount - 1, recentIndex + delta))
        console.log("RECENT_NAV", "requested", delta, "result", nextIndex)
        if (nextIndex === recentIndex)
            return
        recentHome.capturePresentation()
        recentIndex = nextIndex
        recentHome.beginRetarget()
        console.log("RECENT_NAV", "currentRootIndex", recentIndex,
                    "delta", delta, "requestedIndex", nextIndex,
                    "selectedIndex", recentHome.selectedIndex,
                    "retargetTarget", recentHome.selectedIndex)
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

    function moveDownloads(delta) {
        if (downloadsHomeRef)
            downloadsHomeRef.moveSelection(delta)
    }

    function openDownloads(returnSpace) {
        downloadsReturnSpace = returnSpace === "downloads" ? "home" : returnSpace
        space = "downloads"
        message = ""
    }

    function launchGame(game) {
        if (!game)
            return
        var generation = ++launchGeneration
        launchLifecycle = "launch_requested"
        returnPreparationStarted = false
        returnAlreadyHandled = false
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
        }, "Launch failed", generation, function() {
            if (generation !== launchGeneration)
                return
            pendingHomeLaunch = null
            pendingHomeLaunchPhase = "idle"
            launchLifecycle = "shell"
            stopReturnWatch("launch-failed")
            returnAlreadyHandled = false
            returnPresentationPending = true
            launchOverlayRetired = true
            launchOverlayVisible = false
            presentationCoordinator.beginStartup()
        })
    }

    function launchProviderMenu(provider) {
        if (!provider || root.launchOverlayEffectiveVisible)
            return
        var generation = ++launchGeneration
        launchLifecycle = "launch_requested"
        launchTitle = provider.name + " Menu"
        launchGameId = "provider:" + provider.id + ":standalone"
        launchToken = ""
        launchOverlayVisible = true
        launchOverlayRetired = false
        shellWasLeft = false
        gamePresentationObserved = false
        launchStatus = "launching"
        launchStateRank = 1
        message = "Launching " + launchTitle
        request("/mudos/provider", "POST", JSON.stringify({id: provider.id}), function(data) {
            if (generation !== launchGeneration) return
            launchToken = data.token
            refreshLaunchState(generation)
            launchStatusTimer.start()
        }, "Provider launch failed", generation)
    }

    function recentGameById(gameId) {
        return catalogueModel ? catalogueModel.game(gameId) : null
    }

    function beginPendingHomeLaunch(game) {
        if (!game || homeLaunchGated
                || presentationCoordinator.contentState
                    !== presentationCoordinator.presentedState)
            return false
        pendingHomeLaunch = game
        pendingHomeLaunchPhase = "feedback"
        returnPreparationStarted = false
        returnPresentationPending = false
        console.log("RECENT_LAUNCH_SELECTION", JSON.stringify({
            gameId: String(game.game_id),
            rootIndex: recentIndex,
            recentIndex: recentHome.selectedIndex,
            order: recentHome.modelOrder(recentModel)
        }))
        playActivationSerial++
        traceLaunchEvent("PLAY_FEEDBACK_STARTED", {game_id: String(game.game_id)})
        return true
    }

    function completePendingHomeLaunch(gameId) {
        if (pendingHomeLaunchPhase !== "feedback" || !pendingHomeLaunch
                || String(pendingHomeLaunch.game_id) !== String(gameId))
            return
        pendingHomeLaunchPhase = "exiting"
        recentHome.freezePresentation()
        traceLaunchEvent("PRESENTATION_FREEZE", {})
        traceLaunchEvent("PLAY_FEEDBACK_COMPLETED", {game_id: String(gameId)})
        if (!presentationCoordinator.beginContentExit()) {
            pendingHomeLaunch = null
            pendingHomeLaunchPhase = "idle"
        }
    }

    function finishHiddenHomeLaunch() {
        if (pendingHomeLaunchPhase !== "exiting" || !pendingHomeLaunch)
            return
        var game = pendingHomeLaunch
        pendingHomeLaunchPhase = "launching"
        pendingHomeLaunch = null
        traceLaunchEvent("HOME_HIDDEN_LAUNCH_HANDOFF", {game_id: String(game.game_id)})
        launchGame(game)
        startReturnWatch()
    }

    function installGame(game) {
        if (!game || launchOverlayEffectiveVisible)
            return
        var generation = ++launchGeneration
        launchTitle = game.title
        launchGameId = String(game.game_id)
        launchToken = ""
        // Downloads use the Store card's acquisition overlay. Do not open the
        // launch overlay: its Back action is a launch cancellation boundary,
        // while SteamCMD cancellation is intentionally unsupported.
        launchOverlayVisible = false
        launchOverlayRetired = true
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
            refreshAcquisitionJobs()
        }, "Install failed", generation)
    }

    function retryAcquisition(jobId) {
        if (!jobId)
            return
        request("/acquisition/retry/" + encodeURIComponent(jobId), "POST", "", function(data) {
            root.applyAcquisitionSnapshot(systemStatus.acquisitionSnapshot)
        }, "Retry failed")
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
        if (!launchOverlayEffectiveVisible)
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
                traceLaunchEvent("LULU_PRESENTED_CHANGED", {value: value})
                if (value === true)
                    evaluateReturnReadiness("signal")
                if (root.launchGameId.indexOf("steam:") === 0) {
                    if (!value) {
                        root.shellWasLeft = true
                        root.traceLaunchEvent("SHELL_LEFT_OBSERVED", {luluPresented: value})
                    } else if (root.shellWasLeft) {
                        root.refreshLaunchState(root.launchGeneration)
                    }
                }
                if (value === true && root.returnWatchActive)
                    root.refreshReturnState(root.launchGeneration)
            }
            if (key === "requestedSurface" && value === "downloads") {
                root.openDownloads(root.space)
                root.request("/surface/clear", "POST", "", function(data) {})
            }
            if (key === "action" && value === "back" && root.launchOverlayEffectiveVisible)
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

    function refreshMudosMenu() {
        root.request("/mudos-menu", "GET", "", function(providers) {
            var rows = [
                {key: "mudos.reset", label: "Reset Mudos", kind: "action", value: "", writable: true},
                {key: "mudos.metadata", label: "Refresh Metadata", kind: "action", value: "", writable: true},
                {key: "mudos.library", label: "Refresh Library Catalogue", kind: "action", value: "", writable: true},
                {key: "mudos.downloads", label: "Refresh Available Downloads Catalogue", kind: "action", value: "", writable: true},
                {key: "mudos.reboot", label: "Reboot", kind: "action", value: "", writable: true},
                {key: "mudos.shutdown", label: "Shutdown", kind: "action", value: "", writable: true}
            ]
            for (var i = 0; i < providers.length; i++) {
                root.standaloneProviderModes[providers[i].id] = providers[i].controller_mode || "game"
                rows.push({key: "mudos.provider:" + providers[i].id,
                           label: providers[i].name + " Menu", kind: "action", value: "", writable: true})
            }
            root.systemSettings = rows
            root.systemRowIndex = Math.min(root.systemRowIndex, Math.max(0, rows.length - 1))
        }, "Mudos Menu unavailable")
    }

    function activateMudosAction(key) {
        var destructive = (key === "mudos.reset" || key === "mudos.reboot" || key === "mudos.shutdown")
        if (destructive && root.pendingMudosAction !== key) {
            root.pendingMudosAction = key
            root.message = "Press A again to confirm " + root.systemSettings[root.systemRowIndex].label
            return
        }
        root.pendingMudosAction = ""
        var path = ""
        if (key === "mudos.reset") path = "/reset"
        else if (key === "mudos.metadata") path = "/mudos/refresh-metadata"
        else if (key === "mudos.library") path = "/mudos/refresh-library"
        else if (key === "mudos.downloads") path = "/mudos/refresh-downloads"
        else if (key === "mudos.reboot") path = "/mudos/reboot"
        else if (key === "mudos.shutdown") path = "/mudos/shutdown"
        else if (key.indexOf("mudos.provider:") === 0) {
            var providerId = key.substring(15)
            root.launchProviderMenu({id: providerId,
                                     name: root.systemSettings[root.systemRowIndex].label.replace(/ Menu$/, "")})
            return
        }
        if (path) {
            root.message = key === "mudos.metadata" ? "Refreshing metadata…" :
                key === "mudos.library" ? "Refreshing library…" :
                key === "mudos.downloads" ? "Refreshing available downloads…" : "Working…"
            root.request(path, "POST", "", function(data) { root.message = "" }, "Mudos action failed")
        }
    }

    function activate() {
        if (credentialRequest.status === "requested" || credentialRequest.status === "waiting") {
            root.lastCredentialValue = credentialValue
            root.request("/credential/submit", "POST", JSON.stringify({id: credentialRequest.id, value: credentialValue}),
                         function(data) {
                             var target = credentialTarget
                             credentialValue = ""
                             credentialRequest = data
                              if (target.kind === "romm-pair")
                                  root.request("/plugins/romm/pair", "POST", JSON.stringify({code: root.lastCredentialValue}), function(result) {
                                      root.message = "RomM paired"
                                      root.refreshSystemSettings()
                                  }, "RomM pairing failed: check that the code is new and unexpired")
                              else if (target.kind === "secret")
                                 root.request("/plugins/" + target.plugin + "/secret/" + target.name,
                                     "POST", JSON.stringify({value: root.lastCredentialValue}), function(result) {
                                         if (result.verification && result.verification.status === "authenticated")
                                             root.message = "SteamCMD signed in"
                                         else if (result.verification && result.verification.status === "challenge-required")
                                             root.message = "SteamCMD requires a Steam Guard code"
                                         else
                                             root.message = "Secret saved; SteamCMD authentication could not be verified"
                                     }, "Secret save failed")
                             else if (target.kind === "setting")
                                 root.request("/plugins/" + target.plugin + "/setting/" + target.name,
                                     "POST", JSON.stringify({value: root.lastCredentialValue}), function() {}, "Setting save failed")
                             root.lastCredentialValue = ""
                             root.request("/keyboard/hide", "POST", "", function() {
                                 root.credentialKeyboardShown = false
                                 root.credentialKeyboardShowAttempted = false
                             })
                         },
                         function() { root.lastCredentialValue = ""; root.message = "Credential rejected" })
            return
        }
        if (root.homeLaunchGated)
            return
        if (gameOptionsOpen) {
            activateGameOptions()
            return
        }
        if (space === "system") {
            if (!systemLanding && (systemCategories[systemCategoryIndex] === "Mudos Menu"
                                   || systemCategories[systemCategoryIndex] === "Plugins")
                    && systemSettings[systemRowIndex]) {
                var selectedKey = systemSettings[systemRowIndex].key
                if (selectedKey.indexOf("plugin.open:") === 0) {
                    root.pluginDetailId = selectedKey.substring(12)
                    root.systemRowIndex = 0
                    root.refreshSystemSettings()
                } else if (selectedKey === "plugin.steam.open")
                    root.request("/plugins/steam/signin", "POST", "", function(data) {
                        root.message = "Steam sign-in surface opened"
                    }, "Plugin sign-in failed")
                else if (selectedKey === "plugin.steamcmd.username")
                    root.beginPluginCredential("steam", "username", "SteamCMD Username", "Username", "setting", false)
                else if (selectedKey === "plugin.steamcmd.password")
                    root.beginPluginCredential("steam", "password", "SteamCMD Password", "Password", "secret", true)
                else if (selectedKey === "plugin.steamcmd.password.clear")
                    root.request("/plugins/steam/secret/password/clear", "POST", "", function() { root.refreshSystemSettings() }, "Secret clear failed")
                else if (selectedKey === "plugin.romm.url")
                    root.beginPluginCredential("romm", "url", "RomM URL", "Server URL", "setting", false)
                else if (selectedKey === "plugin.romm.api_key")
                    root.beginPluginCredential("romm", "api-key", "Pair RomM Device", "Code (XXXX-XXXX)", "romm-pair", false)
                else if (selectedKey === "plugin.romm.api_key.clear")
                    root.request("/plugins/romm/secret/api-key/clear", "POST", "", function() { root.refreshSystemSettings() }, "Secret clear failed")
                else if (selectedKey.indexOf("mudos.") === 0)
                    activateMudosAction(selectedKey)
                return
            }
            if (!systemLanding && systemCategories[systemCategoryIndex] === "Network"
                    && internetSettingsRef) {
                internetSettingsRef.activate()
                return
            }
            if (!systemLanding && systemCategories[systemCategoryIndex] === "Audio"
                    && audioSettingsRef) {
                audioSettingsRef.activate()
                return
            }
            if (!systemLanding && systemCategories[systemCategoryIndex] === "Display"
                    && displaySettingsRef) {
                displaySettingsRef.activate()
                return
            }
            if (!systemLanding && systemCategories[systemCategoryIndex] === "Controllers"
                    && controllerSettingsRef) {
                controllerSettingsRef.activate()
                return
            }
            if (!systemLanding && systemCategories[systemCategoryIndex] === "Storage"
                    && storageSettingsRef) {
                storageSettingsRef.activate()
                return
            }
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
        if (space === "downloads") {
            if (downloadsHomeRef)
                downloadsHomeRef.activateSelected()
            return
        }

        if (selectedCategoryIndex === 3) {
            beginPendingHomeLaunch(visibleRecentGame)
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

    property string lastCredentialValue: ""
    function beginPluginCredential(plugin, name, title, prompt, kind, secret) {
        credentialTarget = ({plugin: plugin, name: name, kind: kind})
        credentialKeyboardShown = false
        credentialKeyboardShowAttempted = false
        request("/credential/begin", "POST", JSON.stringify({title: title, prompt: prompt,
                input_type: secret ? "secret" : "text", secret: secret, max_length: 4096}),
                function(data) { credentialRequest = data }, "Credential editor unavailable")
    }

    function openSystemCategory(index) {
        systemCategoryIndex = Math.max(0, Math.min(systemCategories.length - 1, index))
        systemRowIndex = 0
        systemLanding = false
        space = "system"
        console.log("SYSTEM_HOME_ACTIVATE", "category", systemCategories[systemCategoryIndex])
        refreshSystemSettings()
        if (systemCategories[systemCategoryIndex] === "Mudos Menu")
            refreshMudosMenu()
        if (systemCategories[systemCategoryIndex] === "Network")
            refreshNetworkState()
        if (systemCategories[systemCategoryIndex] === "Audio")
            refreshAudioState()
        if (systemCategories[systemCategoryIndex] === "Storage")
            refreshStorageState()
        if (systemCategories[systemCategoryIndex] === "Display")
            refreshDisplayState()
        if (systemCategories[systemCategoryIndex] === "Controllers")
            refreshControllerState()
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
        if (credentialRequest.status === "requested" || credentialRequest.status === "waiting") {
            root.request("/credential/cancel", "POST", JSON.stringify({id: credentialRequest.id}),
                         function(data) {
                             credentialRequest = data
                             root.request("/keyboard/hide", "POST", "", function() {
                                 root.credentialKeyboardShown = false
                                 root.credentialKeyboardShowAttempted = false
                             })
                         }, "Credential cancellation failed")
            return
        }
        if (launchOverlayEffectiveVisible) {
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
        if (space === "system" && !systemLanding && systemCategories[systemCategoryIndex] === "Plugins"
                && pluginDetailId !== "") {
            pluginDetailId = ""
            systemRowIndex = 0
            refreshSystemSettings()
            return
        }
        if (space === "system" && !systemLanding
                && systemCategories[systemCategoryIndex] === "Storage" && storageSettingsRef
                && storageSettingsRef.back())
            return
        if (space === "system" && !systemLanding
                && systemCategories[systemCategoryIndex] === "Display" && displaySettingsRef
                && displaySettingsRef.back())
            return
        if (space === "system" && !systemLanding
                && systemCategories[systemCategoryIndex] === "Controllers" && controllerSettingsRef
                && controllerSettingsRef.view !== "main"
                && controllerSettingsRef.back())
            return
        if (space === "system") {
            if (!systemLanding && systemCategories[systemCategoryIndex] === "Network"
                    && internetSettingsRef && internetSettingsRef.credentialView) {
                internetSettingsRef.credentialView = false
                request("/keyboard/hide", "POST", "", function(data) {})
                return
            }
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
        } else if (space === "downloads") {
            space = downloadsReturnSpace || "home"
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
            // Preserve the animated destination while the category state
            // completion waits for the companion animation.
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
        if (systemStatus)
            root.applyAcquisitionSnapshot(systemStatus.acquisitionSnapshot)
        refreshCatalogue()
        refreshStore()
    }

    function controllerUp() {
            console.log("CONTROLLER_QML", "up", "gated", root.homeLaunchGated,
                        "space", root.space)
            if (root.homeLaunchGated) return
            if (root.gameOptionsOpen) root.moveGameOptions(-1)
            else if (root.space === "home") root.moveDomain(-1)
            else if (root.space === "library") root.moveLibraryVertical(-1)
            else if (root.space === "store") root.moveStoreGameVertical(-1)
            else if (root.space === "downloads") root.moveDownloads(-1)
            else if (root.space === "system") {
                if (root.systemLanding) root.moveSystemCategory(-4)
                else if (root.systemCategories[root.systemCategoryIndex] === "Network" && root.internetSettingsRef)
                    root.internetSettingsRef.move(-1)
                else if (root.systemCategories[root.systemCategoryIndex] === "Audio" && root.audioSettingsRef)
                    root.audioSettingsRef.move(-1)
                else if (root.systemCategories[root.systemCategoryIndex] === "Storage" && root.storageSettingsRef)
                    root.storageSettingsRef.move(-1)
                else if (root.systemCategories[root.systemCategoryIndex] === "Display" && root.displaySettingsRef)
                    root.displaySettingsRef.move(-1)
                else if (root.systemCategories[root.systemCategoryIndex] === "Controllers" && root.controllerSettingsRef)
                    root.controllerSettingsRef.move(-1)
                else root.systemRowIndex = Math.max(0, root.systemRowIndex - 1)
            }
    }
    function controllerDown() {
            console.log("CONTROLLER_QML", "down", "gated", root.homeLaunchGated,
                        "space", root.space)
            if (root.homeLaunchGated) return
            if (root.gameOptionsOpen) root.moveGameOptions(1)
            else if (root.space === "home") root.moveDomain(1)
            else if (root.space === "library") root.moveLibraryVertical(1)
            else if (root.space === "store") root.moveStoreGameVertical(1)
            else if (root.space === "downloads") root.moveDownloads(1)
            else if (root.space === "system") {
                if (root.systemLanding) root.moveSystemCategory(4)
                else if (root.systemCategories[root.systemCategoryIndex] === "Network" && root.internetSettingsRef)
                    root.internetSettingsRef.move(1)
                else if (root.systemCategories[root.systemCategoryIndex] === "Audio" && root.audioSettingsRef)
                    root.audioSettingsRef.move(1)
                else if (root.systemCategories[root.systemCategoryIndex] === "Storage" && root.storageSettingsRef)
                    root.storageSettingsRef.move(1)
                else if (root.systemCategories[root.systemCategoryIndex] === "Display" && root.displaySettingsRef)
                    root.displaySettingsRef.move(1)
                else if (root.systemCategories[root.systemCategoryIndex] === "Controllers" && root.controllerSettingsRef)
                    root.controllerSettingsRef.move(1)
                else root.systemRowIndex = Math.min(Math.max(0, root.systemSettings.length - 1), root.systemRowIndex + 1)
            }
    }
    function controllerLeft() {
            console.log("CONTROLLER_QML", "left", "gated", root.homeLaunchGated,
                        "space", root.space)
            if (root.homeLaunchGated) return
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
                else if (root.systemCategories[root.systemCategoryIndex] === "Network" && root.internetSettingsRef)
                    root.internetSettingsRef.move(-1)
                else if (root.systemCategories[root.systemCategoryIndex] === "Audio" && root.audioSettingsRef)
                    root.audioSettingsRef.adjust(-5)
                else if (root.systemCategories[root.systemCategoryIndex] === "Storage" && root.storageSettingsRef)
                    root.storageSettingsRef.move(-1)
                else if (root.systemCategories[root.systemCategoryIndex] === "Display" && root.displaySettingsRef)
                    root.displaySettingsRef.move(-1)
                else if (root.systemCategories[root.systemCategoryIndex] === "Controllers" && root.controllerSettingsRef)
                    root.controllerSettingsRef.move(-1)
                else root.systemRowIndex = Math.max(0, root.systemRowIndex - 1)
            }
    }
    function controllerRight() {
            console.log("CONTROLLER_QML", "right", "gated", root.homeLaunchGated,
                        "space", root.space)
            if (root.homeLaunchGated) return
            if (root.gameOptionsOpen) root.moveGameOptions(1)
            else if (root.space === "home") {
                if (root.selectedCategoryIndex === 3) root.moveRecent(1)
                else if (root.selectedCategoryIndex === 2) root.moveLibraryLanding(1)
                else if (root.selectedCategoryIndex === 0) root.moveSystemCategory(1)
            } else if (root.space === "library") {
                root.moveLibrary(1)
            } else if (root.space === "store") {
                root.moveStoreGame(1)
            } else if (root.space === "downloads") {
                root.moveDownloads(1)
            } else if (root.space === "system") {
                if (root.systemLanding) root.moveSystemCategory(1)
                else if (root.systemCategories[root.systemCategoryIndex] === "Network" && root.internetSettingsRef)
                    root.internetSettingsRef.move(1)
                else if (root.systemCategories[root.systemCategoryIndex] === "Audio" && root.audioSettingsRef)
                    root.audioSettingsRef.adjust(5)
                else if (root.systemCategories[root.systemCategoryIndex] === "Storage" && root.storageSettingsRef)
                    root.storageSettingsRef.move(1)
                else if (root.systemCategories[root.systemCategoryIndex] === "Display" && root.displaySettingsRef)
                    root.displaySettingsRef.move(1)
                else if (root.systemCategories[root.systemCategoryIndex] === "Controllers" && root.controllerSettingsRef)
                    root.controllerSettingsRef.move(1)
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
        presentationCoordinator: presentationCoordinator
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

    Timer {
        interval: 1200
        running: true
        repeat: false
        onTriggered: console.log("MUDOS_RENDER_CHAIN_QML",
            "window", root.width, root.height,
            "dprUnavailableInQml", "see_native_log",
            "orbitRenderSource", orbitRenderSource.width, orbitRenderSource.height,
            "orbitTextureLogical", orbitTexture.width, orbitTexture.height,
            "orbitTextureRequested", orbitTexture.textureSize.width,
                orbitTexture.textureSize.height,
            "sourceRect", orbitTexture.sourceRect.x, orbitTexture.sourceRect.y,
                orbitTexture.sourceRect.width, orbitTexture.sourceRect.height)
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
            if (root.homeLaunchGated) {
                event.accepted = true
                return
            }
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
            } else if (space === "downloads") {
                if (event.key === Qt.Key_Up) {
                    moveDownloads(-1)
                    event.accepted = true
                } else if (event.key === Qt.Key_Down) {
                    moveDownloads(1)
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
                         id: librarySpatialSurface
                         canonicalTexture: orbitTexture
                         canonicalCoordinateRoot: orbitRenderSource
                         canonicalSize: Qt.size(root.width, root.height)
             progress: root.libraryTransitionProgress
            homeX: root.homeContentRailX
            homeY: root.homeActiveContentOriginY
             homeWidth: root.homeNavigationCardWidth
            homeHeight: root.libraryHomePresentationHeight
            fullscreenX: root.expandedShellX
            fullscreenY: root.expandedShellY
            fullscreenWidth: root.expandedShellWidth
            fullscreenHeight: root.expandedShellHeight
             uiScale: root.uiScale
             verticalOffset: root.homeCategoryOffset(2)
             transparentOutsideMask: true
              surfaceVisible: root.space === "library" || root.space === "store"
                 || root.libraryTransitioning || root.storeTransitioning
        }

        Item {
            id: homeScene
            anchors.fill: parent
            visible: presentationCoordinator.contentVisible
                && (root.space === "home" || root.libraryTransitioning || root.storeTransitioning)
            opacity: root.homeContentOpacity
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
                        recentModel: root.catalogueRecentModel
                        presentationCoordinator: presentationCoordinator
                        selectedIndex: root.recentIndex
                        playActivationSerial: root.playActivationSerial
                         focalCardWidth: root.homeFocalCardWidth
                         focalCardHeight: root.homeFocalCardHeight
                         compactCardWidth: root.compactGameCardWidth
                         compactCardHeight: root.compactCardHeight
                        railGap: root.homeInterCardGap
                        focalScale: 0.67
                        uiScale: root.uiScale
                        typography: typography
                        luluPalette: luluPalette
                         canonicalTexture: orbitTexture
                         canonicalCoordinateRoot: orbitRenderSource
                         canonicalSize: Qt.size(root.width, root.height)
                         categoryPresentationOffset: root.homeCategoryOffset(3)
                         onSelectionIndexRequested: {
                             console.log("RECENT_RECONCILE",
                                         "selectionIndexRequested", index,
                                         "oldRootIndex", root.recentIndex)
                             root.recentIndex = index
                             console.log("RECENT_RECONCILE",
                                         "resultingRootIndex", root.recentIndex,
                                         "resultingSelectedIndex", recentHome.selectedIndex)
                         }
                        onSelectionGameChanged: {
                             root.syncGameOptionsGame()
                         }
                          onActivationRequested: root.beginPendingHomeLaunch(
                             root.recentGameById(gameId))
                         onPlayFeedbackCompleted: root.completePendingHomeLaunch(gameId)
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
                          cardHeight: root.homeNavigationCardHeight
                        uiScale: root.uiScale
                        typography: typography
                        luluPalette: luluPalette
                        canonicalTexture: orbitTexture
                        canonicalCoordinateRoot: orbitRenderSource
                        canonicalSize: Qt.size(root.width, root.height)
                          compactCardWidth: root.homeNavigationCardWidth
                         presentationCoordinator: presentationCoordinator
                         categoryProgress: root.homeCategoryProgress
                         categoryTransitioning: root.homeCategoryTransitioning
                         categoryFrom: root.homeCategoryFrom
                         categoryTarget: root.homeCategoryTarget
                         categoryDirection: root.homeCategoryDirection
                         categoryMotionVelocity: root.homeCategoryPresentationVelocity(2)
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
                         cardWidth: root.homeNavigationCardWidth
                         cardHeight: root.homeNavigationCardHeight
                        uiScale: root.uiScale
                        typography: typography
                        luluPalette: luluPalette
                         canonicalTexture: orbitTexture
                         canonicalCoordinateRoot: orbitRenderSource
                         canonicalSize: Qt.size(root.width, root.height)
                         presentationCoordinator: presentationCoordinator
                         categoryProgress: root.homeCategoryProgress
                         categoryTransitioning: root.homeCategoryTransitioning
                         categoryFrom: root.homeCategoryFrom
                         categoryTarget: root.homeCategoryTarget
                         categoryDirection: root.homeCategoryDirection
                         categoryMotionVelocity: root.homeCategoryPresentationVelocity(1)
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
                         cardWidth: root.homeNavigationCardWidth
                         cardHeight: root.homeNavigationCardHeight
                        categories: root.systemCategories
                        selectedIndex: root.systemCategoryIndex
                        uiScale: root.uiScale
                        typography: typography
                        luluPalette: luluPalette
                        canonicalTexture: orbitTexture
                         canonicalCoordinateRoot: orbitRenderSource
                          canonicalSize: Qt.size(root.width, root.height)
                           presentationCoordinator: presentationCoordinator
                          categoryProgress: root.homeCategoryProgress
                          categoryTransitioning: root.homeCategoryTransitioning
                          categoryFrom: root.homeCategoryFrom
                          categoryTarget: root.homeCategoryTarget
                          categoryDirection: root.homeCategoryDirection
                          categoryMotionVelocity: root.homeCategoryPresentationVelocity(0)
                      }
                    Component.onCompleted: root.systemHomeRailRef = systemHomeRail
                }

                }
            }
        }

        // Title choreography has its own screen-space viewport. It is a
        // direct child of the input surface so Home content clips cannot
        // shorten the animated travel envelope.
        Item {
            id: titlePresentationViewport
            x: 0
            y: 0
            width: root.width
            height: parent.height
            z: 20
            clip: true
            visible: presentationCoordinator.contentVisible
                && (root.space === "home" || root.libraryTransitioning || root.storeTransitioning)
            opacity: root.homeContentOpacity

            Item {
                id: titleRail
                x: root.homeCategoryRailX
                y: root.titleRailY
                width: parent.width
                height: parent.height

                Repeater {
                    id: homeCategoryTitles
                    model: root.domains
                    delegate: Item {
                        required property int index
                        readonly property real titleBlurPadding: presentationCoordinator
                            ? presentationCoordinator.motionBlurMaxPixels : 64
                        width: titleText.width
                        height: titleText.height
                        x: presentationCoordinator.titleOffset(index,
                            root.homeCategoryRailX, titleText.width)
                        y: root.titleRailChildY(index)
                        visible: true

                        Text {
                            id: titleText
                            width: implicitWidth
                            height: implicitHeight
                            text: root.domains[index].toUpperCase()
                            color: root.homeCategoryTitleColor(index)
                            font.family: typography.displayFamily
                            font.weight: typography.displayWeight
                            font.pixelSize: root.homeCategoryFontSize
                            font.letterSpacing: 5 * root.uiScale
                            // The blur source is captured by titleMotionBlur;
                            // keep the source opaque and fade the visible copy.
                            opacity: 1
                            scale: 1
                        }

                        DirectionalMotionBlur {
                            id: titleMotionBlur
                            x: -titleBlurPadding
                            y: -titleBlurPadding
                            width: titleText.width + 2 * titleBlurPadding
                            height: titleText.height + 2 * titleBlurPadding
                            sourceItem: titleText
                            sourceRect: Qt.rect(-titleBlurPadding, -titleBlurPadding,
                                titleText.width + 2 * titleBlurPadding,
                                titleText.height + 2 * titleBlurPadding)
                            blurPixels: presentationCoordinator
                                ? presentationCoordinator.titleSignedBlurPixels(index,
                                    root.homeCategoryRailX, titleText.width) : 0
                            opacity: root.homeCategoryTitleOpacity(index)
                        }
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
             contentSideMargin: root.expandedContentSideMargin
             firstVisibleRow: root.libraryFirstVisibleRow
             contentBottom: root.expandedContentBottom
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
            acquisitionJobs: root.acquisitionJobs
            categories: root.storeCategories
            focalCardWidth: root.homeFocalCardWidth
            focalCardHeight: root.homeFocalCardHeight
             compactCardWidth: root.compactCardWidth
             contentSideMargin: root.expandedContentSideMargin
             uiScale: root.uiScale
            typography: typography
            luluPalette: luluPalette
            canonicalTexture: orbitTexture
            canonicalCoordinateRoot: orbitRenderSource
            canonicalSize: Qt.size(root.width, root.height)
            contentBottom: root.expandedContentBottom
            errorMessage: root.storeError
            contentOpacity: root.libraryContentOpacity
            onSteamStoreRequested: root.openSteamStore()
            onInstallGameRequested: root.installGame(game)
            onDownloadsRequested: root.openDownloads("store")
            Component.onCompleted: root.storeHomeRef = storeHome
        }

        DownloadsHome {
            id: downloadsHome
            anchors.fill: parent
            visible: root.space === "downloads"
            snapshot: systemStatus.acquisitionSnapshot
            uiScale: root.uiScale
            typography: typography
            luluPalette: luluPalette
            canonicalTexture: orbitTexture
            canonicalCoordinateRoot: orbitRenderSource
            canonicalSize: Qt.size(root.width, root.height)
            onRetryRequested: root.retryAcquisition(jobId)
            onBackRequested: root.back()
            Component.onCompleted: root.downloadsHomeRef = downloadsHome
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
                && root.systemCategories[root.systemCategoryIndex] !== "Network"
            category: root.systemCategories[root.systemCategoryIndex]
            settings: root.systemSettings
            selectedIndex: root.systemRowIndex
            uiScale: root.uiScale
            typography: typography
            luluPalette: luluPalette
            onActionRequested: {
                if (root.systemCategories[root.systemCategoryIndex] === "Mudos Menu")
                    root.activateMudosAction(key)
                else if (key === "lulu.reset") root.resetMudos()
            }
        }

        InternetSettings {
            id: internetSettings
            anchors.fill: parent
            visible: root.space === "system" && !root.systemLanding
                && root.systemCategories[root.systemCategoryIndex] === "Network"
            networkData: root.networkState
            selectedIndex: 0
            uiScale: root.uiScale
            typography: typography
            luluPalette: luluPalette
            Component.onCompleted: root.internetSettingsRef = internetSettings
            onOperationRequested: root.networkOperation(action, ssid, password)
            onBackRequested: root.back()
        }

        AudioSettings {
            id: audioSettings
            anchors.fill: parent
            visible: root.space === "system" && !root.systemLanding
                && root.systemCategories[root.systemCategoryIndex] === "Audio"
            audioData: root.audioState
            selectedIndex: 0
            uiScale: root.uiScale
            typography: typography
            luluPalette: luluPalette
            Component.onCompleted: root.audioSettingsRef = audioSettings
            onOperationRequested: root.audioOperation(action, deviceId, volume, inputDevice, muted)
            onBackRequested: root.back()
        }

        StorageSettings {
            id: storageSettings
            anchors.fill: parent
            visible: root.space === "system" && !root.systemLanding
                && root.systemCategories[root.systemCategoryIndex] === "Storage"
            storageData: root.storageState
            selectedIndex: 0
            uiScale: root.uiScale
            typography: typography
            luluPalette: luluPalette
            Component.onCompleted: root.storageSettingsRef = storageSettings
            onOperationRequested: root.storageOperation(action, deviceId, kind)
            onBackRequested: root.back()
        }

        DisplaySettings {
            id: displaySettings
            anchors.fill: parent
            visible: root.space === "system" && !root.systemLanding
                && root.systemCategories[root.systemCategoryIndex] === "Display"
            displayData: root.displayState
            uiScale: root.uiScale
            typography: typography
            luluPalette: luluPalette
            Component.onCompleted: root.displaySettingsRef = displaySettings
            onApplyRequested: root.applyDisplay(output, width, height, refresh)
            onBackRequested: root.back()
        }

        ControllerSettings {
            id: controllerSettings
            anchors.fill: parent
            visible: root.space === "system" && !root.systemLanding
                && root.systemCategories[root.systemCategoryIndex] === "Controllers"
            controllerData: root.controllerState
            uiScale: root.uiScale
            typography: typography
            luluPalette: luluPalette
            Component.onCompleted: root.controllerSettingsRef = controllerSettings
            onOperationRequested: root.controllerOperation(action, controllerId, player)
            onRefreshRequested: root.refreshControllerState()
            onBackRequested: root.back()
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

        SystemStatusStrip {
            id: systemStatusStrip
            z: 50
            anchors.top: parent.top
            anchors.right: parent.right
            anchors.topMargin: root.statusStripTop
            anchors.rightMargin: root.statusStripRightMargin
            compact: false
            uiScale: root.uiScale
            typography: typography
            luluPalette: luluPalette
            activeDownloadCount: systemStatus ? systemStatus.activeDownloadCount : 0
            controllers: controllerBridge.controllers
            bluetoothAvailable: systemStatus ? systemStatus.bluetoothPowered : false
            networkAvailable: systemStatus ? systemStatus.networkConnected : false
            networkConnectionType: systemStatus ? systemStatus.networkConnectionType : ""
        }

        Item {
            id: interactionRail
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.bottom: parent.bottom
            height: root.design(72)

            Row {
                id: expandedHintRow
                // Size to the visible hints so the complete group, rather
                // than a content-column box, is centered on the screen.
                width: implicitWidth
                anchors.horizontalCenter: parent.horizontalCenter
                anchors.verticalCenter: parent.verticalCenter
                visible: presentationCoordinator.contentVisible
                    && (root.space === "library" || root.space === "store"
                        || root.libraryTransitioning || root.storeTransitioning)
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
                    label: root.space === "library" ? "Launch" : "Download"
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
                // Keep the hint group centered independently of its contents,
                // selected card, and the surrounding content columns.
                width: implicitWidth
                anchors.horizontalCenter: parent.horizontalCenter
                anchors.verticalCenter: parent.verticalCenter
                visible: presentationCoordinator.contentVisible
                    && root.space !== "library" && root.space !== "store"
                    && !root.libraryTransitioning && !root.storeTransitioning
                y: presentationCoordinator.hintsOffset()
                opacity: root.homeContentOpacity * presentationCoordinator.hintsOpacity()
                spacing: root.design(14)

                ControllerHint {
                    action: "navigation"
                      label: root.selectedCategoryIndex === 3 ? "Navigation" : "Navigate"
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
        id: returnObserverTimer
        interval: 150
        repeat: true
        onTriggered: root.refreshReturnState(root.launchGeneration)
    }

    Timer {
        id: launchLogTimer
        interval: 500
        repeat: true
        onTriggered: root.refreshLaunchLog(root.launchGeneration)
    }

    Rectangle {
        id: launchLogOverlay
        visible: root.launchOverlayEffectiveVisible
        z: 100
        anchors.fill: parent
        clip: true
        color: luluPalette.launchOverlaySurface
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
        interval: 100
        running: true
        repeat: true
        onTriggered: {
            var group = controllerBridge.consumeDiagnosticRefreshRequest()
            if (group === "all")
                root.refreshCatalogue()
            else if (group === "recent")
                root.refreshRecentCatalogue()
            else if (group === "library")
                root.refreshLibrary()
            else if (group === "platforms")
                root.refreshPlatformsCatalogue()
            else if (group === "recent-library" || group === "recent-platforms"
                     || group === "library-platforms")
                root.refreshCataloguePair(group)
            else if (group === "serial-all")
                root.refreshCatalogueSerial()

        }
    }

    Timer {
        interval: 2000
        running: !root.catalogueRefreshTimerDisabled
        repeat: true
        onTriggered: root.refreshCatalogue()
    }
}
