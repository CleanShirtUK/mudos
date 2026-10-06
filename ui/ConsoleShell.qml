import QtQuick
import "OnboardingBack.js" as OnboardingBack
import "InstallableProjection.js" as InstallableProjection
import "HomeDomains.js" as HomeDomains
import "MudosAssetCatalog.js" as MudosAssetCatalog
import QtQuick.Window
import QtQuick.Controls

    Window {
    id: root
    visible: false
    visibility: Window.FullScreen
    color: luluPalette.backdrop
    flags: Qt.FramelessWindowHint

    onVisibleChanged: { }

    readonly property bool recentDomainAvailable: HomeDomains.recentVisible(
        recentHome ? recentHome.itemCount : 0,
        homeCategoryTransitioning, homeCategoryFrom, homeCategoryTarget)
    readonly property var domains: HomeDomains.categories(recentDomainAvailable)
    property int selectedCategoryIndex: 3
    property int desiredCategoryIndex: 3
    function syncRecentDomain() {
        if (recentHome && recentHome.itemCount > 0) {
            // The initial Home selection remains Recent when the catalogue
            // arrives before the intro. Later arrivals do not steal focus.
            if (startupLifecycle !== "HOME" && !homeCategoryTransitioning) {
                selectedCategoryIndex = 3
                desiredCategoryIndex = 3
                homeCategoryFrom = 3
                homeCategoryTarget = 3
                titleRailY = selectedDomainY - 3 * homeCategoryPitch
            }
            return
        }
        desiredCategoryIndex = HomeDomains.clampSelection(desiredCategoryIndex, 0)
        if (homeCategoryTransitioning)
            return // Let the current hop settle, then continue to Library.
        if (selectedCategoryIndex === 3) {
            selectedCategoryIndex = 2
            homeCategoryFrom = 2
            homeCategoryTarget = 2
            homeCategoryProgress = 1
            titleRailY = selectedDomainY - 2 * homeCategoryPitch
        }
    }
    function focusRecentForReturn() {
        if (!recentHome || recentHome.itemCount <= 0)
            return
        desiredCategoryIndex = 3
        selectedCategoryIndex = 3
        homeCategoryFrom = 3
        homeCategoryTarget = 3
        homeCategoryDirection = 0
        homeCategoryProgress = 1
        homeCategoryTransitioning = false
        suppressTitleRailCompletion = true
        titleRailAnimation.stop()
        suppressTitleRailCompletion = false
        titleRailY = selectedDomainY - 3 * homeCategoryPitch
    }
    property bool onboardingOpen: false
    property bool onboardingNetworkSettings: false
    property bool onboardingCompletionPending: false
    property bool onboardingSetupCompleted: false
    property bool onboardingWifiAvailable: true
    readonly property bool perfDiagnostics: typeof mudosPerfDiagnostics !== "undefined"
        && mudosPerfDiagnostics
    property int perfFrameCount: 0
    property int perfSlowFrameCount: 0
    property real perfFrameTotalMs: 0
    property real perfWorstFrameMs: 0
    readonly property real referenceWidth: 1280
    readonly property real referenceHeight: 720
    readonly property real uiScale: Math.min(width / referenceWidth, height / referenceHeight)
    function design(value) { return value * uiScale }

    function recordPerfFrame(frameMs) {
        if (!perfDiagnostics || frameMs <= 0 || frameMs > 1000)
            return
        perfFrameCount += 1
        perfFrameTotalMs += frameMs
        perfWorstFrameMs = Math.max(perfWorstFrameMs, frameMs)
        if (frameMs > 33.3)
            perfSlowFrameCount += 1
        if (perfFrameCount >= 120) {
            console.log("MUDOS_FRAME_WINDOW", "frames", perfFrameCount,
                "avg_ms", (perfFrameTotalMs / perfFrameCount).toFixed(2),
                "worst_ms", perfWorstFrameMs.toFixed(2),
                "slow_over_33ms", perfSlowFrameCount,
                "fps", (1000 * perfFrameCount / perfFrameTotalMs).toFixed(1))
            perfFrameCount = 0
            perfSlowFrameCount = 0
            perfFrameTotalMs = 0
            perfWorstFrameMs = 0
        }
    }

    FrameAnimation {
        running: root.perfDiagnostics
        onTriggered: root.recordPerfFrame(frameTime * 1000)
    }

    Typography {
        id: typography
        uiScale: root.uiScale
    }

    LuluPalette {
        id: luluPalette
    }

    UiAudioEngine { id: uiAudioEngine }

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
        uiAudioEngine.play(event)
    }

    function loadOnboardingState() {
        request("/onboarding", "GET", "", function(state) {
            if (state.status === "completed") {
                onboardingSetupCompleted = true
                if (onboardingOpen) {
                    onboardingCompletionPending = true
                    onboardingOpen = false
                    onboardingNetworkSettings = false
                    if (startupLibraryReady) {
                        startupLifecycle = "READY_FOR_INTRO"
                        tryBeginStartup()
                    }
                }
            }
            if (state.required) {
                onboardingOpen = true
                if (systemStatus && systemStatus.networkOnline) {
                    onboardingNetworkSettings = false
                    space = "home"
                }
                request("/network", "GET", "", function(network) {
                    onboardingWifiAvailable = !!network.wifi_available
                    if (!systemStatus || !systemStatus.networkOnline) {
                        if (onboardingWifiAvailable)
                            onboardingOpenNetwork()
                    }
                })
            }
        })
    }

    function onboardingContinueHome() {
        request("/onboarding/dismiss", "POST", "", function() {
            onboardingOpen = false
            onboardingNetworkSettings = false
            onboardingSetupCompleted = true
            space = "home"
            inputSurface.forceActiveFocus()
        }, "Could not save onboarding choice")
    }

    function onboardingOpenLocalSetup() {
        openBrowser("http://127.0.0.1/setup?local=1")
    }

    function onboardingOpenNetwork() {
        onboardingNetworkSettings = true
        openSettingsCategory("Network")
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
    readonly property real statusStripTop: selectedDomainY - 3 * homeCategoryPitch
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
    readonly property real expandedShellSideMargin: 20
    readonly property real expandedSurfaceChromeGap: design(8)
    readonly property real statusStripBottom: statusStripTop + systemStatusStrip.height
    readonly property real expandedHintRowTop: interactionRail.y + expandedHintRow.y
    readonly property real expandedShellTop: 20
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
    property int libraryHomeIndex: 0
    readonly property var libraryDimensions: [
        {label: "Platform", mode: "platform"},
        {label: "Provider", mode: "provider"},
        {label: "Game Mode", mode: "game_mode"},
        {label: "Genre", mode: "genre"}
    ]
    property var libraryCollections: [{"label": "Platform", "mode": "platform"}, {"label": "Provider", "mode": "provider"}, {"label": "Game Mode", "mode": "game_mode"}, {"label": "Genre", "mode": "genre"}]
    property var libraryCategoryMru: ["platform", "provider", "game_mode", "genre"]
    property string libraryDimension: "platform"
    property string space: "home"
    property string downloadsReturnSpace: "home"
    property var downloadsHomeRef: null
    property int systemCategoryIndex: 0
    property int systemHomeCardIndex: 0
    property string settingsPanelFocus: "categories"
    property var systemHomeRailRef: null
    property var settingsSpaceRef: null
    readonly property var systemHomeCards: ["Settings", "Utilities"]
    readonly property var settingsCategoryModel: MudosAssetCatalog.settingsCategories(systemCategories)
    property int systemRowIndex: 0
    property var systemCategories: ["System", "Display", "Audio", "Network", "Bluetooth", "Controllers", "Storage", "Utilities"]
    property var systemSettings: []
    property var utilities: []
    property var utilitiesHomeRef: null
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
    property string libraryTransitionState: "RESTING"
    property bool libraryTransitioning: false
    property bool storeTransitioning: false
    property string presentationTarget: "library"
    property real libraryTransitionProgress: 0
    property bool libraryTransitionExpanding: true
    property bool libraryHandoffPending: false
    property var pendingLibraryLaunch: null
    property real homeContentOpacity: 1
    property real libraryContentOpacity: 0
    property bool homeCategoryTransitioning: false
    property int homeCategoryFrom: 3
    property int homeCategoryTarget: 3
    property int homeCategoryDirection: 1
    property real homeCategoryProgress: 1
    property int homeCategoryHopDuration: 250
    readonly property real homeCategoryTravel: height + design(72)
    property real titleRailY: HomeDomains.titleRailY(
        selectedDomainY, selectedCategoryIndex, homeCategoryPitch)
    property bool suppressTitleRailCompletion: false
    readonly property real titleRailTargetY: HomeDomains.titleRailY(
        selectedDomainY,
        homeCategoryTransitioning ? homeCategoryTarget : selectedCategoryIndex,
        homeCategoryPitch)
    onSelectedDomainYChanged: {
        if (!homeCategoryTransitioning)
            titleRailY = titleRailTargetY
    }
    onHomeCategoryPitchChanged: {
        if (!homeCategoryTransitioning)
            titleRailY = titleRailTargetY
    }
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
    property var storeBookmarks: bookmarkStore ? bookmarkStore.bookmarks : []
    property var pluginStoreCards: pluginStoreCardsBridge ? pluginStoreCardsBridge.cards : []
    property bool browserVisible: false
    property bool browserSuspended: false
    property string browserLaunchId: ""
    property string browserLaunchName: ""
    property string browserLaunchUrl: ""
    property string browserTrustProfile: ""
    property string browserTrustOrigin: ""
    property string browserReturnSpace: "home"
    property string browserPriorInputMode: "gamepad"
    property bool browserInputModePending: false
    property bool browserTextInputPending: false
    property var browserTextInputField: ({})
    property string pendingStoreRemovalId: ""
    property bool storeOptionsOpen: false
    property var acquisitionJobs: ({})
    property var acquisitionCompletionSeen: ({})
    property var storeCategories: InstallableProjection.categories([])
    property var storeHomeRef: null
    property var storeHomeLandingRef: null
    property string storeError: ""
    property string message: ""
    property var credentialRequest: ({status: "idle"})
    property string credentialValue: ""
    property bool credentialSubmitInFlight: false
    property var credentialTarget: ({kind: "", plugin: "", name: ""})
    property bool credentialKeyboardShown: false
    property bool credentialKeyboardShowAttempted: false
    property int lastBrowserTextEntryShortcut: 0
    property string launchStatus: "idle"
    property string launchTitle: ""
    property string launchGameId: ""
    property string launchToken: ""
    // Development-only parity switch for the stationary landing-card specimen.
    property bool catalogueRefreshTimerDisabled: true
    property bool launchOverlayVisible: false
    property bool launchOverlayRetired: false
    property bool shellWasLeft: false
    property bool gamePresentationObserved: false
    property var launchLogLines: []
    property string normalizedLaunchStage: "preparing"
    property string normalizedLaunchStageLabel: "Preparing launch"
    property string normalizedLaunchDetail: ""
    property string normalizedLaunchProvider: ""
    property bool normalizedLaunchCancellable: false
    property bool launchCancellationRequested: false
    property bool gameOptionsOpen: false
    property string gameOptionsView: "menu"
    property int gameOptionsIndex: 0
    property string gameOptionsGameId: ""
    property var gameOptionsGame: null
    property var uninstallCapability: ({supported: false, installed: false})
    property string uninstallCapabilityKey: ""
    property int mappingSearchGeneration: 0
    property int artworkCandidateGeneration: 0
    property var artworkCandidates: []
    property var mappingCandidates: []
    property string mappingQuery: ""
    property string selectedArtworkRole: "icon_square"
    property string artworkError: ""
    property bool gameOptionsTextEntryActive: false
    property bool gameOptionsKeyboardShown: false
    property bool gameOptionsKeyboardWasVisible: false
    property var gameOptionsRef: null
    property int launchGeneration: 0
    property int launchStateSerial: 0
    property int launchStateApplied: 0
    property int launchStateRank: 0
    property var launchTracePrevious: ({})
    property var pendingHomeLaunch: null
    property string pendingHomeLaunchPhase: "idle"
    property string launchLifecycle: "shell"
    property string startupLifecycle: "BOOTSTRAPPING"
    property bool startupLibraryReady: false
    property bool startupCatalogueSnapshotLoaded: false
    property bool startupRuntimeObserved: false
    property bool startupControllerConnected: false
    property string startupSteamState: "unknown"
    readonly property bool startupSurfaceVisible: startupLifecycle === "BOOTSTRAPPING"
        || startupLifecycle === "RECONCILING_LIBRARY"
        || startupLifecycle === "READY_FOR_INTRO"
    function markStartupTiming(event) {
        if (typeof startupTimingBridge !== "undefined")
            startupTimingBridge.mark(event)
    }
    onStartupLibraryReadyChanged: if (startupLibraryReady) syncRecentDomain()
    property bool startupReadinessRequestInFlight: false
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
        || startupLifecycle !== "HOME"
        || presentationCoordinator.contentState !== presentationCoordinator.presentedState
    readonly property bool launchOverlayEffectiveVisible: launchOverlayVisible
        && !launchOverlayRetired
    readonly property bool launchScreenVisible: launchOverlayEffectiveVisible
        && presentationCoordinator.contentHidden
        && launchLifecycle !== "game" && launchLifecycle !== "returning"
        || (launchOverlayEffectiveVisible && launchStatus === "failed"
            && presentationCoordinator.contentPresented)

    Rectangle {
        id: startupSurface
        anchors.fill: parent
        z: 100000
        visible: root.startupSurfaceVisible
        color: luluPalette.backdrop

        Column {
            anchors.centerIn: parent
            width: Math.min(parent.width * 0.62, root.design(520))
            spacing: root.design(28)

            Text {
                text: "MUDOS"
                color: luluPalette.primaryText
                font.family: "JetBrainsMono Nerd Font"
                font.pixelSize: root.design(46)
                font.letterSpacing: root.design(8)
                font.weight: Font.DemiBold
                anchors.horizontalCenter: parent.horizontalCenter
            }
            Text {
                text: "Starting system..."
                color: luluPalette.secondaryText
                font.family: "JetBrainsMono Nerd Font"
                font.pixelSize: root.design(17)
                anchors.horizontalCenter: parent.horizontalCenter
            }
            Column {
                width: parent.width
                spacing: root.design(12)
                Repeater {
                    model: [
                        {label: "Core services", state: root.startupLibraryReady ? "ready" : "starting"},
                        {label: "Controller", state: !root.startupRuntimeObserved ? "checking"
                            : root.startupControllerConnected ? "ready" : "unavailable"},
                        {label: "Library", state: root.startupCatalogueSnapshotLoaded ? "ready" : "starting"},
                        {label: "Steam", state: root.startupSteamState}
                    ]
                    delegate: Row {
                        required property var modelData
                        width: parent.width
                        spacing: root.design(14)
                        Text {
                            width: root.design(22)
                            text: modelData.state === "ready" ? "✓"
                                : modelData.state === "unavailable" ? "—" : "•"
                            color: modelData.state === "ready" ? luluPalette.accent : luluPalette.mutedText
                            font.pixelSize: root.design(16)
                            horizontalAlignment: Text.AlignHCenter
                        }
                        Text {
                            width: parent.width - root.design(130)
                            text: modelData.label
                            color: luluPalette.primaryText
                            font.pixelSize: root.design(15)
                        }
                        Text {
                            width: root.design(90)
                            text: modelData.state === "ready" ? "Ready"
                                : modelData.state === "unavailable" ? "Unavailable"
                                : modelData.state === "starting" ? "Starting" : "Checking"
                            color: luluPalette.mutedText
                            font.pixelSize: root.design(13)
                            horizontalAlignment: Text.AlignRight
                        }
                    }
                }
            }
        }
    }

    PresentationCoordinator {
        id: presentationCoordinator
        titleCount: root.domains.length
    }

    Connections {
        target: presentationCoordinator
        function onReadyChanged() {
            root.tryBeginStartup()
        }
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
            if (root.startupLifecycle === "PLAYING_INTRO") {
                root.startupLifecycle = "HOME"
                root.markStartupTiming("home-available")
                root.traceLaunchEvent("STARTUP_INTRO_COMPLETE", {})
                root.refreshPlatformsCatalogue()
                root.refreshStore()
            }
            console.log("HOME_INPUT_UNLOCK_ATTEMPT", JSON.stringify({
                homeLaunchGated: root.homeLaunchGated,
                coordinatorState: presentationCoordinator.contentState,
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
    }

    // CatalogueModel receives Consoled's generation signal only after provider
    // reconciliation has committed its catalogue deltas. Refresh the QML array
    // projections at that point as well; the initial uninstall/job refresh may
    // have raced and read the pre-removal catalogue snapshot.
    Connections {
        target: catalogueModel
        function onGenerationChanged() {
            root.refreshCatalogue()
            root.refreshStore()
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
    readonly property var visibleLibraryGame: librarySpace ? librarySpace.selectedGame : null
    readonly property var selectedGameForOptions: {
        if (space === "library" && libraryFocus === "games")
            return visibleLibraryGame
        if (space === "home" && selectedCategoryIndex === 3)
            return visibleRecentGame
        return null
    }
    readonly property string libraryScope: "all"

    function request(path, method, body, callback, failureMessage, generation, failureCallback) {
        var request = new XMLHttpRequest()
        request.onreadystatechange = function() {
            if (request.readyState !== XMLHttpRequest.DONE)
                return
            if (request.status === 200 || request.status === 202)
                callback(JSON.parse(request.responseText))
            else if (failureMessage && (generation === undefined || generation === launchGeneration)) {
                message = failureMessage || "Catalogue unavailable"
                playAudioEvent("error")
                if (generation !== undefined) {
                    launchStatus = "failed"
                    launchStatusTimer.stop()
                }
                if (failureCallback)
                    failureCallback()
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
        if (done) done()
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
                storeCategories = InstallableProjection.categories([])
                storeError = "Installable titles unavailable"
                return
            }
            try {
                var rows = JSON.parse(request.responseText)
                var games = []
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
                }
                storeAvailableGames = games
                storeCategories = InstallableProjection.categories(games)
                storeError = ""
            } catch (error) {
                storeAvailableGames = []
                storeCategories = InstallableProjection.categories([])
                storeError = "Installable titles unavailable"
            }
        }
        // Installable is the combined entitled-but-uninstalled catalogue. Provider
        // filtering belongs to the catalogue boundary, not this presentation.
        request.open("GET", apiUrl + "/available")
        request.send()
    }

    function applyAcquisitionSnapshot(snapshot) {
        try {
            var parsed = typeof snapshot === "string" ? JSON.parse(snapshot) : snapshot
            var jobs = ({})
            var rows = parsed.jobs || []
            for (var index = 0; index < rows.length; index++) {
                var job = rows[index]
                if (String(job.content_identity || ""))
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
            launchLogTimer.stop()
            if (launchStatus === "failed" && state.last_failure_reason) {
                var failureDetail = String(state.last_failure_reason).replace(/\s+/g, " ").slice(0, 320)
                if (launchLogLines.indexOf("[Launch] " + failureDetail) < 0)
                    launchLogLines = launchLogLines.concat(["[Launch] " + failureDetail])
            }
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
        message = ""
        launchToken = ""
        launchGameId = ""
        launchLogLines = []
        shellWasLeft = false
        gamePresentationObserved = false
        launchGeneration++
        libraryTransitioning = false
        storeTransitioning = false
        libraryTransitionState = "RESTING"
        // A Library launch deliberately keeps the home layer faded out while
        // its surface exits. Restore that layer before the coordinator's
        // normal entrance so a failed launch returns to the actual home UI.
        homeContentOpacity = 1
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
        request("/launch-status", "GET", "", function(data) {
            var accepted = generation === launchGeneration && !launchOverlayRetired
                && (!data.game_id || data.game_id === launchGameId)
            traceLaunchResponse("/launch-status", data, generation, data.token || "", accepted, accepted ? "apply" : "ignored")
            if (generation !== launchGeneration || launchOverlayRetired || !accepted)
                return
            normalizedLaunchStage = data.stage || "preparing"
            normalizedLaunchStageLabel = data.stage_label || "Preparing launch"
            normalizedLaunchProvider = data.provider || ""
            normalizedLaunchDetail = data.detail || ""
            normalizedLaunchCancellable = data.cancellable === true && !launchCancellationRequested
            if (data.lines)
                launchLogLines = data.lines
        }, "", generation)
    }

    function refreshLibrary(done) {
        request("/?scope=" + libraryScope, "GET", "", function(data) {
            libraryGames = data
            syncGameOptionsGame()
            if (done)
                done()
        })
    }

    function requestStartupReadiness() {
        if (startupLibraryReady || startupReadinessRequestInFlight)
            return
        startupReadinessRequestInFlight = true
        request("/startup-ready", "GET", "", function(data) {
            startupReadinessRequestInFlight = false
            traceLaunchEvent("STARTUP_READINESS_RESPONSE", {ready: data && data.ready === true})
            if (!data || data.ready !== true) {
                startupReadinessTimer.start()
                return
            }
            startupLibraryReady = true
            startupLifecycle = "READY_FOR_INTRO"
            markStartupTiming("startup-readiness-achieved")
            traceLaunchEvent("LIBRARY_RECONCILE_READY", {})
            // This is a local cached catalogue projection; no optional
            // metadata or storefront request is part of the startup barrier.
            refreshLibrary(function() {
                startupCatalogueSnapshotLoaded = true
                traceLaunchEvent("STARTUP_LIBRARY_MODEL_READY", {count: libraryGames.length})
                root.tryBeginStartup()
            })
        }, "", undefined, function() {
            startupReadinessRequestInFlight = false
            startupReadinessTimer.start()
        })
    }

    function tryBeginStartup() {
        if (onboardingCompletionPending && startupLibraryReady && startupCatalogueSnapshotLoaded
                && startupLifecycle === "HOME")
            startupLifecycle = "READY_FOR_INTRO"
        traceLaunchEvent("STARTUP_TRY_INTRO", {
            libraryReady: startupLibraryReady && startupCatalogueSnapshotLoaded,
            lifecycle: startupLifecycle,
            coordinatorReady: presentationCoordinator.ready
        })
        if (!startupLibraryReady || !startupCatalogueSnapshotLoaded
                || startupLifecycle !== "READY_FOR_INTRO"
                || !presentationCoordinator.ready)
            return
        startupLifecycle = "PLAYING_INTRO"
        markStartupTiming("home-intro-started")
        onboardingCompletionPending = false
        traceLaunchEvent("STARTUP_INTRO_BEGIN", {})
        presentationCoordinator.beginStartup()
    }

    function refreshCataloguePair(group) {
        if (group === "store") {
            refreshStore()
        } else if (group === "recent-library") {
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
        var games = libraryGames.slice(0)
        if (visibleRecentGame)
            games.push(visibleRecentGame)
        for (var index = 0; index < games.length; index++) {
            if (String(games[index].game_id) === gameOptionsGameId) {
                gameOptionsGame = games[index]
                gameOptionsRef.mappingOverride = !!games[index].match_locked
                refreshGameOptionsCapability(games[index])
                return
            }
        }
    }

    function openSelectedGameOptions() {
        if (lutrisRecipeInstall.visible || lutrisAddGame.visible)
            return
        if (removeSelectedHomeStore()) {
            playAudioEvent(audioEventForAction("confirm"))
            return
        }
        if (space === "downloads" && downloadsHomeRef) {
            downloadsHomeRef.requestCancel()
            return
        }
        if (space === "store") {
            beginLutrisSearch()
            return
        }
        if (gameOptionsOpen)
            return
        if (selectedGameForOptions) {
            playAudioEvent(audioEventForAction("options"))
            openGameOptions(selectedGameForOptions)
        }
    }

    function openGameOptions(game) {
        if (!game)
            return
        gameOptionsGame = game
        gameOptionsRef.mappingOverride = !!game.match_locked
        gameOptionsGameId = String(game.game_id)
        gameOptionsView = "menu"
        gameOptionsIndex = 0
        uninstallCapability = ({supported: false, installed: false})
        uninstallCapabilityKey = ""
        artworkError = ""
        mappingCandidates = []
        artworkCandidates = []
        gameOptionsOpen = true
        refreshGameOptionsCapability(game)
    }

    function refreshGameOptionsCapability(game) {
        if (!game || !gameOptionsOpen)
            return
        var key = [game.game_id, game.provider, game.provider_id, game.install_state,
                   game.installed_game_id || ""].join("|")
        if (key === uninstallCapabilityKey)
            return
        uninstallCapabilityKey = key
        var gameId = String(game.game_id)
        request("/uninstall/capability/" + encodeURIComponent(gameId), "GET", "", function(data) {
            if (gameOptionsOpen && gameOptionsGameId === gameId
                    && uninstallCapabilityKey === key) {
                uninstallCapability = data || ({supported: false, installed: false})
            }
        }, "Uninstall capability unavailable")
    }

    function closeGameOptions() {
        if (gameOptionsTextEntryActive)
            finishGameOptionsTextEntry(true)
        gameOptionsOpen = false
        gameOptionsGame = null
        gameOptionsGameId = ""
        uninstallCapability = ({supported: false, installed: false})
        uninstallCapabilityKey = ""
        mappingSearchGeneration++
        artworkCandidateGeneration++
        artworkError = ""
    }

    function loadGameArtworkCandidates(role) {
        selectedArtworkRole = role
        artworkCandidates = []
        var generation = ++artworkCandidateGeneration
        var gameId = gameOptionsGameId
        request("/artwork/candidates?game_id=" + encodeURIComponent(gameOptionsGameId)
                + "&role=" + encodeURIComponent(role), "GET", "", function(data) {
            if (!gameOptionsOpen || gameId !== gameOptionsGameId
                    || role !== selectedArtworkRole || generation !== artworkCandidateGeneration)
                return
            gameOptionsRef.selectedCandidateId = ""
            artworkCandidates = data || []
            gameOptionsIndex = 0
            if (gameOptionsRef)
                gameOptionsRef.ensureCandidateVisible()
            if (!artworkCandidates.length)
                artworkError = "No integrated candidates are available for this artwork type"
        }, "Artwork candidates unavailable")
    }

    function searchGameMapping(query) {
        mappingQuery = String(query || "")
        mappingCandidates = []
        if (!mappingQuery.trim()) {
            artworkError = "Enter a game title to search"
            return
        }
        var generation = ++mappingSearchGeneration
        var gameId = gameOptionsGameId
        request("/metadata/search?game_id=" + encodeURIComponent(gameOptionsGameId)
                + "&query=" + encodeURIComponent(mappingQuery), "GET", "", function(data) {
            if (!gameOptionsOpen || gameId !== gameOptionsGameId
                    || generation !== mappingSearchGeneration)
                return
            gameOptionsRef.selectedCandidateId = ""
            mappingCandidates = data || []
            gameOptionsIndex = mappingCandidates.length ? 2 : 0
            if (gameOptionsRef)
                gameOptionsRef.ensureCandidateVisible()
            artworkError = mappingCandidates.length ? "" : "No matching games found"
        }, "Metadata search unavailable")
    }

    function showGameOptionsKeyboard() {
        gameOptionsTextEntryActive = true
        gameOptionsKeyboardShown = false
        gameOptionsKeyboardWasVisible = false
        request("/keyboard/show", "POST", "", function(data) {
            gameOptionsKeyboardShown = data && data.visible === true
            if (!gameOptionsKeyboardShown) {
                gameOptionsTextEntryActive = false
                artworkError = "On-screen keyboard is unavailable"
            }
        }, "On-screen keyboard unavailable")
    }

    function finishGameOptionsTextEntry(cancelled) {
        var hideKeyboard = gameOptionsKeyboardShown
        gameOptionsTextEntryActive = false
        gameOptionsKeyboardShown = false
        gameOptionsKeyboardWasVisible = false
        if (gameOptionsRef) {
            if (cancelled)
                gameOptionsRef.cancelTextEntry()
            else
                gameOptionsRef.textEditing = false
        }
        if (!cancelled && gameOptionsView === "title" && gameOptionsRef) {
            if (!gameOptionsRef.titleDraft.trim()) {
                artworkError = "Enter a title"
            } else {
                request("/metadata/title/" + encodeURIComponent(gameOptionsGameId), "POST",
                        JSON.stringify({title: gameOptionsRef.titleDraft}), function() {
                    gameOptionsView = "menu"
                    gameOptionsIndex = 0
                    refreshCatalogue()
                }, "Title update failed")
            }
        }
        if (hideKeyboard)
            request("/keyboard/hide", "POST", "", function() {})
    }

    function selectGameMapping(candidate) {
        if (!candidate || !candidate.id)
            return
        request("/metadata/match/" + encodeURIComponent(gameOptionsGameId), "POST",
                JSON.stringify({provider: String(candidate.provider || "igdb"),
                    metadata_game_id: String(candidate.id), canonical_title: String(candidate.title || "")}),
                function() {
                    mappingSearchGeneration++
                    artworkCandidateGeneration++
                    mappingCandidates = []
                    artworkCandidates = []
                    refreshLibrary(function() {
                        refreshPlatformsCatalogue()
                        gameOptionsView = "menu"
                        gameOptionsIndex = 0
                        artworkError = ""
                        syncGameOptionsGame()
                    })
                }, "Mapping update failed")
    }

    function artworkMutation(path, body, callback) {
        request(path, "POST", JSON.stringify(body || {}), function(data) {
            refreshCatalogue()
            if (callback)
                callback(data)
        }, "Artwork update failed")
    }

    function activateGameOptions() {
        if (!gameOptionsGame)
            return
        if (gameOptionsView === "menu") {
            var menuChoice = gameOptionsRef.menuEntries[gameOptionsIndex]
            if (menuChoice === "Change Mapping") {
                gameOptionsView = "mapping"
                mappingQuery = String(gameOptionsGame.canonical_title || gameOptionsGame.title || "")
                mappingCandidates = []
                artworkError = ""
                gameOptionsIndex = 0
            } else if (menuChoice === "Revert Mapping") {
                request("/metadata/match/revert/" + encodeURIComponent(gameOptionsGameId), "POST", "{}", function() {
                    refreshCatalogue()
                    refreshLibrary(function() {
                        refreshPlatformsCatalogue()
                        gameOptionsView = "menu"
                        gameOptionsIndex = 0
                        syncGameOptionsGame()
                    })
                }, "Mapping revert failed")
            } else if (menuChoice === "Change Artwork") {
                gameOptionsView = "artworkRole"
                artworkError = ""
                gameOptionsIndex = 0
            } else if (menuChoice === "Change Title") {
                gameOptionsView = "title"
                gameOptionsRef.titleDraft = String(gameOptionsGame.display_title_override
                    || gameOptionsGame.canonical_title || gameOptionsGame.title || "")
                gameOptionsRef.titleOverride = !!gameOptionsGame.display_title_override
                artworkError = ""
                gameOptionsIndex = 0
            } else if (menuChoice === "Uninstall" && uninstallCapability.supported) {
                gameOptionsView = "confirm"
                gameOptionsIndex = 0
            }
        } else if (gameOptionsView === "confirm") {
            if (gameOptionsIndex === 0) {
                request("/uninstall/" + encodeURIComponent(gameOptionsGameId), "POST", "", function(data) {
                    closeGameOptions()
                    refreshCatalogue()
                }, "Uninstall failed")
            } else {
                gameOptionsView = "menu"
                gameOptionsIndex = 0
            }
        } else if (gameOptionsView === "mapping") {
            if (gameOptionsIndex === 0) {
                gameOptionsRef.beginTextEntry("mapping")
            } else if (gameOptionsIndex === 1) {
                searchGameMapping(mappingQuery)
            } else {
                selectGameMapping(gameOptionsRef.selectedCandidate())
            }
        } else if (gameOptionsView === "artworkRole") {
            var roles = ["cover", "icon_square", "preview_still"]
            loadGameArtworkCandidates(roles[gameOptionsIndex] || "cover")
            gameOptionsView = "artwork"
        } else if (gameOptionsView === "artwork") {
            if (!artworkCandidates.length || !artworkCandidates[gameOptionsIndex])
                return
            var artwork = gameOptionsRef.selectedCandidate()
            artworkMutation("/artwork/" + encodeURIComponent(gameOptionsGameId), {
                role: selectedArtworkRole, source_url: artwork.url
            }, function() {
                gameOptionsView = "menu"
                gameOptionsIndex = 0
            })
        } else if (gameOptionsView === "title") {
            if (gameOptionsIndex === 0) {
                gameOptionsRef.beginTextEntry("title")
            } else if (gameOptionsIndex === 1) {
                if (gameOptionsRef.titleDraft.trim()) {
                    request("/metadata/title/" + encodeURIComponent(gameOptionsGameId), "POST",
                            JSON.stringify({title: gameOptionsRef.titleDraft}), function() {
                        gameOptionsView = "menu"
                        gameOptionsIndex = 0
                        refreshCatalogue()
                    }, "Title update failed")
                }
            } else if (gameOptionsIndex === 2 && gameOptionsRef.titleOverride) {
                request("/metadata/title/clear/" + encodeURIComponent(gameOptionsGameId),
                        "POST", "{}", function() {
                    gameOptionsView = "menu"
                    gameOptionsIndex = 0
                    refreshCatalogue()
                }, "Title reset failed")
            } else {
                gameOptionsRef.cancelTextEntry()
                gameOptionsView = "menu"
                gameOptionsIndex = 0
                artworkError = ""
            }
        }
    }

    function moveGameOptions(delta) {
        var count = gameOptionsView === "menu" ? (gameOptionsRef ? gameOptionsRef.menuEntries.length : 0)
            : gameOptionsView === "mapping" ? 2 + mappingCandidates.length
            : gameOptionsView === "artworkRole" ? 2
            : gameOptionsView === "artwork" ? artworkCandidates.length
            : gameOptionsView === "title" ? 1 + (gameOptionsRef ? gameOptionsRef.titleActionCount : 0)
            : gameOptionsView === "confirm" ? 2 : 0
        if (count > 0) {
            gameOptionsIndex = Math.max(0, Math.min(count - 1, gameOptionsIndex + delta))
            if (gameOptionsRef)
                gameOptionsRef.ensureCandidateVisible()
        }
    }

    function refreshSystemSettings() {
        if (systemCategories[systemCategoryIndex] === "System") {
            refreshMudosMenu()
            return
        }
        if (systemCategories[systemCategoryIndex] === "Utilities") {
            refreshUtilities()
            return
        }
        var selectedKey = systemSettings[systemRowIndex] ? systemSettings[systemRowIndex].key : ""
        request("/settings?category=" + encodeURIComponent(systemCategories[systemCategoryIndex]),
                "GET", "", function(data) {
                    systemSettings = data
                    var stableIndex = -1
                    for (var index = 0; index < data.length; index++)
                        if (data[index].key === selectedKey) { stableIndex = index; break }
                    systemRowIndex = stableIndex >= 0 ? stableIndex
                        : Math.min(systemRowIndex, Math.max(0, data.length - 1))
                })
    }

    function refreshUtilities() {
        request("/utilities", "GET", "", function(data) {
            utilities = Array.isArray(data) ? data : []
            if (utilitiesHomeRef) {
                utilitiesHomeRef.applications = utilities
                utilitiesHomeRef.statusMessage = ""
            }
        }, "Utilities are unavailable", undefined, function() {
            utilities = []
            if (utilitiesHomeRef)
                utilitiesHomeRef.statusMessage = "Flatpak application inventory is unavailable."
        })
    }

    function launchUtility(applicationRef) {
        message = "Launching application…"
        request("/utilities/launch", "POST", JSON.stringify({ref: applicationRef}), function() {
            message = ""
        }, "Application could not be launched", undefined, function() { message = "" })
    }

    function activateBluetoothSetting(key) {
        if (key.indexOf("bluetooth:") !== 0) return
        var parts = key.split(":")
        var action = parts[1]
        var devicePath = parts.length > 2 ? parts.slice(2).join(":") : ""
        if (action === "pairing-accept")
            devicePath = systemSpace.bluetoothInputValue
        root.message = action === "discover" ? "Starting Bluetooth discovery…"
            : action === "pair" ? "Pairing Bluetooth device…" : "Updating Bluetooth…"
        request("/bluetooth/action", "POST", JSON.stringify({action: action, path: devicePath}), function() {
            root.message = "Bluetooth updated"
            if (action === "pairing-accept") systemSpace.bluetoothInputValue = ""
            root.refreshSystemSettings()
        }, "Bluetooth action failed", undefined, function() { root.refreshSystemSettings() })
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
        running: root.space === "system"
            && root.systemCategories[root.systemCategoryIndex] === "Network"
        onTriggered: root.refreshNetworkState()
    }

    Timer {
        id: audioRefreshTimer
        interval: 1000
        repeat: true
        running: root.space === "system"
            && root.systemCategories[root.systemCategoryIndex] === "Audio"
        onTriggered: root.refreshAudioState()
    }

    Timer {
        interval: 1200
        repeat: true
        running: root.space === "system"
            && root.systemCategories[root.systemCategoryIndex] === "Bluetooth"
        onTriggered: root.refreshSystemSettings()
    }

    Timer {
        id: credentialTimer
        interval: 1000
        repeat: true
        // Acquisitiond may create a request without a preceding shell request.
        // Poll while active so SteamCMD password/Guard prompts are discovered.
        running: true
        onTriggered: root.request("/credential", "GET", "", function(data) {
            root.credentialRequest = data
        })
    }

    Timer {
        id: browserTextEntryShortcutTimer
        interval: 100
        repeat: true
        running: root.browserVisible
        onTriggered: {
            var serial = Number(controllerBridge.textEntryShortcutSerial || 0)
            if (serial === root.lastBrowserTextEntryShortcut)
                return
            root.lastBrowserTextEntryShortcut = serial
            browserSurface.requestTextEntryForFocusedElement()
        }
    }

    Timer {
        id: credentialFocusTimer
        interval: 300
        repeat: true
        running: root.credentialRequest.status === "requested" || root.credentialRequest.status === "waiting"
        onTriggered: {
            if (root.credentialRequest.input_type === "waiting") {
                if (root.credentialKeyboardShown) {
                    root.request("/keyboard/hide", "POST", "", function() {
                        root.credentialKeyboardShown = false
                    })
                }
                return
            }
            if (root.credentialRequest.multiline)
                credentialTextArea.forceActiveFocus()
            else
                credentialInput.forceActiveFocus()
            if (!root.credentialKeyboardShown && !root.credentialKeyboardShowAttempted) {
                root.credentialKeyboardShowAttempted = true
                root.request("/keyboard/show", "POST", "", function() {
                    root.credentialKeyboardShown = true
                }, "Keyboard unavailable", undefined, function() {
                    root.credentialKeyboardShowAttempted = false
                    root.message = "Credential input unavailable"
                    if (root.credentialRequest.status === "requested"
                            || root.credentialRequest.status === "waiting") {
                        root.request("/credential/cancel", "POST",
                                     JSON.stringify({id: root.credentialRequest.id}),
                                     function(data) { root.credentialRequest = data })
                    }
                })
            }
        }
    }

    Timer {
        id: gameOptionsKeyboardTimer
        interval: 300
        repeat: true
        running: root.gameOptionsOpen && root.gameOptionsTextEntryActive
            && root.gameOptionsKeyboardShown
        onTriggered: root.request("/keyboard/status", "GET", "", function(data) {
            var visible = data && data.visible === true
            if (root.gameOptionsKeyboardWasVisible && !visible) {
                root.gameOptionsKeyboardShown = false
                root.gameOptionsTextEntryActive = false
                if (root.gameOptionsRef)
                    root.gameOptionsRef.keyboardDismissed()
            }
            root.gameOptionsKeyboardWasVisible = visible
        })
    }

    Rectangle {
        anchors.fill: parent
        visible: root.credentialRequest.status === "requested" || root.credentialRequest.status === "waiting"
        z: 1000
        color: root.credentialRequest.presentation === "attached"
            ? luluPalette.transparent : luluPalette.backdrop
        Text {
            anchors.centerIn: parent
            anchors.verticalCenterOffset: -150
            visible: root.credentialRequest.presentation === "prompted"
                || root.credentialTarget.kind !== "browser"
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
            visible: root.credentialRequest.input_type !== "waiting"
                && (!root.credentialRequest.multiline
                    || root.credentialRequest.presentation === "attached")
            opacity: root.credentialRequest.presentation === "attached"
                && root.credentialTarget.kind === "browser" ? 0 : 1
            text: root.credentialValue
            color: luluPalette.primaryText
            font.pixelSize: 28
            horizontalAlignment: TextInput.AlignHCenter
            onTextChanged: root.credentialValue = text
            onAccepted: root.submitCredential(true)
            Keys.onPressed: function(event) {
                if ((event.key === Qt.Key_Return || event.key === Qt.Key_Enter)
                        && !root.credentialRequest.multiline) {
                    event.accepted = true
                    root.submitCredential(true)
                } else if (event.key === Qt.Key_Escape) {
                    event.accepted = true
                    root.back()
                }
            }
        }
        TextArea {
            id: credentialTextArea
            anchors.centerIn: parent
            width: 700
            height: 180
            focus: parent.visible && !!root.credentialRequest.multiline
            visible: root.credentialRequest.input_type !== "waiting"
                && !!root.credentialRequest.multiline
            opacity: root.credentialRequest.presentation === "attached"
                && root.credentialTarget.kind === "browser" ? 0 : 1
            text: root.credentialValue
            Keys.onPressed: function(event) {
                if (event.key === Qt.Key_Escape) {
                    event.accepted = true
                    root.back()
                }
            }
            color: luluPalette.primaryText
            font.pixelSize: 28
            wrapMode: TextArea.Wrap
            onTextChanged: root.credentialValue = text
        }
        Text {
            anchors.centerIn: parent
            anchors.verticalCenterOffset: 100
            visible: root.credentialRequest.presentation !== "attached"
            text: root.credentialRequest.input_type === "waiting"
                ? "A: I Approved   X: Enter Code   B: Cancel"
                : (root.credentialRequest.status === "waiting"
                    ? "Waiting…  A: continue   B: cancel" : "A: submit   B: cancel")
            color: luluPalette.secondaryText
            font.pixelSize: 20
        }
    }

    Timer {
        id: storageRefreshTimer
        interval: 2000
        repeat: true
        running: root.space === "system"
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
        moveLibraryVertical(delta)
    }

    function moveLibraryLanding(delta) {
        libraryHomeLanding.moveSelection(delta)
        libraryHomeIndex = libraryHomeLanding.selectedIndex
    }

    function libraryDimensionLabel(mode) {
        for (var i = 0; i < libraryDimensions.length; ++i)
            if (libraryDimensions[i].mode === mode) return libraryDimensions[i].label
        return "Platform"
    }

    function setLibraryDimension(mode) {
        var valid = false
        for (var i = 0; i < libraryDimensions.length; ++i)
            if (libraryDimensions[i].mode === mode) valid = true
        if (!valid) return
        libraryDimension = mode
        libraryHomeIndex = 0
        var order = libraryCategoryMru.filter(function(item) { return item !== mode })
        order.unshift(mode)
        libraryCategoryMru = order
        libraryCollections = order.map(function(item) {
            return {label: libraryDimensionLabel(item), mode: item}
        })
    }

    function commitLibraryCategory(index) {
        var selected = libraryCollections[index]
        if (!selected) return
        setLibraryDimension(String(selected.mode))
    }

    function moveLibraryVertical(delta) {
        if (librarySpace) librarySpace.moveGame(delta)
    }

    function moveLibraryCategory(delta) {
        if (librarySpace) librarySpace.moveCategory(delta)
    }

    function adjacentLibraryDimension(delta) {
        var index = -1
        for (var i = 0; i < libraryDimensions.length; ++i)
            if (libraryDimensions[i].mode === libraryDimension) index = i
        if (index < 0 || !libraryDimensions.length) return "platform"
        var next = (index + delta + libraryDimensions.length) % libraryDimensions.length
        return libraryDimensions[next].mode
    }

    function moveLibraryCollection(delta) {
        setLibraryDimension(adjacentLibraryDimension(delta))
    }

    function moveStoreCategory(delta) {
        if (storeHomeRef)
            storeHomeRef.moveCategory(delta)
    }

    function moveStoreGame(delta) {
        if (space === "home" && storeHomeLandingRef)
            storeHomeLandingRef.moveHome(delta)
        else if (storeHomeRef)
            storeHomeRef.moveGame(delta)
    }

    function moveStoreGameVertical(delta) {
        if (space === "home")
            return
        if (storeHomeRef)
            storeHomeRef.moveVertical(delta)
    }

    function moveDownloads(delta) {
        if (downloadsHomeRef)
            downloadsHomeRef.moveSelection(delta)
    }

    function openDownloads(returnSpace) {
        if (credentialTarget.kind === "browser")
            cancelBrowserTextInput()
        if (browserVisible) {
            browserVisible = false
            browserSuspended = true
            request("/browser-surface/active", "POST", JSON.stringify({active: false}), function() {})
            request("/input-mode/" + encodeURIComponent(browserPriorInputMode), "POST", "", function() {})
        }
        downloadsReturnSpace = returnSpace === "downloads" ? "home" : returnSpace
        space = "downloads"
        message = ""
    }

    function openDownloadsGlobal() {
        if (lutrisRecipeInstall.visible || lutrisAddGame.visible)
            return
        if (space !== "downloads")
            openDownloads(space)
    }

    function openBrowser(url, trustProfile, trustOrigin) {
        browserSuspended = false
        browserVisible = false
        browserLaunchUrl = url
        browserTrustProfile = trustProfile || ""
        browserTrustOrigin = trustOrigin || ""
        browserInputModePending = true
        request("/state", "GET", "", function(state) {
            browserPriorInputMode = String(state.input_mode || "gamepad")
            request("/browser-surface/active", "POST", JSON.stringify({active: true}), function() {
                request("/input-mode/compat", "POST", "", function() {
                    browserInputModePending = false
                    browserVisible = true
                    browserSurface.trustedProfile = browserTrustProfile
                    browserSurface.trustedOrigin = browserTrustOrigin
                    browserSurface.open(url)
                }, "Browser compatibility mode unavailable", undefined, function() {
                    request("/browser-surface/active", "POST", JSON.stringify({active: false}), function() {})
                    request("/input-mode/" + encodeURIComponent(browserPriorInputMode), "POST", "", function() {})
                    browserInputModePending = false
                })
            }, "Browser session unavailable", undefined, function() {
                browserInputModePending = false
            })
        }, "Browser session state unavailable", undefined, function() {
            browserInputModePending = false
        })
    }

    function launchHomeStore(id, displayName, url) {
        browserLaunchId = id
        browserLaunchName = displayName
        browserLaunchUrl = url
        browserReturnSpace = "home"
        openBrowser(url)
    }

    function closeBrowser() {
        if (credentialTarget.kind === "browser")
            cancelBrowserTextInput()
        browserVisible = false
        browserSuspended = false
        browserSurface.releasePage()
        browserTrustProfile = ""
        browserTrustOrigin = ""
        request("/browser-surface/active", "POST", JSON.stringify({active: false}), function() {})
        request("/input-mode/" + encodeURIComponent(browserPriorInputMode), "POST", "", function() {})
    }

    function trustedWebCredentialRequest(details) {
        if (!browserVisible || browserTrustProfile === ""
                || details.profile !== browserTrustProfile
                || details.origin !== browserTrustOrigin)
            return
        request("/web-credentials/get", "POST", JSON.stringify({
            profile: browserTrustProfile, origin: browserTrustOrigin
        }), function(data) {
            if (data.configured && data.username !== undefined && data.password !== undefined)
                browserSurface.applyTrustedCredentials(data.username, data.password)
        }, "Trusted web credential lookup unavailable")
    }

    function trustedWebCredentialCaptured(details) {
        if (!browserVisible || browserTrustProfile === ""
                || details.profile !== browserTrustProfile
                || details.origin !== browserTrustOrigin
                || !details.candidate || !details.candidate.username
                || !details.candidate.password)
            return
        request("/web-credentials/save", "POST", JSON.stringify({
            profile: browserTrustProfile, origin: browserTrustOrigin,
            username: details.candidate.username, password: details.candidate.password
        }), function() { browserSurface.clearTrustedCredentialCandidate() },
        "Trusted web credential save unavailable")
    }

    function cancelBrowserTextInput() {
        credentialSubmitInFlight = false
        if (credentialRequest.status === "requested" || credentialRequest.status === "waiting") {
            root.request("/credential/cancel", "POST", JSON.stringify({id: credentialRequest.id}), function(data) {
                credentialRequest = data
                root.request("/keyboard/hide", "POST", "", function() {
                    credentialKeyboardShown = false
                    credentialKeyboardShowAttempted = false
                    browserTextInputPending = false
                    browserTextInputField = ({})
                    browserSurface.clearEditableState()
                })
            })
        } else {
            browserTextInputPending = false
            browserTextInputField = ({})
            browserSurface.clearEditableState()
        }
    }

    function beginBrowserTextInput(field) {
        if (!browserVisible || browserTextInputPending
                || credentialRequest.status === "requested"
                || credentialRequest.status === "waiting")
            return
        browserTextInputPending = true
        browserTextInputField = field
        browserSurface.lockEditable()
        credentialTarget = ({kind: "browser"})
        credentialValue = field.secret ? "" : String(field.value || "")
        credentialKeyboardShown = false
        credentialKeyboardShowAttempted = false
        request("/credential/begin", "POST", JSON.stringify({
            title: "Web Page Input", prompt: field.secret ? "Password" : "Text",
            input_type: field.secret ? "secret" : "text", secret: !!field.secret,
            max_length: 16384, presentation: "attached", multiline: field.type === "textarea"
                || field.type === "contenteditable"
        }), function(data) { credentialRequest = data }, "Browser text input unavailable",
        root.launchGeneration, function() {
            browserSurface.clearEditableState()
            browserTextInputPending = false
            browserTextInputField = ({})
        })
    }

    function submitCredential(submitWithEnter, waitingChoice) {
        if (credentialRequest.status !== "requested" && credentialRequest.status !== "waiting")
            return
        if (credentialSubmitInFlight)
            return
        credentialSubmitInFlight = true
        root.lastCredentialValue = credentialRequest.input_type === "waiting"
            ? (waitingChoice || "approved") : credentialValue
        var target = credentialTarget
        root.request("/credential/submit", "POST", JSON.stringify({id: credentialRequest.id, value: root.lastCredentialValue}),
            function(data) {
                credentialValue = ""
                credentialRequest = data
                if (target.kind === "browser") {
                    var value = root.lastCredentialValue
                    root.request("/keyboard/hide", "POST", "", function() {
                        credentialKeyboardShown = false
                        credentialKeyboardShowAttempted = false
                        browserSurface.commitText(value, submitWithEnter, function() {
                            browserTextInputPending = false
                            browserTextInputField = ({})
                            root.lastCredentialValue = ""
                            credentialSubmitInFlight = false
                        })
                    })
                } else {
                    root.completeCredentialTarget(target, root.lastCredentialValue)
                    root.lastCredentialValue = ""
                    root.request("/keyboard/hide", "POST", "", function() {
                        credentialKeyboardShown = false
                        credentialKeyboardShowAttempted = false
                        credentialSubmitInFlight = false
                    })
                }
            }, function() {
                credentialSubmitInFlight = false
                root.lastCredentialValue = ""
                root.message = "Credential rejected"
            })
    }

    function resumeBrowserSession() {
        request("/input-mode/compat", "POST", "", function() {
            request("/browser-surface/active", "POST", JSON.stringify({active: true}), function() {
                browserSuspended = false
                browserVisible = true
                browserSurface.forceActiveFocus()
            })
        })
    }

    Timer {
        interval: 300
        repeat: true
        running: root.browserVisible && !root.browserInputModePending
        onTriggered: root.request("/state", "GET", "", function(state) {
            if (root.browserVisible && state.delegated_surface !== "browser")
                root.closeBrowser()
        })
    }

    function controllerOptions() {
        openSelectedGameOptions()
    }

    function removeSelectedHomeStore() {
        if (space !== "home" || selectedCategoryIndex !== 1 || !storeHomeLandingRef)
            return false
        var card = storeHomeLandingRef.homeCards()[storeHomeLandingRef.homeSelectedIndex]
        if (!card || card.kind !== "store" || card.removable === false)
            return false
        if (pendingStoreRemovalId !== card.id) {
            pendingStoreRemovalId = card.id
            message = "Press X again to remove " + card.title
            return true
        }
        bookmarkStore.removeBookmark(card.id)
        pendingStoreRemovalId = ""
        message = "Store removed"
        return true
    }

    function pauseAcquisition(jobId) {
        request("/acquisition/pause/" + encodeURIComponent(jobId), "POST", "", function() {}, "Pause failed")
    }

    function resumeAcquisition(jobId) {
        request("/acquisition/resume/" + encodeURIComponent(jobId), "POST", "", function() {}, "Resume failed")
    }

    function cancelAcquisition(jobId) {
        request("/acquisition/cancel/" + encodeURIComponent(jobId), "POST", "", function() {}, "Cancel failed")
    }

    function clearAcquisition(jobId) {
        request("/acquisition/clear/" + encodeURIComponent(jobId), "POST", "", function() {
            root.refreshAcquisitionJobs()
        }, "Clear failed")
    }

    function launchGame(game, choreographyComplete) {
        if (!game)
            return
        if (choreographyComplete !== true && presentationCoordinator.contentPresented) {
            pendingHomeLaunch = game
            pendingHomeLaunchPhase = "exiting"
            if (!presentationCoordinator.beginContentExit()) {
                pendingHomeLaunch = null
                pendingHomeLaunchPhase = "idle"
            }
            return
        }
        var generation = ++launchGeneration
        launchLifecycle = "launch_requested"
        returnPreparationStarted = false
        returnAlreadyHandled = false
        traceLaunchEvent("LAUNCH_REQUESTED", {game_id: String(game.game_id), title: game.title})
        launchTitle = game.title
        launchGameId = String(game.game_id)
        launchToken = ""
        focusRecentForReturn()
        launchOverlayVisible = true
        traceLaunchEvent("OVERLAY_SHOWN", {game_id: launchGameId})
        launchOverlayRetired = false
        shellWasLeft = false
        gamePresentationObserved = false
        launchLogLines = ["[Lulu] Play requested: " + game.title + " / " + game.game_id]
        launchLogTimer.start()
        launchStatus = "launching"
        normalizedLaunchStage = "preparing"
        normalizedLaunchStageLabel = "Preparing launch"
        normalizedLaunchProvider = String(game.provider || "")
        normalizedLaunchDetail = ""
        normalizedLaunchCancellable = false
        launchCancellationRequested = false
        launchStateRank = 1
        message = "Launching " + game.title
        launchStatusTimer.start()
        launchLogTimer.start()
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
            launchOverlayRetired = false
            launchOverlayVisible = true
            normalizedLaunchStage = "failed"
            normalizedLaunchStageLabel = "Launch failed"
            normalizedLaunchCancellable = false
            launchStatusTimer.stop()
            launchLogTimer.stop()
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
        normalizedLaunchStage = "preparing"
        normalizedLaunchStageLabel = "Preparing provider"
        normalizedLaunchProvider = String(provider.id || "")
        launchCancellationRequested = false
        launchStateRank = 1
        message = "Launching " + launchTitle
        launchStatusTimer.start()
        launchLogTimer.start()
        request("/mudos/provider", "POST", JSON.stringify({id: provider.id}), function(data) {
            if (generation !== launchGeneration) return
            launchToken = data.token
            refreshLaunchState(generation)
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
        launchGame(game, true)
        startReturnWatch()
    }

    function installGame(game) {
        if (!game || launchOverlayEffectiveVisible)
            return
        console.log("INSTALLABLE_INSTALL_DISPATCH", "game", String(game.game_id),
                    "provider", String(game.provider), "provider_id", String(game.provider_id),
                    "install_state", String(game.install_state),
                    "availability_state", String(game.availability_state))
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

    // Legacy retry action remains service-owned for failed-job recovery:
    // root.retryAcquisition(jobId) -> /acquisition/retry/<job_id>.

    function openSteamStore() {
        // The former delegated path used launchTitle = "Steam Store" and
        // launchToken = data.token; this browser path intentionally does not.
        openBrowser("https://store.steampowered.com/")
    }

    function cancelLaunch() {
        if (!launchOverlayEffectiveVisible)
            return
        launchCancellationRequested = true
        normalizedLaunchStage = "cancelling"
        normalizedLaunchStageLabel = "Cancelling launch…"
        normalizedLaunchCancellable = false
        request("/cancel", "POST", "", function(data) {
            launchStatusTimer.stop()
            normalizedLaunchStage = "cancelled"
            normalizedLaunchStageLabel = "Launch cancelled"
            launchOverlayRetired = true
            launchOverlayVisible = false
            launchLifecycle = "shell"
            returnPresentationPending = true
            returnPreparationStarted = false
            presentationCoordinator.beginStartup()
            message = ""
        }, "Launch cancellation failed", launchGeneration)
    }

    function dismissLaunchFailure() {
        launchOverlayRetired = true
        launchOverlayVisible = false
        launchStatus = "idle"
        message = ""
        launchToken = ""
        launchGameId = ""
        launchLogLines = []
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
            // Migrate the useful read-only facts from the retired System
            // category into the surviving System destination. Operational
            // controls remain owned by the Mudos menu rows above.
            root.systemSettings = rows
            root.systemRowIndex = Math.min(root.systemRowIndex, Math.max(0, rows.length - 1))
            root.request("/settings?category=System", "GET", "", function(settings) {
                for (var j = 0; j < settings.length; j++) {
                    if (settings[j].key === "lulu.reset") continue
                    rows.push({key: "mudos.setting:" + settings[j].key,
                               label: settings[j].label, kind: "status",
                               value: settings[j].value, description: settings[j].detail,
                               writable: false})
                }
                root.systemSettings = rows
                root.systemRowIndex = Math.min(root.systemRowIndex, Math.max(0, rows.length - 1))
            }, "System information unavailable")
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

    function completeCredentialTarget(target, value) {
        if (target.kind === "lutris-search")
            lutrisRecipeInstall.openForQuery(value)
        else if (target.kind === "romm-pair")
            root.request("/plugins/romm/pair", "POST", JSON.stringify({code: value}), function(result) {
                root.message = "RomM paired"
                root.refreshSystemSettings()
            }, "RomM pairing failed: check that the code is new and unexpired")
        else if (target.kind === "secret")
            root.request("/plugins/" + target.plugin + "/secret/" + target.name,
                "POST", JSON.stringify({value: value}), function(result) {
                    if (result.verification && result.verification.status === "authenticated")
                        root.message = "SteamCMD signed in"
                    else if (result.verification && result.verification.status === "challenge-required")
                        root.message = "SteamCMD requires a Steam Guard code"
                    else
                        root.message = "Secret saved; SteamCMD authentication could not be verified"
                }, "Secret save failed")
        else if (target.kind === "setting")
            root.request("/plugins/" + target.plugin + "/setting/" + target.name,
                "POST", JSON.stringify({value: value}), function() {}, "Setting save failed")
        else if (target.kind === "store") {
            if (bookmarkStore && bookmarkStore.addBookmark(value)) {
                root.message = "Store saved"
                if (root.storeHomeRef) root.storeHomeRef.stores = bookmarkStore.bookmarks
                if (root.storeHomeLandingRef) root.storeHomeLandingRef.stores = bookmarkStore.bookmarks
            } else root.message = "Invalid store URL"
        } else if (target.kind === "store-name") {
            if (bookmarkStore && bookmarkStore.updateBookmarkName(target.id, value)) {
                root.message = "Store name updated"
                root.closeStoreOptions()
            } else root.message = "Store name must not be blank"
        } else if (target.kind === "store-url") {
            if (bookmarkStore && bookmarkStore.updateBookmarkUrl(target.id, value)) {
                root.message = "Store URL updated"
                root.closeStoreOptions()
            } else root.message = "Use a valid http:// or https:// URL"
        }
    }

    function beginLutrisSearch() {
        credentialTarget = ({kind: "lutris-search"})
        credentialValue = ""
        credentialKeyboardShown = false
        credentialKeyboardShowAttempted = false
        request("/credential/begin", "POST", JSON.stringify({
            title: "Find a Lutris game", prompt: "Game title",
            input_type: "text", secret: false, max_length: 160,
            presentation: "attached", multiline: false
        }), function(data) { credentialRequest = data }, "Lutris search input unavailable")
    }

    function selectedHomeStore() {
        if (space !== "home" || selectedCategoryIndex !== 1 || !storeHomeLandingRef)
            return null
        var card = storeHomeLandingRef.homeCards()[storeHomeLandingRef.homeSelectedIndex]
        return card && card.kind === "store" && card.id !== "steam"
            ? card : null
    }
    function openStoreOptions() {
        var card = selectedHomeStore()
        if (!card) return
        storeOptionsOpen = true
        storeOptions.store = card
        storeOptions.selectedIndex = 0
    }
    function closeStoreOptions() {
        storeOptionsOpen = false
        storeOptions.store = null
        pendingStoreRemovalId = ""
    }
    function beginStoreEdit(action) {
        var card = selectedHomeStore()
        if (!card) return
        credentialTarget = ({kind: action === "Change Name" ? "store-name" : "store-url", id: card.id})
        credentialValue = action === "Change Name" ? card.title : card.url
        credentialKeyboardShown = false
        credentialKeyboardShowAttempted = false
        request("/credential/begin", "POST", JSON.stringify({
            title: action, prompt: action === "Change Name" ? "Store Name" : "Store URL",
            input_type: "text", secret: false, max_length: action === "Change Name" ? 128 : 2048,
            presentation: "attached"
        }), function(data) { credentialRequest = data }, "Store editor unavailable")
    }
    function handleStoreOption(action) {
        if (action === "Change Name" || action === "Update URL") {
            beginStoreEdit(action)
            return
        }
        if (action === "Remove Store") {
            var card = selectedHomeStore()
            if (!card) return
            if (pendingStoreRemovalId !== card.id) {
                pendingStoreRemovalId = card.id
                message = "Press A again to remove " + card.title
                return
            }
            bookmarkStore.removeBookmark(card.id)
            closeStoreOptions()
            message = "Store removed"
        }
    }

    function activate() {
        console.log("CONTROLLER_ACTIVATE", "space", space,
                    "selectedCategory", selectedCategoryIndex,
                    "storeReady", !!storeHomeRef,
                    "storeSelected", storeHomeRef ? storeHomeRef.selectedIndex : -1)
        if (lutrisRecipeInstall.visible) {
            lutrisRecipeInstall.activate()
            return
        }
        if (lutrisAddGame.visible) {
            lutrisAddGame.activate()
            return
        }
        if (credentialRequest.status === "requested" || credentialRequest.status === "waiting") {
            submitCredential(false)
             return
         }
        if (root.homeLaunchGated)
            return
        playAudioEvent(audioEventForAction("confirm"))
        if (space === "system"
                && systemCategories[systemCategoryIndex] !== "Utilities"
                && settingsPanelFocus === "categories") {
            settingsPanelFocus = "content"
            if (settingsSpaceRef) settingsSpaceRef.enterContent()
            return
        }
        if (root.onboardingOpen && !root.onboardingNetworkSettings && !root.browserVisible) {
            onboardingPage.activate()
            return
        }
        if (root.browserVisible) {
            root.browserSurface.activate()
            return
        }
        if (gameOptionsOpen) {
            activateGameOptions()
            return
        }
        if (space === "system") {
            if (systemCategories[systemCategoryIndex] === "Utilities") {
                if (utilitiesHomeRef)
                    utilitiesHomeRef.activateSelected()
                return
            }
            if (systemCategories[systemCategoryIndex] === "System"
                    && systemSettings[systemRowIndex]) {
                var selectedKey = systemSettings[systemRowIndex].key
                if (selectedKey.indexOf("mudos.") === 0)
                    activateMudosAction(selectedKey)
                return
            }
            if (systemCategories[systemCategoryIndex] === "Network"
                    && internetSettingsRef) {
                internetSettingsRef.activate()
                return
            }
            if (systemCategories[systemCategoryIndex] === "Bluetooth"
                    && systemSettings[systemRowIndex]) {
                activateBluetoothSetting(systemSettings[systemRowIndex].key)
                return
            }
            if (systemCategories[systemCategoryIndex] === "Audio"
                    && audioSettingsRef) {
                audioSettingsRef.activate()
                return
            }
            if (systemCategories[systemCategoryIndex] === "Display"
                    && displaySettingsRef) {
                displaySettingsRef.activate()
                return
            }
            if (systemCategories[systemCategoryIndex] === "Controllers"
                    && controllerSettingsRef) {
                controllerSettingsRef.activate()
                return
            }
            if (systemCategories[systemCategoryIndex] === "Storage"
                    && storageSettingsRef) {
                storageSettingsRef.activate()
                return
            }
            if (systemSettings[systemRowIndex]
                    && systemSettings[systemRowIndex].key === "lulu.reset")
                resetMudos()
            return
        }
        if (space === "library") {
            if (visibleLibraryGame && !libraryTransitioning) {
                pendingLibraryLaunch = visibleLibraryGame
                libraryTransitionState = "ACTIVATING"
                libraryTransitioning = true
                libraryTransitionExpanding = false
                libraryTransitionProgress = 1
                libraryTransitionAnimation.restart()
                libraryContentFadeIn.stop()
                libraryContentFadeOut.restart()
                homeFadeOut.stop()
                homeFadeIn.stop()
            }
            return
        }
        if (space === "store") {
            if (storeHomeRef) {
                console.log("STORE_CONTROLLER_ACTIVATE", "selectedIndex", storeHomeRef.selectedIndex,
                            "displayCount", storeHomeRef.displayGames.length,
                            "selected", storeHomeRef.displayGames.length > storeHomeRef.selectedIndex
                                ? JSON.stringify(storeHomeRef.displayGames[storeHomeRef.selectedIndex]) : "null")
                storeHomeRef.activateSelected()
            }
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
            openSystemCategory(systemHomeRailRef ? systemHomeRailRef.selectedIndex : systemHomeCardIndex)
        } else if (selectedCategoryIndex === 1) {
            if (storeHomeLandingRef) {
                storeHomeLandingRef.activateHome()
                return
            }
            openInstallableSurface()
        } else {
            // Store space is not implemented for unknown future domains: message = "Store space is not implemented"
            message = "System space is not implemented"
        }
    }

    function openInstallableSurface() {
        console.log("INSTALLABLE_SURFACE_OPEN")
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
        if (storeHomeRef) {
            storeHomeRef.categoryIndex = 0
            storeHomeRef.selectedIndex = 0
        }
        refreshStore()
        message = ""
    }

    property string lastCredentialValue: ""
    function beginPluginCredential(plugin, name, title, prompt, kind, secret) {
        credentialTarget = ({plugin: plugin, name: name, kind: kind})
        credentialKeyboardShown = false
        credentialKeyboardShowAttempted = false
        request("/credential/begin", "POST", JSON.stringify({title: title, prompt: prompt,
                input_type: secret ? "secret" : "text", secret: secret, max_length: 4096,
                presentation: "attached"}),
                function(data) { credentialRequest = data }, "Credential editor unavailable")
    }

    function beginStoreBookmark() {
        credentialTarget = ({kind: "store"})
        credentialValue = ""
        credentialKeyboardShown = false
        credentialKeyboardShowAttempted = false
        request("/credential/begin", "POST", JSON.stringify({title: "Add New Store", prompt: "Store URL",
                input_type: "text", secret: false, max_length: 2048,
                presentation: "attached"}),
                function(data) { credentialRequest = data }, "Store URL input unavailable")
    }

    function settingsCategoryIndex(target) {
        for (var i = 0; i < systemCategories.length; i++)
            if (systemCategories[i] === target) return i
        return systemCategories.indexOf("System")
    }

    function openSettingsCategory(target) {
        systemCategoryIndex = settingsCategoryIndex(String(target || "System"))
        systemRowIndex = 0
        systemHomeCardIndex = 0
        space = "system"
        settingsPanelFocus = "categories"
        if (settingsSpaceRef) {
            var modelIndex = settingsCategoryModel.findIndex(function(item) {
                return item.target === systemCategories[systemCategoryIndex]
            })
            settingsSpaceRef.selectedCategory = Math.max(0, modelIndex)
            settingsSpaceRef.enterCategories()
        }
        console.log("SYSTEM_HOME_ACTIVATE", "category", systemCategories[systemCategoryIndex])
        refreshSystemSettings()
        if (systemCategories[systemCategoryIndex] === "System")
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

    function openSystemCategory(index) {
        systemHomeCardIndex = Math.max(0, Math.min(systemHomeCards.length - 1, index))
        if (systemHomeCards[systemHomeCardIndex] === "Utilities") {
            systemCategoryIndex = systemCategories.indexOf("Utilities")
            space = "system"
            refreshUtilities()
        } else {
            openSettingsCategory(systemCategories[systemCategoryIndex] === "Utilities"
                ? "System" : systemCategories[systemCategoryIndex])
        }
    }

    function moveSystemCategory(delta) {
        var rail = systemHomeRailRef
        var oldIndex = rail.selectedIndex
        rail.moveSelection(delta)
        systemHomeCardIndex = rail.selectedIndex
        if (oldIndex !== rail.selectedIndex)
            console.log("SYSTEM_HOME_NAV", "old", systemHomeCards[oldIndex],
                        "new", systemHomeCards[rail.selectedIndex])
    }

    function selectSettingsCategory(index) {
        var item = settingsCategoryModel[index]
        if (!item) return
        systemCategoryIndex = settingsCategoryIndex(item.target)
        systemRowIndex = 0
        refreshSystemSettings()
        if (item.target === "Network") refreshNetworkState()
        else if (item.target === "Audio") refreshAudioState()
        else if (item.target === "Storage") refreshStorageState()
        else if (item.target === "Display") refreshDisplayState()
        else if (item.target === "Controllers") refreshControllerState()
        if (item.target === "System") refreshMudosMenu()
    }

    function back() {
        playAudioEvent(audioEventForAction("back"))
        if (lutrisRecipeInstall.visible) {
            lutrisRecipeInstall.back()
            return
        }
        if (lutrisAddGame.visible) {
            lutrisAddGame.back()
            return
        }
        if (browserVisible) {
            if (credentialTarget.kind === "browser"
                    && (credentialRequest.status === "requested" || credentialRequest.status === "waiting")) {
                cancelBrowserTextInput()
                return
            }
            browserSurface.goBackOrClose()
            return
        }
        if (storeOptionsOpen) {
            closeStoreOptions()
            return
        }
        if (credentialRequest.status === "requested" || credentialRequest.status === "waiting") {
            credentialSubmitInFlight = false
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
        var onboardingBack = OnboardingBack.action(onboardingOpen, onboardingNetworkSettings,
                                                   !!(internetSettingsRef && internetSettingsRef.credentialView))
        if (onboardingBack !== "shell") {
            if (onboardingBack === "close-credential") {
                internetSettingsRef.credentialView = false
                request("/keyboard/hide", "POST", "", function(data) {})
            } else if (onboardingBack === "show-onboarding") {
                onboardingNetworkSettings = false
                space = "home"
                inputSurface.forceActiveFocus()
            }
            message = systemStatus && systemStatus.networkOnline
                ? "Choose Set Up Locally or Continue to Home."
                : "Connect to Wi-Fi or explicitly continue offline from onboarding."
            return
        }
        if (launchOverlayEffectiveVisible) {
            cancelLaunch()
            return
        }
        if (space === "downloads") {
            if (downloadsHomeRef && downloadsHomeRef.confirmationPending) {
                downloadsHomeRef.confirmationPending = false
                return
            }
            space = downloadsReturnSpace || "home"
            if (browserSuspended) {
                resumeBrowserSession()
            }
            message = ""
            return
        }
        if (gameOptionsOpen) {
            if (gameOptionsTextEntryActive) {
                finishGameOptionsTextEntry(true)
                return
            }
            if (gameOptionsView === "menu")
                closeGameOptions()
            else {
                gameOptionsView = "menu"
                gameOptionsIndex = 0
                artworkError = ""
            }
            return
        }
        if (space === "system"
                && systemCategories[systemCategoryIndex] === "Storage" && storageSettingsRef
                && storageSettingsRef.back())
            return
        if (space === "system"
                && systemCategories[systemCategoryIndex] === "Display" && displaySettingsRef
                && displaySettingsRef.back())
            return
        if (space === "system"
                && systemCategories[systemCategoryIndex] === "Controllers" && controllerSettingsRef
                && controllerSettingsRef.view !== "main"
                && controllerSettingsRef.back())
            return
        if (space === "system") {
            if (systemCategories[systemCategoryIndex] === "Network"
                    && internetSettingsRef && internetSettingsRef.credentialView) {
                internetSettingsRef.credentialView = false
                request("/keyboard/hide", "POST", "", function(data) {})
                return
            }
            console.log("SETTINGS_PAGE_CLOSE", "category", systemCategories[systemCategoryIndex])
            space = "home"
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
                if (!root.pendingLibraryLaunch)
                    homeFadeIn.restart()
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
            if (root.pendingLibraryLaunch) {
                var game = root.pendingLibraryLaunch
                root.pendingLibraryLaunch = null
                root.traceLaunchEvent("LIBRARY_SURFACE_HIDDEN", {game_id: String(game.game_id)})
                root.pendingHomeLaunch = game
                root.pendingHomeLaunchPhase = "exiting"
                if (presentationCoordinator.beginContentExit()) {
                    root.traceLaunchEvent("LIBRARY_WALLPAPER_EXIT_STARTED", {
                        game_id: String(game.game_id)
                    })
                } else {
                    root.pendingHomeLaunch = null
                    root.pendingHomeLaunchPhase = "idle"
                    root.homeContentOpacity = 1
                }
            }
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
        markStartupTiming("qml-loaded")
        inputSurface.forceActiveFocus()
        if (systemStatus)
            root.applyAcquisitionSnapshot(systemStatus.acquisitionSnapshot)
        startupLifecycle = "RECONCILING_LIBRARY"
        traceLaunchEvent("STARTUP_RECONCILE_BEGIN", {})
        requestStartupReadiness()
        loadOnboardingState()
    }

    Connections {
        target: systemStatus
        function onNetworkOnlineChanged() {
            if (root.onboardingOpen && root.onboardingNetworkSettings
                    && systemStatus.networkOnline) {
                root.onboardingNetworkSettings = false
                root.space = "home"
                root.message = "Network connected. Setup is ready."
                inputSurface.forceActiveFocus()
            }
        }
    }

    Timer {
        id: startupRuntimePoll
        interval: 750
        repeat: true
        running: root.startupSurfaceVisible
        onTriggered: root.request("/state", "GET", "", function(state) {
            root.startupRuntimeObserved = true
            var steam = state && state.resident_steam_runtime
                ? state.resident_steam_runtime.state : "unknown"
            root.startupSteamState = steam === "failed" || steam === "degraded"
                ? "unavailable" : steam
            var controllers = state && state.controller && state.controller.controllers
                ? state.controller.controllers : {}
            var ids = Object.keys(controllers)
            root.startupControllerConnected = ids.some(function(id) {
                return controllers[id] && controllers[id].connected === true
            })
        })
    }

    Timer {
        interval: 3000
        repeat: true
        running: root.onboardingOpen
        onTriggered: root.loadOnboardingState()
    }

    function controllerUp() {
            console.log("CONTROLLER_QML", "up", "gated", root.homeLaunchGated,
                        "space", root.space)
            if (root.homeLaunchGated) return
            root.playAudioEvent(root.audioEventForAction("up"))
            if (lutrisRecipeInstall.visible) { lutrisRecipeInstall.move(-1); return }
            if (lutrisAddGame.visible) { lutrisAddGame.move(-1); return }
            if (root.onboardingOpen && !root.onboardingNetworkSettings && !root.browserVisible) {
                onboardingPage.move(-1)
                return
            }
            if (root.browserVisible) { root.browserSurface.directional("up"); return }
            if (root.gameOptionsOpen) root.moveGameOptions(-1)
            else if (root.space === "home") root.moveDomain(-1)
            else if (root.space === "library") root.moveLibraryVertical(-1)
            else if (root.space === "store") {
                if (root.browserVisible) root.browserSurface.directional("up")
                else root.moveStoreGameVertical(-1)
            }
            else if (root.space === "downloads") root.moveDownloads(-1)
            else if (root.space === "system") {
                if (root.systemCategories[root.systemCategoryIndex] !== "Utilities"
                         && root.settingsPanelFocus === "categories") {
                    if (root.settingsSpaceRef) root.settingsSpaceRef.moveCategory(-1)
                }
                else if (root.systemCategories[root.systemCategoryIndex] === "Utilities" && root.utilitiesHomeRef)
                    root.utilitiesHomeRef.move(-1)
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
            root.playAudioEvent(root.audioEventForAction("down"))
            if (lutrisRecipeInstall.visible) { lutrisRecipeInstall.move(1); return }
            if (lutrisAddGame.visible) { lutrisAddGame.move(1); return }
            if (root.onboardingOpen && !root.onboardingNetworkSettings && !root.browserVisible) {
                onboardingPage.move(1)
                return
            }
            if (root.browserVisible) { root.browserSurface.directional("down"); return }
            if (root.gameOptionsOpen) root.moveGameOptions(1)
            else if (root.space === "home") root.moveDomain(1)
            else if (root.space === "library") root.moveLibraryVertical(1)
            else if (root.space === "store") {
                if (root.browserVisible) root.browserSurface.directional("down")
                else root.moveStoreGameVertical(1)
            }
            else if (root.space === "downloads") root.moveDownloads(1)
            else if (root.space === "system") {
                if (root.systemCategories[root.systemCategoryIndex] !== "Utilities"
                         && root.settingsPanelFocus === "categories") {
                    if (root.settingsSpaceRef) root.settingsSpaceRef.moveCategory(1)
                }
                else if (root.systemCategories[root.systemCategoryIndex] === "Utilities" && root.utilitiesHomeRef)
                    root.utilitiesHomeRef.move(1)
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
            root.playAudioEvent(root.audioEventForAction("left"))
            if (lutrisRecipeInstall.visible || lutrisAddGame.visible) return
            if (root.onboardingOpen && !root.onboardingNetworkSettings && !root.browserVisible)
                return
            if (root.browserVisible) { root.browserSurface.directional("left"); return }
            if (root.gameOptionsOpen) root.moveGameOptions(-1)
            else if (root.space === "home") {
                if (root.selectedCategoryIndex === 3) root.moveRecent(-1)
                else if (root.selectedCategoryIndex === 2) root.moveLibraryLanding(-1)
                else if (root.selectedCategoryIndex === 0) root.moveSystemCategory(-1)
                else if (root.selectedCategoryIndex === 1) root.moveStoreGame(-1)
            } else if (root.space === "library") {
                root.moveLibraryCategory(-1)
            } else if (root.space === "store") {
                if (root.browserVisible) root.browserSurface.directional("left")
                else root.moveStoreCategory(-1)
            } else if (root.space === "system") {
                if (root.systemCategories[root.systemCategoryIndex] !== "Utilities") {
                    if (root.settingsPanelFocus === "content"
                            && root.systemCategories[root.systemCategoryIndex] === "Audio"
                            && root.audioSettingsRef)
                        root.audioSettingsRef.adjust(-5)
                    else {
                        root.settingsPanelFocus = "categories"
                        if (root.settingsSpaceRef) root.settingsSpaceRef.enterCategories()
                    }
                }
                else if (root.systemCategories[root.systemCategoryIndex] === "Utilities" && root.utilitiesHomeRef)
                    root.utilitiesHomeRef.moveScreenshot(-1)
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
            root.playAudioEvent(root.audioEventForAction("right"))
            if (lutrisRecipeInstall.visible || lutrisAddGame.visible) return
            if (root.onboardingOpen && !root.onboardingNetworkSettings && !root.browserVisible)
                return
            if (root.browserVisible) { root.browserSurface.directional("right"); return }
            if (root.gameOptionsOpen) root.moveGameOptions(1)
            else if (root.space === "home") {
                if (root.selectedCategoryIndex === 3) root.moveRecent(1)
                else if (root.selectedCategoryIndex === 2) root.moveLibraryLanding(1)
                else if (root.selectedCategoryIndex === 0) root.moveSystemCategory(1)
                else if (root.selectedCategoryIndex === 1) root.moveStoreGame(1)
            } else if (root.space === "library") {
                root.moveLibraryCategory(1)
            } else if (root.space === "store") {
                if (root.browserVisible) root.browserSurface.directional("right")
                else root.moveStoreCategory(1)
            } else if (root.space === "downloads") {
                root.moveDownloads(1)
            } else if (root.space === "system") {
                if (root.systemCategories[root.systemCategoryIndex] !== "Utilities") {
                    if (root.settingsPanelFocus === "categories") {
                        root.settingsPanelFocus = "content"
                        if (root.settingsSpaceRef) root.settingsSpaceRef.enterContent()
                    } else if (root.systemCategories[root.systemCategoryIndex] === "Audio"
                               && root.audioSettingsRef)
                        root.audioSettingsRef.adjust(5)
                }
                else if (root.systemCategories[root.systemCategoryIndex] === "Utilities" && root.utilitiesHomeRef)
                    root.utilitiesHomeRef.moveScreenshot(1)
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
        if (lutrisRecipeInstall.visible || lutrisAddGame.visible)
            return
        if (root.space === "library")
            root.playAudioEvent(root.audioEventForAction(delta < 0 ? "leftShoulder" : "rightShoulder"))
        if (root.space === "library") root.moveLibraryCollection(delta)
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
            // Credential text entry is the sole Mudos controller owner. The
            // TextInput receives its own generated keyboard events; shell
            // shortcuts must be consumed and never replayed after handoff.
            if (root.credentialRequest.status === "requested"
                    || root.credentialRequest.status === "waiting") {
                if (event.key === Qt.Key_Escape) {
                    root.back()
                    event.accepted = true
                } else if (root.credentialRequest.input_type === "waiting"
                           && event.key === Qt.Key_X) {
                    root.submitCredential(false, "enter-code")
                    event.accepted = true
                } else if ((event.key === Qt.Key_Return || event.key === Qt.Key_Enter)
                           && !root.credentialRequest.multiline) {
                    root.submitCredential(true)
                    event.accepted = true
                }
                return
            }
            if (root.launchScreenVisible) {
                if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter) {
                    if (root.normalizedLaunchCancellable)
                        root.cancelLaunch()
                    else if (root.launchStatus === "failed")
                        root.dismissLaunchFailure()
                } else if (event.key === Qt.Key_Escape || event.key === Qt.Key_Backspace) {
                    if (root.normalizedLaunchCancellable)
                        root.cancelLaunch()
                    else if (root.launchStatus === "failed")
                        root.dismissLaunchFailure()
                }
                // The launch screen has one actionable control. Keep all
                // controller navigation on that control instead of allowing
                // hidden Home content to receive shell shortcuts.
                event.accepted = true
                return
            }
            if (root.homeLaunchGated) {
                event.accepted = true
                return
            }
            if (lutrisAddGame.visible) {
                if (event.key === Qt.Key_Up) lutrisAddGame.move(-1)
                else if (event.key === Qt.Key_Down) lutrisAddGame.move(1)
                else if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter) lutrisAddGame.activate()
                else if (event.key === Qt.Key_Escape || event.key === Qt.Key_Backspace) lutrisAddGame.back()
                event.accepted = true
                return
            }
            if (lutrisRecipeInstall.visible) {
                if (event.key === Qt.Key_Up) lutrisRecipeInstall.move(-1)
                else if (event.key === Qt.Key_Down) lutrisRecipeInstall.move(1)
                else if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter) lutrisRecipeInstall.activate()
                else if (event.key === Qt.Key_Escape || event.key === Qt.Key_Backspace) lutrisRecipeInstall.back()
                event.accepted = true
                return
            }
            if (event.key === Qt.Key_X) {
                if (root.browserVisible)
                    browserSurface.requestTextEntryForFocusedElement()
                else if (root.selectedHomeStore())
                    root.openStoreOptions()
                else
                    root.openSelectedGameOptions()
                event.accepted = true
                return
            }
            if (event.key === Qt.Key_Y) {
                if (space === "library") lutrisAddGame.open()
                else if (credentialRequest.status !== "requested" && credentialRequest.status !== "waiting"
                         && space !== "downloads")
                    openDownloads(space)
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
            if (storeOptionsOpen) {
                if (event.key === Qt.Key_Up || event.key === Qt.Key_Left) {
                    storeOptions.move(-1); event.accepted = true
                } else if (event.key === Qt.Key_Down || event.key === Qt.Key_Right) {
                    storeOptions.move(1); event.accepted = true
                } else if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter) {
                    storeOptions.activate(); event.accepted = true
                } else if (event.key === Qt.Key_Escape || event.key === Qt.Key_Backspace) {
                    closeStoreOptions(); event.accepted = true
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
                    moveLibraryCategory(-1)
                    event.accepted = true
                } else if (event.key === Qt.Key_Right) {
                    moveLibraryCategory(1)
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
                    moveStoreCategory(-1)
                    event.accepted = true
                } else if (event.key === Qt.Key_Right) {
                    moveStoreCategory(1)
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
                if (event.key === Qt.Key_Up) {
                    controllerUp(); event.accepted = true
                } else if (event.key === Qt.Key_Down) {
                    controllerDown(); event.accepted = true
                } else if (event.key === Qt.Key_Left) {
                    controllerLeft(); event.accepted = true
                } else if (event.key === Qt.Key_Right) {
                    controllerRight(); event.accepted = true
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
             launchExitActive: root.pendingLibraryLaunch !== null
            homeX: root.homeContentRailX
            homeY: root.homeActiveContentOriginY
             homeWidth: root.homeNavigationCardWidth
            homeHeight: root.libraryHomePresentationHeight
            fullscreenX: root.expandedShellX
            fullscreenY: root.expandedShellY
            fullscreenWidth: root.expandedShellWidth
            fullscreenHeight: root.expandedShellHeight
             uiScale: root.uiScale
             panelSurfaceColor: luluPalette.librarySurface
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
                        onItemCountChanged: root.syncRecentDomain()
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
                          selectedIndex: root.libraryHomeIndex
                         categories: root.libraryCollections
                         onOpenRequested: {
                             root.commitLibraryCategory(index)
                             root.activate()
                        }
                    }
                }

                Item {
                    id: storeReveal
                    // Clip the Store rail at the screen edge, not at the
                    // content inset; match the System and Library reveals.
                    x: -root.homeContentRailX
                    y: root.homeCategoryOffset(1)
                    width: root.width
                    height: root.homeCategoryRevealHeight(1)
                    clip: true
                    opacity: 1
                    visible: root.selectedCategoryIndex === 1
                        || (root.homeCategoryTransitioning
                            && (root.homeCategoryFrom === 1 || root.homeCategoryTarget === 1))
         StoreHome {
                         id: storeHomeLanding
                         x: root.homeContentRailX
                         width: storeReveal.width - root.homeContentRailX
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
                          pluginStores: root.pluginStoreCards
                         onSteamStoreRequested: root.openSteamStore()
                          onHomeDownloadRequested: root.openInstallableSurface()
                          onHomeStoreRequested: function(id, name, url) { root.launchHomeStore(id, name, url) }
                          onHomeStoreOptionsRequested: root.openStoreOptions()
                         onHomeAddStoreRequested: root.beginStoreBookmark()
                         Component.onCompleted: root.storeHomeLandingRef = storeHomeLanding
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
                        categories: root.systemHomeCards
                        selectedIndex: root.systemHomeCardIndex
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
                        onOpenRequested: root.openSystemCategory(index)
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
             id: librarySpace
            x: 0
            width: parent.width
            height: parent.height
            visible: root.space === "library" || root.libraryTransitioning
             canonicalGames: root.libraryGames
             acquisitionJobs: root.acquisitionJobs
             dimensionKey: root.libraryDimension
             dimensionLabel: root.libraryDimensionLabel(root.libraryDimension)
             transitionState: root.libraryTransitionState
             transitionProgress: root.libraryTransitionProgress
             transitionExpanding: root.libraryTransitionExpanding
             returnState: root.space === "library" ? "EXPANDED" : "RESTING"
             uiScale: root.uiScale
             typography: typography
             luluPalette: luluPalette
             canonicalTexture: orbitTexture
             canonicalCoordinateRoot: orbitRenderSource
             canonicalSize: Qt.size(root.width, root.height)
              contentBounds: Qt.rect(root.expandedShellX, root.expandedShellY,
                                     root.expandedShellWidth, root.expandedShellHeight)
             contentSideMargin: root.expandedContentSideMargin
             contentBottom: root.expandedContentBottom
             contentOpacity: root.libraryContentOpacity
              onLaunchRequested: root.launchGame(game)
          }

        LutrisAddGame {
            id: lutrisAddGame
            apiUrl: root.apiUrl
            x: 0
            y: 0
            width: parent.width
            height: parent.height
            onRegistered: {
                root.request("/refresh?stage=lutris", "POST", "", function() {
                    root.refreshLibrary()
                }, "Lutris library refresh failed")
            }
        }

        LutrisRecipeInstall {
            id: lutrisRecipeInstall
            apiUrl: root.apiUrl
            x: 0
            y: 0
            width: parent.width
            height: parent.height
            onSubmitted: function(jobId) {
                root.message = "Lutris installation submitted"
                root.refreshAcquisitionJobs()
                root.openDownloads("store")
            }
        }

          StoreOptions {
             id: storeOptions
             anchors.fill: parent
             store: root.storeOptionsOpen ? root.selectedHomeStore() : null
             uiScale: root.uiScale
             typography: typography
             luluPalette: luluPalette
             onActivated: root.handleStoreOption(action)
             onBacked: root.closeStoreOptions()
         }

        StoreHome {
            id: storeHome
            anchors.fill: parent
            visible: root.space === "store" || root.storeTransitioning
            availableGames: root.storeAvailableGames
             acquisitionJobs: root.acquisitionJobs
             stores: root.storeBookmarks
             pluginStores: root.pluginStoreCards
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
              contentBounds: Qt.rect(root.expandedShellX, root.expandedShellY,
                                     root.expandedShellWidth, root.expandedShellHeight)
             contentBottom: root.expandedContentBottom
            errorMessage: root.storeError
            contentOpacity: root.libraryContentOpacity
             onSteamStoreRequested: root.openSteamStore()
             onStoreRequested: function(url) { root.openBrowser(url) }
             onAddStoreRequested: root.beginStoreBookmark()
            onInstallGameRequested: root.installGame(game)
            onDownloadsRequested: root.openDownloads("store")
            Component.onCompleted: root.storeHomeRef = storeHome
         }

        MudosBrowser {
            id: browserSurface
            anchors.fill: parent
            z: 300
            visible: root.browserVisible
            onClosed: root.closeBrowser()
            onEditableFocused: function(field) { root.beginBrowserTextInput(field) }
            onEditableTargetUnavailable: {
                if (root.browserVisible && root.credentialRequest.status !== "requested"
                        && root.credentialRequest.status !== "waiting")
                    root.request("/keyboard/hide", "POST", "", function() {})
            }
             onTrustedLoginForm: function(details) { root.trustedWebCredentialRequest(details) }
             onTrustedCredentialsCaptured: function(details) { root.trustedWebCredentialCaptured(details) }
             onExternalNavigationRequested: function(targetUrl, sourceOrigin, disposition) {
                 browserSurface.setExternalActionMessage("Preparing installation…")
                 root.message = "Preparing installation…"
                 root.request("/browser-handoff", "POST", JSON.stringify({
                     uri: targetUrl, source_origin: sourceOrigin, disposition: disposition
                 }), function(data) {
                     browserSurface.setExternalActionMessage(data.message || "Installation queued")
                     root.message = data.message || "Installation queued"
                 }, "Mudos could not accept this browser action")
             }
         }

        DownloadsHome {
            id: downloadsHome
            anchors.fill: parent
            visible: root.space === "downloads"
            z: 90
            snapshot: systemStatus.acquisitionSnapshot
            serviceAvailable: systemStatus.acquisitionAvailable
            uiScale: root.uiScale
            typography: typography
            luluPalette: luluPalette
            canonicalTexture: orbitTexture
            canonicalCoordinateRoot: orbitRenderSource
            canonicalSize: Qt.size(root.width, root.height)
             onPauseRequested: root.pauseAcquisition(jobId)
             onResumeRequested: root.resumeAcquisition(jobId)
             onCancelRequested: root.cancelAcquisition(jobId)
             onClearRequested: root.clearAcquisition(jobId)
             onRetryRequested: root.retryAcquisition(jobId)
            Component.onCompleted: root.downloadsHomeRef = downloadsHome
        }

        SettingsSpace {
            id: settingsSpace
            x: root.expandedShellX
            y: root.expandedShellY + root.activeHeadingHeight + root.headingCardGap
            width: root.expandedShellWidth
            height: Math.max(1, root.expandedShellBottom - y)
            visible: root.space === "system"
                && root.systemCategories[root.systemCategoryIndex] !== "Utilities"
            categories: root.settingsCategoryModel
            selectedCategory: Math.max(0, root.settingsCategoryModel.findIndex(function(item) {
                return item.target === root.systemCategories[root.systemCategoryIndex]
            }))
            activePanel: root.settingsPanelFocus
            uiScale: root.uiScale
            typography: typography
            luluPalette: luluPalette
            canonicalTexture: orbitTexture
            canonicalCoordinateRoot: orbitRenderSource
            canonicalSize: Qt.size(root.width, root.height)
            onCategoryChanged: root.selectSettingsCategory(index)
            onPanelFocusRequested: root.settingsPanelFocus = panel
            Component.onCompleted: root.settingsSpaceRef = settingsSpace
        }
        Text {
            x: root.expandedShellX + 22 * root.uiScale
            y: root.expandedShellY + 8 * root.uiScale
            visible: settingsSpace.visible
            text: "SETTINGS"
            color: luluPalette.headingAccent
            font.family: typography.majorHeadingFamily
            font.weight: typography.majorHeadingWeight
            font.pixelSize: typography.size("section", 30)
            font.letterSpacing: 5 * root.uiScale
        }

        SystemSpace {
            id: systemSpace
            parent: settingsSpace.contentHost
            anchors.fill: parent
            visible: settingsSpace.visible
                && (root.systemCategories[root.systemCategoryIndex] === "System"
                    || root.systemCategories[root.systemCategoryIndex] === "Bluetooth")
            category: root.systemCategories[root.systemCategoryIndex]
            embedded: true
            textInputFocusEnabled: root.settingsPanelFocus === "content"
            settings: root.systemSettings
            selectedIndex: root.systemRowIndex
            uiScale: root.uiScale
            typography: typography
            luluPalette: luluPalette
            canonicalTexture: orbitTexture
            canonicalCoordinateRoot: orbitRenderSource
            canonicalSize: Qt.size(root.width, root.height)
            expandedShellX: 0
            expandedShellY: 0
            expandedShellWidth: settingsSpace.contentHost.width
            expandedShellHeight: settingsSpace.contentHost.height
            expandedShellBottom: settingsSpace.contentHost.height
            onActionRequested: {
                if (root.systemCategories[root.systemCategoryIndex] === "System")
                    root.activateMudosAction(key)
                else if (root.systemCategories[root.systemCategoryIndex] === "Bluetooth")
                    root.activateBluetoothSetting(key)
                else if (key === "lulu.reset") root.resetMudos()
            }
            onInteractionRequested: {
                root.settingsPanelFocus = "content"
                settingsSpace.enterContent()
            }
            onTextInputRequested: root.request("/keyboard/show", "POST", "", function() {})
        }

        UtilitiesHome {
            id: utilitiesHome
            anchors.fill: parent
            visible: root.space === "system"
                && root.systemCategories[root.systemCategoryIndex] === "Utilities"
            applications: root.utilities
            uiScale: root.uiScale
            typography: typography
            luluPalette: luluPalette
            canonicalTexture: orbitTexture
            canonicalCoordinateRoot: orbitRenderSource
            canonicalSize: Qt.size(root.width, root.height)
            expandedShellX: root.expandedShellX
            expandedShellY: root.expandedShellY
            expandedShellWidth: root.expandedShellWidth
            expandedShellHeight: root.expandedShellHeight
            onLaunchRequested: function(applicationRef) { root.launchUtility(applicationRef) }
            Component.onCompleted: {
                root.utilitiesHomeRef = utilitiesHome
                utilitiesHome.applications = root.utilities
            }
        }

        InternetSettings {
            id: internetSettings
            parent: settingsSpace.contentHost
            onboardingMode: root.onboardingOpen && root.onboardingNetworkSettings
            anchors.fill: parent
            visible: settingsSpace.visible
                && root.systemCategories[root.systemCategoryIndex] === "Network"
            networkData: root.networkState
            selectedIndex: 0
            embedded: true
            uiScale: root.uiScale
            typography: typography
            luluPalette: luluPalette
            canonicalTexture: orbitTexture
            canonicalCoordinateRoot: orbitRenderSource
            canonicalSize: Qt.size(root.width, root.height)
            expandedShellX: 0
            expandedShellY: 0
            expandedShellWidth: settingsSpace.contentHost.width
            expandedShellHeight: settingsSpace.contentHost.height
            expandedShellBottom: settingsSpace.contentHost.height
            Component.onCompleted: root.internetSettingsRef = internetSettings
            onInteractionRequested: {
                root.settingsPanelFocus = "content"
                settingsSpace.enterContent()
            }
            onOperationRequested: root.networkOperation(action, ssid, password)
            onBackRequested: root.back()
        }

        AudioSettings {
            id: audioSettings
            parent: settingsSpace.contentHost
            anchors.fill: parent
            visible: settingsSpace.visible
                && root.systemCategories[root.systemCategoryIndex] === "Audio"
            audioData: root.audioState
            selectedIndex: 0
            embedded: true
            uiScale: root.uiScale
            typography: typography
            luluPalette: luluPalette
            canonicalTexture: orbitTexture
            canonicalCoordinateRoot: orbitRenderSource
            canonicalSize: Qt.size(root.width, root.height)
            expandedShellX: 0
            expandedShellY: 0
            expandedShellWidth: settingsSpace.contentHost.width
            expandedShellHeight: settingsSpace.contentHost.height
            expandedShellBottom: settingsSpace.contentHost.height
            Component.onCompleted: root.audioSettingsRef = audioSettings
            onInteractionRequested: {
                root.settingsPanelFocus = "content"
                settingsSpace.enterContent()
            }
            onOperationRequested: root.audioOperation(action, deviceId, volume, inputDevice, muted)
            onBackRequested: root.back()
        }

        StorageSettings {
            id: storageSettings
            parent: settingsSpace.contentHost
            anchors.fill: parent
            visible: settingsSpace.visible
                && root.systemCategories[root.systemCategoryIndex] === "Storage"
            storageData: root.storageState
            selectedIndex: 0
            embedded: true
            uiScale: root.uiScale
            typography: typography
            luluPalette: luluPalette
            canonicalTexture: orbitTexture
            canonicalCoordinateRoot: orbitRenderSource
            canonicalSize: Qt.size(root.width, root.height)
            expandedShellX: 0
            expandedShellY: 0
            expandedShellWidth: settingsSpace.contentHost.width
            expandedShellHeight: settingsSpace.contentHost.height
            expandedShellBottom: settingsSpace.contentHost.height
            Component.onCompleted: root.storageSettingsRef = storageSettings
            onInteractionRequested: {
                root.settingsPanelFocus = "content"
                settingsSpace.enterContent()
            }
            onOperationRequested: root.storageOperation(action, deviceId, kind)
            onBackRequested: root.back()
        }

        DisplaySettings {
            id: displaySettings
            parent: settingsSpace.contentHost
            anchors.fill: parent
            visible: settingsSpace.visible
                && root.systemCategories[root.systemCategoryIndex] === "Display"
            displayData: root.displayState
            embedded: true
            uiScale: root.uiScale
            typography: typography
            luluPalette: luluPalette
            canonicalTexture: orbitTexture
            canonicalCoordinateRoot: orbitRenderSource
            canonicalSize: Qt.size(root.width, root.height)
            expandedShellX: 0
            expandedShellY: 0
            expandedShellWidth: settingsSpace.contentHost.width
            expandedShellHeight: settingsSpace.contentHost.height
            expandedShellBottom: settingsSpace.contentHost.height
            Component.onCompleted: root.displaySettingsRef = displaySettings
            onInteractionRequested: {
                root.settingsPanelFocus = "content"
                settingsSpace.enterContent()
            }
            onApplyRequested: root.applyDisplay(output, width, height, refresh)
            onBackRequested: root.back()
        }

        ControllerSettings {
            id: controllerSettings
            parent: settingsSpace.contentHost
            anchors.fill: parent
            visible: settingsSpace.visible
                && root.systemCategories[root.systemCategoryIndex] === "Controllers"
            controllerData: root.controllerState
            embedded: true
            uiScale: root.uiScale
            typography: typography
            luluPalette: luluPalette
            canonicalTexture: orbitTexture
            canonicalCoordinateRoot: orbitRenderSource
            canonicalSize: Qt.size(root.width, root.height)
            expandedShellX: 0
            expandedShellY: 0
            expandedShellWidth: settingsSpace.contentHost.width
            expandedShellHeight: settingsSpace.contentHost.height
            expandedShellBottom: settingsSpace.contentHost.height
            Component.onCompleted: root.controllerSettingsRef = controllerSettings
            onInteractionRequested: {
                root.settingsPanelFocus = "content"
                settingsSpace.enterContent()
            }
            onOperationRequested: root.controllerOperation(action, controllerId, player)
            onRefreshRequested: root.refreshControllerState()
            onBackRequested: root.back()
        }

        GameOptions {
            id: gameOptions
            game: root.gameOptionsGame
            view: root.gameOptionsView
            selectedIndex: root.gameOptionsIndex
            uninstallSupported: root.uninstallCapability.supported === true
            uninstallInProgress: root.uninstallCapability.in_progress === true
            uninstallDescription: String(root.uninstallCapability.description || "Remove installed content")
            artworkCandidates: root.artworkCandidates
            mappingResults: root.mappingCandidates
            mappingQuery: root.mappingQuery
            titleOverride: !!(root.gameOptionsGame && root.gameOptionsGame.display_title_override)
            artworkRole: root.selectedArtworkRole
            errorMessage: root.artworkError
            uiScale: root.uiScale
            typography: typography
            luluPalette: luluPalette
            Component.onCompleted: root.gameOptionsRef = gameOptions
            onTextEntryRequested: root.showGameOptionsKeyboard()
            onTextEntryCancelled: root.finishGameOptionsTextEntry(true)
            onTextEntrySubmitted: root.finishGameOptionsTextEntry(false)
            onMappingQueryEdited: function(query) { root.mappingQuery = query }
            onMappingSearchRequested: function(query) { root.searchGameMapping(query) }
            onActivated: root.activateGameOptions()
            onBacked: root.back()
        }

        SystemStatusStrip {
            id: systemStatusStrip
            z: 50
            anchors.top: parent.top
            anchors.right: parent.right
            anchors.topMargin: root.statusStripTop
            anchors.rightMargin: root.statusStripRightMargin
            visible: presentationCoordinator.contentState
                !== presentationCoordinator.hiddenState
            opacity: presentationCoordinator.presentationProgress
            transform: Translate {
                y: -systemStatusStrip.height
                    * (1 - presentationCoordinator.presentationProgress)
            }
            compact: false
            uiScale: root.uiScale
            canonicalTexture: orbitTexture
            canonicalCoordinateRoot: orbitRenderSource
            canonicalSize: Qt.size(root.width, root.height)
            presentationProgress: presentationCoordinator.presentationProgress
            typography: typography
            luluPalette: luluPalette
            activeDownloadCount: systemStatus ? systemStatus.activeDownloadCount : 0
            controllers: controllerBridge.controllers
            bluetoothAvailable: systemStatus ? systemStatus.bluetoothPowered : false
            bluetoothState: systemStatus ? systemStatus.bluetoothState : "unavailable"
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
                    fontFamily: root.space === "library" ? "JetBrains Mono" : typography.interfaceFamily
                    uiScale: root.uiScale
                    typography: typography
                    luluPalette: luluPalette
                }
                ControllerHint {
                    action: "previousCollection"
                    visible: root.space === "library"
                    label: root.libraryDimensionLabel(root.adjacentLibraryDimension(-1))
                    fontFamily: root.space === "library" ? "JetBrains Mono" : typography.interfaceFamily
                    uiScale: root.uiScale
                    typography: typography
                    luluPalette: luluPalette
                }
                ControllerHint {
                    action: "nextCollection"
                    visible: root.space === "library"
                    label: root.libraryDimensionLabel(root.adjacentLibraryDimension(1))
                    fontFamily: root.space === "library" ? "JetBrains Mono" : typography.interfaceFamily
                    uiScale: root.uiScale
                    typography: typography
                    luluPalette: luluPalette
                }
                ControllerHint {
                    action: "confirm"
                    label: root.space === "library" ? "Launch" : "Download"
                    fontFamily: root.space === "library" ? "JetBrains Mono" : typography.interfaceFamily
                    uiScale: root.uiScale
                    typography: typography
                    luluPalette: luluPalette
                }
                ControllerHint {
                    visible: root.space === "library" && root.libraryFocus === "games" && root.visibleLibraryGame !== null
                    action: "options"
                    label: "Game Options"
                    fontFamily: "JetBrains Mono"
                    uiScale: root.uiScale
                    typography: typography
                    luluPalette: luluPalette
                }
                ControllerHint {
                    action: "back"
                    label: "Back"
                    fontFamily: root.space === "library" ? "JetBrains Mono" : typography.interfaceFamily
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
                    label: root.space === "system"
                        && root.systemCategories[root.systemCategoryIndex] !== "Utilities"
                        ? (root.settingsPanelFocus === "categories"
                            ? "Categories · → Settings" : "Settings · ← Categories")
                        : root.selectedCategoryIndex === 3 ? "Navigation" : "Navigate"
                    uiScale: root.uiScale
                    typography: typography
                    luluPalette: luluPalette
                }
                ControllerHint {
                    action: "confirm"
                    label: root.space === "system"
                            && root.systemCategories[root.systemCategoryIndex] !== "Utilities"
                        ? (root.settingsPanelFocus === "categories" ? "Enter Settings" : "Select")
                        : root.space === "store" ? "Download"
                           : root.selectedCategoryIndex === 3 ? "Launch"
                           : root.selectedCategoryIndex === 2 ? "Open Library" : "Select"
                    uiScale: root.uiScale
                    typography: typography
                    luluPalette: luluPalette
                }
                ControllerHint {
                    visible: root.selectedHomeStore() !== null
                    action: "options"
                    label: "Store Options"
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
                ControllerHint {
                    visible: root.space === "system"
                    action: "back"
                    label: "Back"
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
        id: launchScreen
        visible: root.launchScreenVisible
        z: 100
        anchors.fill: parent
        clip: true
        color: luluPalette.launchOverlaySurface
        Column {
            width: Math.min(parent.width * 0.76, root.design(900))
            anchors.centerIn: parent
            spacing: root.design(20)
            BusyIndicator {
                anchors.horizontalCenter: parent.horizontalCenter
                width: root.design(94)
                height: width
                running: launchScreen.visible
                palette.dark: luluPalette.primaryText
                palette.text: luluPalette.primaryText
            }
            Text {
                width: parent.width
                text: "Launching " + root.launchTitle
                color: luluPalette.primaryText
                font.family: typography.interfaceFamily
                font.pixelSize: typography.size("title", 30)
                horizontalAlignment: Text.AlignHCenter
                wrapMode: Text.Wrap
            }
            Text {
                width: parent.width
                text: root.normalizedLaunchStageLabel
                color: luluPalette.accent
                font.family: typography.interfaceFamily
                font.pixelSize: typography.size("heading", 21)
                horizontalAlignment: Text.AlignHCenter
                wrapMode: Text.Wrap
            }
            Text {
                visible: root.normalizedLaunchProvider !== "" || root.normalizedLaunchDetail !== ""
                width: parent.width
                text: [root.normalizedLaunchProvider ? root.normalizedLaunchProvider.toUpperCase() : "",
                       root.normalizedLaunchDetail].filter(function(value) { return value !== "" }).join(" · ")
                color: luluPalette.secondaryText
                font.family: typography.interfaceFamily
                font.pixelSize: typography.size("secondary", 14)
                horizontalAlignment: Text.AlignHCenter
                wrapMode: Text.Wrap
                elide: Text.ElideRight
            }
            Column {
                width: parent.width
                spacing: root.design(8)
                Repeater {
                    model: root.launchLogLines.slice(-3)
                    delegate: Text {
                        required property string modelData
                        width: root.width * 0.74
                        text: modelData
                        color: luluPalette.secondaryText
                        font.family: "monospace"
                        font.pixelSize: typography.size("secondary", 11)
                        horizontalAlignment: Text.AlignHCenter
                        wrapMode: Text.Wrap
                        maximumLineCount: 2
                        elide: Text.ElideRight
                    }
                }
            }
            Button {
                id: cancelLaunchButton
                anchors.horizontalCenter: parent.horizontalCenter
                visible: root.launchStatus !== "failed"
                    && root.normalizedLaunchCancellable
                enabled: visible
                text: "Cancel Launch"
                focus: launchScreen.visible && visible
                onClicked: root.cancelLaunch()
                Accessible.name: "Cancel game launch"
            }
            Button {
                anchors.horizontalCenter: parent.horizontalCenter
                visible: root.launchStatus === "failed"
                text: "Return to Home"
                focus: launchScreen.visible && visible
                onClicked: root.dismissLaunchFailure()
                Accessible.name: "Return to Home after launch failure"
            }
        }
    }

    Onboarding {
        id: onboardingPage
        z: 500
        visible: root.onboardingOpen && !root.onboardingNetworkSettings && !root.browserVisible
        online: typeof systemStatus !== "undefined" && systemStatus.networkOnline
        networkAdapterAvailable: root.onboardingWifiAvailable
        uiScale: root.uiScale
        typography: typography
        luluPalette: luluPalette
        onOpenNetworkSettings: root.onboardingOpenNetwork()
        onContinueToHome: root.onboardingContinueHome()
        onSetUpLocally: root.onboardingOpenLocalSetup()
    }

    Timer {
        id: startupReadinessTimer
        interval: 50
        repeat: false
        onTriggered: root.requestStartupReadiness()
    }

    Timer {
        interval: 100
        running: root.perfDiagnostics
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
