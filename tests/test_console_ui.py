import os
import shutil
import subprocess
import unittest
import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

from lulu.consoled import ConsoleInterface
from lulu.providers.model import GuideAction


ROOT = Path(__file__).parents[1]
QML = (ROOT / "ui" / "ConsoleShell.qml").read_text()
SHELL_PROFILE = (ROOT / "config" / "inputplumber" / "profiles" / "shell.yaml").read_text()


class ConsoleUiTests(unittest.TestCase):
    def test_startup_surface_is_visible_until_existing_intro_and_never_gates_on_provider(self):
        qml = (ROOT / "ui/ConsoleShell.qml").read_text()
        surface = qml[qml.index("Rectangle {\n        id: startupSurface"):
                      qml.index("PresentationCoordinator {", qml.index("Rectangle {\n        id: startupSurface"))]
        self.assertIn('visible: root.startupSurfaceVisible', surface)
        self.assertIn('text: "MUDOS"', surface)
        self.assertIn('label: "Steam"', surface)
        self.assertIn('"unavailable"', surface)
        self.assertIn('if (!startupLibraryReady || !startupCatalogueSnapshotLoaded', qml)
        self.assertIn("presentationCoordinator.beginStartup()", qml)
        self.assertNotIn("startupSteamState ===", qml)

    def test_guide_input_mode_action_toggles_and_names_current_transition(self) -> None:
        interface = ConsoleInterface.__new__(ConsoleInterface)
        interface._base_guide = (GuideAction(
            "switch-compatibility", "Switch Input Mode", "system", "session:set-input-mode",
            ("game",), False, 10,
        ),)
        interface._mudos_guide = ()
        interface._providers = SimpleNamespace(get=lambda _provider: None, guide_actions=lambda *_args: ())
        state = {"lifecycle": "game", "provider_id": "steam", "session_kind": "game",
                 "input_mode": "compat"}
        interface.sessiond = SimpleNamespace(
            call_get_state=AsyncMock(return_value=json.dumps(state)),
            call_set_input_mode=AsyncMock(),
        )

        actions = json.loads(asyncio.run(ConsoleInterface.GetGuideActions.__wrapped__(interface)))
        self.assertEqual(actions[0]["label"], "Switch to Gamepad Mode")
        self.assertEqual(asyncio.run(ConsoleInterface.ExecuteGuideAction.__wrapped__(
            interface, "switch-compatibility")), "executed")
        interface.sessiond.call_set_input_mode.assert_awaited_once_with("gamepad")

    def test_utility_guide_is_explicit_and_quit_targets_sessiond_identity(self) -> None:
        interface = ConsoleInterface.__new__(ConsoleInterface)
        interface._base_guide = ()
        interface._mudos_guide = ()
        interface._providers = SimpleNamespace(
            get=lambda _provider: self.fail("Utility Guide must not resolve a game provider"),
            guide_actions=lambda *_args: (),
        )
        utility_state = {
            "lifecycle": "game", "session_kind": "utility", "session_title": "Ptyxis",
            "primary_id": "utility:flatpak:app.devsuite.Ptyxis", "launch_token": "token",
            "active_identity": {"token": "token", "pgid": 1234},
            "delegated_surface": "utility",
        }
        interface.sessiond = SimpleNamespace(
            call_get_state=AsyncMock(return_value=json.dumps(utility_state)),
            call_quit_active_session=AsyncMock(),
        )
        context, provider = interface._guide_context(utility_state)
        self.assertEqual(context, "utility")
        self.assertIsNone(provider)
        actions = json.loads(asyncio.run(ConsoleInterface.GetGuideActions.__wrapped__(interface)))
        self.assertEqual([action["id"] for action in actions], ["utility-close"])
        self.assertEqual(actions[0]["label"], "Close Utility")

        result = asyncio.run(ConsoleInterface.ExecuteGuideAction.__wrapped__(interface, "utility-close"))
        self.assertEqual(result, "executed")
        interface.sessiond.call_quit_active_session.assert_awaited_once_with()

    def test_utility_guide_heading_identifies_classification_and_item(self) -> None:
        guide = (ROOT / "ui" / "MudosGuide.qml").read_text()
        native = (ROOT / "native" / "mudos-guide.cpp").read_text()
        self.assertIn('guideModel.sessionClassification !== ""', guide)
        self.assertIn('guideModel.sessionTitle', guide)
        self.assertIn('kind == QStringLiteral("utility")', native)
        self.assertIn('QStringLiteral("UTILITY")', native)
        self.assertIn('surface == QStringLiteral("browser")', native)
        self.assertIn('QStringLiteral("BROWSER")', native)

    def test_game_and_browser_guide_contexts_remain_distinct(self) -> None:
        interface = ConsoleInterface.__new__(ConsoleInterface)
        interface.catalogue = SimpleNamespace(store=SimpleNamespace(get_game=lambda _game: None))
        interface._platforms = SimpleNamespace()
        interface._providers = SimpleNamespace(get=lambda _provider: None)
        self.assertEqual(interface._guide_context({"lifecycle": "game", "session_kind": "game",
                                                   "provider_id": "steam"})[0], "game")
        self.assertEqual(interface._guide_context({"lifecycle": "game", "session_kind": "utility",
                                                   "delegated_surface": "utility"})[0], "utility")
        self.assertEqual(interface._guide_context({"lifecycle": "game", "delegated_surface": "browser"})[0],
                         "browser")

    def test_dolphin_guide_quit_routes_through_sessiond_identity(self) -> None:
        interface = ConsoleInterface.__new__(ConsoleInterface)
        interface._base_guide = ()
        interface._mudos_guide = ()
        interface._providers = SimpleNamespace(
            get=lambda provider: SimpleNamespace(provider_id=provider),
            guide_actions=lambda provider, context: (
                GuideAction("dolphin-quit", "Quit Dolphin", "quit",
                            "process-group-terminate", ("game", "standalone"), False, 90),
            ),
        )
        interface.sessiond = SimpleNamespace(
            call_get_state=AsyncMock(return_value=json.dumps({
                "lifecycle": "game", "provider_id": "dolphin", "session_kind": "game",
            })),
            call_quit_active_session=AsyncMock(),
        )
        result = asyncio.run(ConsoleInterface.ExecuteGuideAction.__wrapped__(
            interface, "dolphin-quit",
        ))
        self.assertEqual(result, "executed")
        interface.sessiond.call_quit_active_session.assert_awaited_once_with()

    def test_store_reveal_clips_at_screen_edge_without_moving_rail(self) -> None:
        viewport = QML.split("id: homeCardViewport", 1)[1].split("id: homeContent", 1)[0]
        reveal = QML.split("id: storeReveal", 1)[1].split("id: systemReveal", 1)[0]
        self.assertIn("x: 0", viewport)
        self.assertIn("clip: true", viewport)
        self.assertIn("x: -root.homeContentRailX", reveal)
        self.assertIn("width: root.width", reveal)
        self.assertIn("clip: true", reveal)
        self.assertIn("id: storeHomeLanding\n                         x: root.homeContentRailX", reveal)
        self.assertIn("width: storeReveal.width - root.homeContentRailX", reveal)
        self.assertIn("readonly property real homeContentRailX: design(52)", QML)
        self.assertIn("targetX: root.homeRailX(index - root.homeSelectedIndex)",
                      (ROOT / "ui" / "StoreHome.qml").read_text())

    def test_external_installable_selection_refreshes_game_preview(self) -> None:
        library_space = (ROOT / "ui" / "LibrarySpace.qml").read_text()
        handler = library_space.split("onSelectedIndexChanged:", 1)[1].split(
            "Component.onCompleted:", 1)[0]
        self.assertIn("if (!committingProjection)", handler)
        self.assertIn("if (!browsingExternalCategories)", handler)
        self.assertIn("preparePreview()", handler)

    def test_game_options_scope_and_controller_text_entry_lifecycle(self) -> None:
        shell = (ROOT / "ui" / "ConsoleShell.qml").read_text()
        options = (ROOT / "ui" / "GameOptions.qml").read_text()
        for action in ("Change Mapping", "Change Artwork", "Change Title", "Uninstall"):
            self.assertIn(action, options)
        self.assertNotIn("Restore Automatic Artwork", options)
        self.assertIn("onMappingSearchRequested", shell)
        self.assertIn("/metadata/search?game_id=", shell)
        self.assertIn("/metadata/match/", shell)
        self.assertIn("/artwork/candidates?game_id=", shell)
        self.assertIn('role: selectedArtworkRole', shell)
        self.assertIn("/keyboard/show", shell)
        self.assertIn("/keyboard/status", shell)
        self.assertIn("/keyboard/hide", shell)
        self.assertIn("function keyboardDismissed()", options)
        self.assertIn("mappingInput.forceActiveFocus()", options)
        self.assertIn("titleInput.forceActiveFocus()", options)
        self.assertIn("id: candidateDelegate", options)
        self.assertIn("candidateDelegate.modelData.thumbnail", options)
        self.assertIn("candidateDelegate.modelData.title", options)
        self.assertIn('role: "cover"', options)
        self.assertIn('role: "icon_square"', options)
        self.assertIn('role: "preview_still"', options)
        self.assertIn("function selectedCandidate()", options)
        self.assertIn("selectGameMapping(gameOptionsRef.selectedCandidate())", shell)
        self.assertIn("var artwork = gameOptionsRef.selectedCandidate()", shell)
        self.assertIn("selectedCandidateId", options)
        self.assertIn("candidate.id", shell)
        self.assertNotIn("artworkRow.modelData", options)
        self.assertNotIn("resultRow.modelData", options)
        self.assertIn("function closeGameOptions()", shell)
        self.assertIn("selectedGameForOptions", shell)
        self.assertIn("onAccepted:", options)

    def test_library_preview_is_image_only_and_multimedia_disabled(self) -> None:
        library = (ROOT / "ui" / "LibrarySpace.qml").read_text()
        self.assertNotIn("import QtMultimedia", library)
        self.assertNotIn("MediaPlayer", library)
        self.assertNotIn("VideoOutput", library)
        self.assertIn("readonly property bool videoPreviewsEnabled: false", library)

    def test_library_animation_is_cached_lazy_and_selection_scoped(self) -> None:
        library = (ROOT / "ui" / "LibrarySpace.qml").read_text()
        self.assertIn('!root.visible', library)
        self.assertIn('root.previewAnimationGameId === String(root.selectedGame.game_id)', library)
        self.assertIn('selectedGame.preview_animation_url', library)
        self.assertIn("AnimatedImage {", library)
        self.assertIn("cache: false", library)
        self.assertNotIn("XMLHttpRequest", library)
        self.assertNotIn("preview-animation/", library)
        self.assertIn("videoPreviewsEnabled: false", library)
        self.assertIn("fillMode: Image.PreserveAspectFit", library)
        self.assertIn("parent.height * 16 / 9", library)
        self.assertIn("GameArtwork.previewStill(root.selectedGame)", library)
        self.assertNotIn("XMLHttpRequest", library)
        self.assertNotIn("ffmpeg", library.lower())

    def test_shell_does_not_export_retired_ffmpeg_video_flags(self) -> None:
        bridge = (ROOT / "scripts" / "console-ui-bridge.py").read_text()
        self.assertNotIn("QT_FFMPEG_DECODING_HW_DEVICE_TYPES", bridge)
        self.assertNotIn("QT_DISABLE_HW_TEXTURES_CONVERSION", bridge)

    def test_qml_preserves_card_to_space_shell_interaction(self) -> None:
        self.assertIn('readonly property var domains: HomeDomains.categories(recentDomainAvailable)', QML)
        self.assertIn('onItemCountChanged: root.syncRecentDomain()', QML)
        self.assertIn('onStartupLibraryReadyChanged: if (startupLibraryReady) syncRecentDomain()', QML)
        self.assertIn('readonly property real statusStripTop: expandedShellTop', QML)
        self.assertIn('readonly property real statusStripRightMargin: expandedShellSideMargin', QML)
        self.assertIn("property int selectedCategoryIndex: 3", QML)
        self.assertIn('property string space: "home"', QML)
        self.assertIn('presentationTarget = "library"', QML)
        self.assertIn('space = settled.space', QML)
        self.assertIn('LibrarySurfaceTransition.completedState', QML)
        self.assertIn('space = "home"', QML)
        self.assertIn('readonly property string apiUrl:', QML)
        self.assertIn("function activate()", QML)
        self.assertIn("readonly property bool launchOverlayEffectiveVisible:", QML)
        self.assertIn("readonly property bool launchScreenVisible:", QML)
        self.assertIn("visible: root.launchScreenVisible", QML)
        self.assertIn("palette.dark: luluPalette.primaryText", QML)
        self.assertIn("palette.text: luluPalette.primaryText", QML)
        self.assertIn('text: "Cancel Launch"', QML)
        self.assertIn('request("/launch-status", "GET"', QML)
        self.assertIn("function moveDomain(delta)", QML)
        self.assertIn("function openSteamStore()", QML)
        self.assertIn('notify("Unavailable", "System space is not implemented", "warning")', QML)
        self.assertIn('function openGameOptions(game)', QML)
        self.assertIn('event.key === Qt.Key_X', QML)
        self.assertIn('action: "options"', QML)
        self.assertIn('GameOptions {', QML)
        self.assertIn('space === "library" && libraryFocus === "games"', QML)
        self.assertIn('space === "home" && selectedCategoryIndex === 3', QML)
        self.assertIn('if (gameOptionsView === "menu")', QML)
        self.assertIn("Math.max(0, Math.min(domains.length - 1", QML)
        self.assertIn("Math.max(0, Math.min(recentHome.itemCount - 1", QML)
        self.assertNotIn("% domains.length", QML)
        self.assertNotIn("% catalogueRecentModel.count", QML)
        self.assertNotIn("Behavior on opacity", QML)
        self.assertNotIn("Behavior on scale", QML)
        recent = (ROOT / "ui" / "RecentHome.qml").read_text()
        self.assertIn("toRelativeIndex: index - recentHome.selectedIndex", recent)
        self.assertNotIn("visibleRailRadius", recent)
        self.assertNotIn("presentationStartVisible", recent)
        self.assertIn("capturePresentation()", recent)
        self.assertIn("suppressTransitionCompletion", recent)
        self.assertIn("transitionAnimation.stop()", recent)
        self.assertIn("transitionAnimation.start()", recent)
        self.assertIn("compactCardWidth + railGap", recent)
        self.assertNotIn("edgeViewportWidth", recent)
        self.assertNotIn("edgePeek", recent)
        self.assertIn("x: -root.homeContentRailX", QML)
        self.assertIn("titleRailY", QML)
        self.assertIn("titleRailTargetY", QML)
        self.assertIn("titleRailActiveGap", QML)
        self.assertIn("titleRailLayoutY(index, activeIndex)", QML)
        self.assertIn("visible: true", QML)
        self.assertIn("anchors.horizontalCenter: parent.horizontalCenter", QML)
        self.assertIn("homeBottomBandCenterY: height - design(36)", QML)
        self.assertIn("homeCategoryRailX: design(52)", QML)
        self.assertIn('homeCategoryFontSize: typography.size("display", 48)', QML)
        self.assertIn("homeCategoryGap: design(25)", QML)
        self.assertIn("homeCategoryPitch: homeCategoryFontSize + homeCategoryGap", QML)
        self.assertNotIn('text: "HOME"', QML)
        self.assertIn("homeFocalCardHeight", QML)
        self.assertIn("homeFocalCardWidth", QML)
        self.assertIn("homeCompactCardWidth", QML)
        self.assertIn("homeNavigationCardAspect: 0.62", QML)
        self.assertIn("homeNavigationCardHeight: homeNavigationCardWidth", QML)
        self.assertIn("compactCardWidth: homeNavigationCardWidth", QML)
        self.assertIn("compactCardHeight: homeNavigationCardHeight", QML)
        self.assertIn("compactGameCardWidth: compactCardWidth", QML)
        self.assertIn("homeCategoryTitleSelectedProgress", QML)
        self.assertIn("homeCategoryTitleOpacityForSelection", QML)
        self.assertIn("Math.abs(index - selectedIndex)", QML)
        self.assertIn("var minimumOpacity = 0.30", QML)
        self.assertIn("var maximumDistance = 3.0", QML)
        self.assertIn("(1.0 - minimumOpacity) / maximumDistance", QML)
        self.assertIn("luluPalette.navigationText", QML)
        self.assertIn("luluPalette.headingAccent", QML)
        self.assertIn("homeInterCardGap: design(24)", QML)
        self.assertIn("homeHeadingCardClearance: design(12)", QML)
        self.assertIn("homeCompositionOffsetY: -design(36)", QML)
        self.assertIn("opacity: libraryHome.contentOpacity", (ROOT / "ui" / "LibraryHome.qml").read_text())
        self.assertIn("property bool libraryHandoffPending: false", QML)
        self.assertIn("handoffTimer.restart()", QML)
        self.assertIn("NavigationCard", (ROOT / "ui" / "LibraryHome.qml").read_text())
        self.assertIn('request("/?scope=recent"', QML)
        self.assertIn('readonly property string libraryScope:', QML)
        self.assertNotIn("/dev/input", QML)
        self.assertNotIn("Social", QML)

    def test_reset_mudos_uses_the_shared_session_boundary(self) -> None:
        guide = (ROOT / "ui" / "MudosGuide.qml").read_text()
        system_space = (ROOT / "ui" / "SystemSpace.qml").read_text()
        bridge = (ROOT / "scripts" / "console-ui-bridge.py").read_text()
        native_guide = (ROOT / "native" / "mudos-guide.cpp").read_text()
        self.assertIn('guideModel.actions', guide)
        self.assertIn('GetGuideActions', native_guide)
        base = (ROOT / "config/guide/base.toml").read_text()
        self.assertIn('id = "switch-compatibility"', base)
        self.assertIn('id = "restart-mudos"', base)
        self.assertIn('id = "reboot-system"', base)
        self.assertIn('id = "shutdown-system"', base)
        self.assertIn('ExecuteGuideAction', native_guide)
        self.assertIn('key === "lulu.reset"', system_space + QML)
        self.assertIn('request("/reset", "POST"', QML)
        self.assertIn("call_reset_mudos", bridge)
        self.assertIn('path == "/reset"', bridge)

    def test_shell_guide_is_limited_and_confirms_power_actions_natively(self) -> None:
        guide = (ROOT / "ui" / "MudosGuide.qml").read_text()
        native_guide = (ROOT / "native" / "mudos-guide.cpp").read_text()
        native_shell = (ROOT / "native" / "lulu-shell.cpp").read_text()
        self.assertIn('guideModel.actions', guide)
        self.assertIn('confirm', native_guide)
        self.assertIn('viewModel_->value("confirmationPending").toBool()', native_guide)
        self.assertIn('target = "system:reboot"', (ROOT / "config/guide/base.toml").read_text())
        self.assertIn('target = "system:shutdown"', (ROOT / "config/guide/base.toml").read_text())
        self.assertNotIn('Quit Application', guide)
        self.assertNotIn('systemctl', guide)
        self.assertNotIn('focusedWindow_ == window_->winId()', native_shell)

    def test_retroarch_provider_menu_fallback_is_native_and_platform_scoped(self) -> None:
        native_guide = (ROOT / "native" / "mudos-guide.cpp").read_text()
        retroarch = (ROOT / "config/providers/retroarch/provider.toml").read_text()
        pcsx2 = (ROOT / "config/providers/pcsx2/provider.toml").read_text()
        self.assertIn('target = "command:/usr/bin/retroarch --command MENU_TOGGLE"', retroarch)
        self.assertIn('target = "key:F12"', pcsx2)
        self.assertIn('xcb_test_fake_input', native_guide)
        self.assertNotIn('KEY_ESC', native_guide)

    def test_extracted_ui_primitives_preserve_real_game_card_data(self) -> None:
        for filename in ("GameCard.qml", "RecentHome.qml", "LibraryHome.qml", "LibrarySpace.qml", "PlaceholderHome.qml"):
            self.assertTrue((ROOT / "ui" / filename).exists())
        game_card = (ROOT / "ui" / "GameCard.qml").read_text()
        library_space = (ROOT / "ui" / "LibrarySpace.qml").read_text()
        self.assertIn("property var game: null", game_card)
        self.assertIn("card.game.artwork_url", game_card)
        self.assertIn('property string dimensionKey: "platform"', library_space)
        self.assertIn("signal launchRequested", library_space)

    def test_recent_refresh_avoids_unchanged_model_replacement(self) -> None:
        game_card = (ROOT / "ui" / "GameCard.qml").read_text()
        navigation_surface = (ROOT / "ui" / "NavigationCardSurface.qml").read_text()
        spatial_surface = (ROOT / "ui" / "LibrarySpatialSurface.qml").read_text()
        self.assertNotIn("interval: 16", navigation_surface + spatial_surface)
        self.assertIn("readonly property var catalogueRecentModel: recentModel", QML)
        self.assertIn("recentModel: root.catalogueRecentModel", QML)
        self.assertNotIn("recentGames =", QML)
        self.assertIn("property string selectionAnchorId", (ROOT / "ui" / "RecentHome.qml").read_text())
        self.assertNotIn("recentModel.count", (ROOT / "ui" / "RecentHome.qml").read_text())
        self.assertIn("recentRepeater.count", (ROOT / "ui" / "RecentHome.qml").read_text())
        self.assertIn("nativePlayCanonicalRect", game_card)
        self.assertIn("canonicalRect: root.canonicalRect", navigation_surface)

    def test_recent_selection_has_one_live_index_derived_identity(self) -> None:
        recent = (ROOT / "ui" / "RecentHome.qml").read_text()
        self.assertIn("readonly property string selectedGameId:", recent)
        self.assertNotIn("selectedGameId =", recent)
        shell = QML
        self.assertIn("readonly property string recentSelectedGameId:", shell)
        self.assertNotIn("root.recentSelectedGameId =", shell)
        self.assertIn("beginPendingHomeLaunch(visibleRecentGame)", shell)

    def test_provider_and_download_guide_actions_are_contextual(self) -> None:
        guide = (ROOT / "ui" / "MudosGuide.qml").read_text()
        native = (ROOT / "native" / "mudos-guide.cpp").read_text()
        consoled = (ROOT / "src" / "lulu" / "consoled.py").read_text()
        self.assertIn('guideModel.actions', guide)
        self.assertIn('def GetGuideActions', consoled)
        self.assertIn('def SetProviderSetting', consoled)
        self.assertIn('load_providers()', consoled)
        self.assertNotIn('source: "UiAudioEngine.qml"', guide)
        self.assertNotIn("audioEventSerial", guide + native)
        self.assertNotIn("fps_show", guide + native)

    def test_controller_hint_groups_center_on_the_full_interaction_rail(self) -> None:
        shell = (ROOT / "ui" / "ConsoleShell.qml").read_text()
        library_space = (ROOT / "ui" / "LibrarySpace.qml").read_text()
        self.assertGreaterEqual(shell.count("width: implicitWidth"), 2)
        self.assertGreaterEqual(shell.count("anchors.horizontalCenter: parent.horizontalCenter"), 2)
        self.assertNotIn("width: parent.width * 0.54", shell)

    def test_internet_settings_uses_network_boundary_and_controller_model(self) -> None:
        qml = (ROOT / "ui" / "InternetSettings.qml").read_text()
        shell = (ROOT / "ui" / "ConsoleShell.qml").read_text()
        bridge = (ROOT / "scripts" / "console-ui-bridge.py").read_text()
        consoled = (ROOT / "src" / "lulu" / "consoled.py").read_text()
        network = (ROOT / "src" / "lulu" / "network_manager.py").read_text()
        self.assertIn('signal operationRequested(string action, string ssid, string password)', qml)
        self.assertIn('operationRequested("connect", selectedSsid, password)', qml)
        self.assertIn('request("/network"', shell)
        self.assertIn('request("/keyboard/show"', shell)
        self.assertIn('path.startswith("/network/")', bridge)
        self.assertIn('def GetNetworkState', consoled)
        self.assertIn('def ConnectWifi', consoled)
        self.assertIn('BusType.SYSTEM', network)
        self.assertNotIn('nmcli', network)
        self.assertIn('operationRequested("forget", row.ssid, "")', qml)
        self.assertIn('passwordInput.forceActiveFocus()', qml)

    def test_setup_back_stays_in_onboarding_until_explicit_dismissal(self) -> None:
        shell = (ROOT / "ui" / "ConsoleShell.qml").read_text()
        back = shell.split('function back() {', 1)[1].split('NumberAnimation {', 1)[0]
        self.assertIn('OnboardingBack.action(onboardingOpen, onboardingNetworkSettings,', back)
        self.assertIn('if (onboardingBack !== "shell")', back)
        self.assertIn('onboardingNetworkSettings = false', back)
        self.assertIn('space = "home"', back)
        self.assertIn('internetSettingsRef.credentialView = false', back)
        self.assertLess(back.index('if (onboardingBack !== "shell")'),
                        back.index('if (space === "system")'))
        self.assertNotIn('onboardingOpen && (!systemStatus || !systemStatus.networkOnline)', back)
        self.assertIn('request("/onboarding/dismiss", "POST"', shell)

    def test_onboarding_handoff_and_completion_reuse_startup_intro(self) -> None:
        onboarding = (ROOT / "ui" / "Onboarding.qml").read_text()
        shell = (ROOT / "ui" / "ConsoleShell.qml").read_text()
        self.assertIn('http://mudos.local/setup', onboarding)
        self.assertIn('onboardingCompletionPending = true', shell)
        self.assertIn('startupLifecycle = "READY_FOR_INTRO"', shell)
        self.assertIn('presentationCoordinator.beginStartup()', shell)
        self.assertIn('onContinueToHome: root.onboardingContinueHome()', shell)

    def test_audio_settings_uses_session_audio_boundary_and_controller_model(self) -> None:
        qml = (ROOT / "ui" / "AudioSettings.qml").read_text()
        shell = (ROOT / "ui" / "ConsoleShell.qml").read_text()
        bridge = (ROOT / "scripts" / "console-ui-bridge.py").read_text()
        consoled = (ROOT / "src" / "lulu" / "consoled.py").read_text()
        audio = (ROOT / "src" / "lulu" / "audio_manager.py").read_text()
        self.assertIn('signal operationRequested(string action, string deviceId, int volume, bool inputDevice, bool muted)', qml)
        self.assertIn('Left/Right: Volume', qml)
        self.assertIn('request("/audio"', shell)
        self.assertIn('path.startswith("/audio/")', bridge)
        self.assertIn('def GetAudioState', consoled)
        self.assertIn('def SetAudioVolume', consoled)
        self.assertIn('pactl', audio)
        self.assertNotIn('QtMultimedia', qml + shell)

    def test_storage_settings_uses_udisks_boundary_and_stable_targets(self) -> None:
        qml = (ROOT / "ui" / "StorageSettings.qml").read_text()
        shell = (ROOT / "ui" / "ConsoleShell.qml").read_text()
        bridge = (ROOT / "scripts" / "console-ui-bridge.py").read_text()
        consoled = (ROOT / "src" / "lulu" / "consoled.py").read_text()
        storage = (ROOT / "src" / "lulu" / "storage_manager.py").read_text()
        paths = (ROOT / "src" / "lulu" / "paths.py").read_text()
        self.assertIn('request("/storage"', shell)
        self.assertIn('path.startswith("/storage/")', bridge)
        self.assertIn('def GetStorageState', consoled)
        self.assertIn('def MountStorage', consoled)
        self.assertIn('BusType.SYSTEM', storage)
        self.assertIn('IdUUID', storage)
        self.assertIn('system', storage)
        self.assertIn('steam_library_root', paths)
        self.assertIn('request("/refresh"', shell)
        self.assertIn('root.refreshCatalogue()', shell)
        self.assertNotIn('lsblk', storage + qml)

    def test_typography_uses_central_semantic_families(self) -> None:
        typography = (ROOT / "ui" / "Typography.qml").read_text()
        self.assertIn("FontLoader", typography)
        self.assertIn("regularFont.name", typography)
        self.assertIn('familyForRole("icon", "icons")', typography)
        self.assertIn('familyForRole("display", "heavy")', typography)
        self.assertIn('familyForRole("majorHeading", "heavy")', typography)
        self.assertIn('familyForRole("interface", "regular")', typography)
        self.assertIn('themeRoles.majorHeading === "bold"', typography)
        palette = (ROOT / "ui" / "LuluPalette.qml").read_text()
        for role in ("guideSurface", "guideBorder", "guideItemSurface", "guideSelectedText",
                     "overlayBackdrop", "overlaySurface", "launchOverlaySurface"):
            self.assertIn(role, palette)
        self.assertIn("function size(role, value)", typography)
        for filename in ("ConsoleShell.qml", "GameCard.qml", "LibraryHome.qml", "LibrarySpace.qml", "PlaceholderHome.qml", "RecentHome.qml"):
            self.assertIn("typography", (ROOT / "ui" / filename).read_text())

    def test_semantic_asset_and_controller_boundaries(self) -> None:
        catalog = (ROOT / "ui" / "MudosAssetCatalog.js").read_text()
        profiles = (ROOT / "ui" / "ControllerProfiles.js").read_text()
        icon = (ROOT / "ui" / "MudosIcon.qml").read_text()
        controller = (ROOT / "ui" / "ControllerGlyph.qml").read_text()
        self.assertIn("wifi:", catalog)
        self.assertIn("function platformArtwork", catalog)
        self.assertIn("function suppliedArtwork", catalog)
        self.assertIn("function physicalControl", profiles)
        self.assertIn("function glyphFile", profiles)
        self.assertIn("function glyph(profile, action)", profiles)
        self.assertIn('confirm: "a"', profiles)
        self.assertIn('previousCollection: "leftBumper"', profiles)
        self.assertIn('a: "\\u0100"', profiles)
        self.assertIn("mudosTheme.fonts.controller", controller)
        self.assertIn('options: "x"', (ROOT / "ui" / "ControllerProfiles.js").read_text())
        self.assertIn("MudosAssetCatalog.icon", icon)
        self.assertIn("tightBoundingRect", icon)
        self.assertIn("verticalAlignment: Text.AlignVCenter", icon)
        self.assertIn('collection: "\\ueb9c"', catalog)
        self.assertIn('download: "\\uf019"', catalog)
        self.assertNotIn('font.family: "JetBrains Mono"', controller)
        self.assertIn("controllerProfile", controller)

    def test_ui_palette_is_semantic_and_centralized(self) -> None:
        palette = (ROOT / "ui" / "LuluPalette.qml").read_text()
        for role in ("primaryText", "secondaryText", "mutedText", "selectedText", "accent",
                     "focusIndicator", "warning", "glassTint", "glassBorder", "backdrop"):
            self.assertIn("property color " + role, palette)
        for filename in ("ConsoleShell.qml", "GameCard.qml", "RecentHome.qml", "LibraryHome.qml", "LibrarySpace.qml", "PlaceholderHome.qml"):
            component = (ROOT / "ui" / filename).read_text()
            self.assertIn("luluPalette", component)
            self.assertNotRegex(component, r'(?m)^\s*(?:border\.)?color:\s*"#')

    def test_system_status_strip_is_shell_level_and_responsive(self) -> None:
        strip = (ROOT / "ui" / "SystemStatusStrip.qml").read_text()
        shell = (ROOT / "ui" / "ConsoleShell.qml").read_text()
        system_home = (ROOT / "ui" / "SystemHome.qml").read_text()
        library_home = (ROOT / "ui" / "LibraryHome.qml").read_text()
        store_home = (ROOT / "ui" / "StoreHome.qml").read_text()
        native = (ROOT / "native" / "lulu-shell.cpp").read_text()
        self.assertIn('property bool compact', strip)
        self.assertIn('property var controllers', strip)
        self.assertIn('property int activeDownloadCount', strip)
        self.assertIn('readonly property real backingPadding', strip)
        self.assertIn('? 0 : root.groupSpacing', strip)
        self.assertIn('&& root.leadingControllerIndex < 0 ? 0 : root.groupSpacing', strip)
        self.assertIn('index !== root.leadingControllerIndex', strip)
        self.assertIn('width: root.activeDownloadCount > 0', strip)
        self.assertIn('downloadContent.implicitWidth + contentInset : 0', strip)
        self.assertIn('controllerPresentation.setProperty(index, "present", false)', strip)
        self.assertIn('if (!controllerPresentation.get(index).present)', strip)
        self.assertIn('objectName: "statusBacking"', strip)
        self.assertIn('MudosGlassItem {', strip)
        self.assertIn('backdrop: root.canonicalTexture', strip)
        self.assertIn('canonicalRect: root.backingCanonicalRect', strip)
        self.assertIn('presentationProgress: presentationCoordinator.presentationProgress', shell)
        self.assertIn('property string networkConnectionType', strip)
        self.assertIn('root.networkConnectionType === "ethernet"', strip)
        self.assertIn('? "ethernet" : "wifi"', strip)
        self.assertIn('"wifiOff"', strip)
        self.assertIn('"bluetoothOn"', strip)
        self.assertIn('text: player', strip)
        self.assertIn('visible: batteryKind === "percent" && batteryPercentage >= 0', strip)
        self.assertIn('text: ": " + battery', strip)
        self.assertIn('Qt.formatTime(new Date(), "HH:mm")', strip)
        self.assertIn('SystemStatusStrip {', shell)
        self.assertIn('MudosAssetCatalog.systemIcon(modelData)', system_home)
        self.assertIn('MudosAssetCatalog.libraryDimensionIcon(modelData.mode)', library_home)
        library_space = (ROOT / "ui/LibrarySpace.qml").read_text()
        spatial = (ROOT / "ui/LibrarySpatialSurface.qml").read_text()
        self.assertEqual(library_space.count('border.color: root.luluPalette.libraryBorder'), 2)
        self.assertIn('panelSurfaceColor: luluPalette.librarySurface', shell)
        self.assertIn('opacity: root.panelSurfaceOpacity * root.surfacePresentationProgress', spatial)
        self.assertIn('kind === "catalogue"', store_home)
        self.assertIn('root.selectedCategoryIndex === 3 ? "Navigation" : "Navigate"', shell)
        self.assertNotIn('"Navigate / Games"', shell)
        self.assertIn('systemStatus.networkConnected', shell)
        self.assertIn('systemStatus.bluetoothPowered', shell)
        self.assertIn('systemStatus.activeDownloadCount', shell)
        self.assertIn('systemStatus.networkConnectionType', shell)
        self.assertIn('org.lulu.Acquisitiond', native)
        self.assertIn('activeDownloadCountChanged', native)
        self.assertIn('acquisitionSnapshotChanged', native)
        self.assertIn('acquisitionAvailable', native)
        self.assertIn('onAcquisitionRegistered', native)
        self.assertIn('onAcquisitionUnregistered', native)
        unregistered = native[native.index('void onAcquisitionUnregistered'):
                              native.index('\nprivate:', native.index('void onAcquisitionUnregistered'))]
        self.assertIn('setAcquisitionAvailable(false)', unregistered)
        self.assertNotIn('updateAcquisitionSnapshot', unregistered)
        self.assertIn('setAcquisitionAvailable(false)', native)
        self.assertIn('root.serviceAvailable && !root.confirmationPending',
                      (ROOT / "ui/DownloadsHome.qml").read_text())
        self.assertNotIn('root.applyAcquisitionSnapshot("{\\"jobs\\":[],\\"activeDownloadCount\\":0}")',
                         shell)
        self.assertIn('refreshAcquisitionStatus()', native)
        self.assertIn('acquisitionSnapshot', shell)
        self.assertIn('interval: 30000', shell)
        self.assertIn('controllers: controllerBridge.controllers', shell)
        self.assertNotIn('statusControllers', shell)
        self.assertIn('setContextProperty("systemStatus", &systemStatus)',
                      (ROOT / "native" / "lulu-shell.cpp").read_text())
        self.assertIn('Q_PROPERTY(QString bluetoothState', native)
        self.assertIn('Q_PROPERTY(QString networkConnectionType', native)
        self.assertIn('networkConnectionTypeChanged', native)
        self.assertIn('802-3-ethernet', native)
        self.assertIn('802-11-wireless', native)
        self.assertIn('QStringLiteral("Default")', native)
        self.assertIn('org.freedesktop.NetworkManager', native)
        self.assertIn('org.bluez', native)
        self.assertIn('anchors.right: parent.right', shell)
        status = shell.split('objectName: "shellStatusChrome"', 1)[1].split('\n        }', 1)[0]
        self.assertIn('parent: root.contentItem', status)
        self.assertIn('anchors.topMargin: root.statusStripTop', status)
        self.assertIn('anchors.rightMargin: root.statusStripRightMargin', status)
        self.assertNotIn('transform: Translate', status)
        self.assertNotIn('root.space ===', status)
        self.assertIn('visible: presentationCoordinator.contentState', shell)
        self.assertIn('opacity: presentationCoordinator.presentationProgress', shell)
        self.assertIn('opacity: presentationCoordinator.presentationProgress', status)
        self.assertIn('compact: false', shell)
        self.assertIn('TextMetrics', (ROOT / "ui" / "StatusGlyph.qml").read_text())
        self.assertIn('tightBoundingRect.height', (ROOT / "ui" / "StatusGlyph.qml").read_text())
        self.assertIn('targetPaintedHeight', (ROOT / "ui" / "StatusGlyph.qml").read_text())
        self.assertIn('displayFamily', strip)
        self.assertIn('displayWeight', strip)
        self.assertIn('property real innerSpacing', strip)
        self.assertIn('property real groupSpacing', strip)
        self.assertIn('text: ": " + battery', strip)

    def test_system_settings_is_controller_first_and_backend_driven(self) -> None:
        system_home = (ROOT / "ui" / "SystemHome.qml").read_text()
        system_space = (ROOT / "ui" / "SystemSpace.qml").read_text()
        self.assertIn('property var systemCategories:', QML)
        self.assertIn('property var systemSettings:', QML)
        self.assertIn('function settingsCategoryIndex(target)', QML)
        self.assertIn('function openSettingsCategory(target)', QML)
        self.assertIn('openSettingsCategory("Network")', QML)
        self.assertIn('systemHomeCards[systemHomeCardIndex] === "Utilities"', QML)
        self.assertIn('settingsSpaceRef.moveCategory(-1)', QML)
        self.assertIn('settingsSpaceRef.moveCategory(1)', QML)
        self.assertIn('request("/settings?category="', QML)
        self.assertIn('signal openRequested(int index)', system_home)
        self.assertIn('PageUp', QML)
        self.assertIn('PageDown', QML)
        settings_page = (ROOT / "ui" / "MudosSettingsPage.qml").read_text()
        self.assertIn('modelData.label', settings_page)
        self.assertIn('LibrarySpatialSurface {', settings_page)
        self.assertIn('surfaceVisible: !root.embedded', settings_page)
        self.assertIn('MudosCardSurface {', settings_page)
        self.assertIn('MudosSettingsPage {', system_space)
        self.assertIn('property var systemCategories: ["System", "Display", "Audio", "Network", "Bluetooth", "Controllers", "Storage", "Performance", "Utilities"]', QML)
        self.assertNotIn('"Plugins"', QML)
        self.assertNotIn('"Lulu"', QML)
        self.assertIn('request("/settings?category=System"', QML)
        self.assertIn('navigationText', settings_page)
        self.assertIn('root.expandedShellX + root.contentInset', settings_page)
        card_surface = (ROOT / "ui" / "MudosCardSurface.qml").read_text()
        self.assertIn('transmission: root.themeOptics.transmission', card_surface)
        self.assertIn('refractionPixels: root.themeOptics.refractionPixels || 80', card_surface)
        self.assertIn('focusedCardSurface', card_surface)
        self.assertIn('while (dependencyItem)', card_surface)
        self.assertIn('sourceItem.mapToItem', card_surface)
        self.assertIn('selectionScale: 1.01', settings_page)
        self.assertIn('root.verticalScaleInset', settings_page)
        self.assertIn('horizontalScaleInset', settings_page)
        self.assertIn('function ensureSelectedVisible()', settings_page)
        self.assertIn('onSelectedIndexChanged: ensureSelectedVisible()', settings_page)
        self.assertIn('transformOrigin: Item.Center', settings_page)

    def test_settings_uses_unified_two_panel_host_without_category_rail(self) -> None:
        shell = (ROOT / "ui" / "ConsoleShell.qml").read_text()
        settings_space = (ROOT / "ui" / "SettingsSpace.qml").read_text()
        catalog = (ROOT / "ui" / "MudosAssetCatalog.js").read_text()
        self.assertIn('property var systemHomeCards: ["Settings", "Utilities", "Desktop Mode"]', shell)
        self.assertIn('categories: root.systemHomeCards', shell)
        self.assertIn('MudosAssetCatalog.settingsCategories(systemCategories)', shell)
        self.assertIn('function settingsCategories(systemCategories)', catalog)
        self.assertIn('component: pages[label] || "systemSpace"', catalog)
        for category in ("Network", "Bluetooth", "Display", "Audio", "Controllers", "Storage", "Performance", "System"):
            self.assertIn('"' + category + '"', catalog)
        self.assertIn('property string activePanel: "categories"', settings_space)
        self.assertIn('function enterContent()', settings_space)
        self.assertIn('function enterCategories()', settings_space)
        self.assertIn('border.width: root.activePanel === "categories"', settings_space)
        self.assertIn('border.width: root.activePanel === "content"', settings_space)
        self.assertIn('contentHost', shell)
        self.assertIn('settingsPanelFocus = "categories"', shell)
        self.assertIn('settingsPanelFocus = "content"', shell)
        self.assertIn('parent: settingsSpace.contentHost', shell)
        self.assertIn('|| root.systemCategories[root.systemCategoryIndex] === "Performance")', shell)
        self.assertIn('root.systemCategories[root.systemCategoryIndex] === "System"', shell)
        self.assertIn('embedded: true', shell)
        self.assertIn('root.settingsCategoryModel.findIndex', shell)
        self.assertIn('onOperationRequested: root.networkOperation(action, ssid, password)', shell)
        self.assertIn('onOperationRequested: root.audioOperation(action, deviceId, volume, inputDevice, muted)', shell)
        self.assertIn('onOperationRequested: root.storageOperation(action, deviceId, kind)', shell)
        self.assertIn('onApplyRequested: root.applyDisplay(output, width, height, refresh)', shell)
        self.assertIn('onOperationRequested: root.controllerOperation(action, controllerId, player)', shell)
        back = shell.split("function back()", 1)[1].split("NumberAnimation {", 1)[0]
        self.assertLess(back.index("storageSettingsRef.back()"),
                        back.index('console.log("SETTINGS_PAGE_CLOSE"'))
        self.assertIn('space = "home"', back)
        # SettingsSpace intentionally has no Library category tape/rail or
        # page-up/page-down category handlers; its list is authoritative.
        self.assertNotIn('categoryRail', settings_space)
        self.assertNotIn('PageUp', settings_space)
        self.assertNotIn('PageDown', settings_space)
        self.assertIn('y: root.expandedShellY + (root.embedded ? 12 : 110)',
                      (ROOT / "ui" / "MudosSettingsPage.qml").read_text())
        self.assertIn('root.embedded && rowDelegate.index === root.selectedIndex',
                      (ROOT / "ui" / "MudosSettingsPage.qml").read_text())

    def test_settings_back_returns_directly_home_without_system_landing(self) -> None:
        self.assertNotIn('systemLandingHome', QML)
        self.assertNotIn('property bool systemLanding', QML)
        back = QML.split('function back()', 1)[1].split('NumberAnimation {', 1)[0]
        self.assertIn('space = "home"', back)
        settings_back = back.split('console.log("SETTINGS_PAGE_CLOSE"', 1)[1]
        self.assertIn('beginSystemExit()', settings_back)
        self.assertNotIn('settingsPanelFocus === "content"', settings_back)
        self.assertIn('root.space = "home"', QML[QML.index('id: systemTransitionAnimation'):])

    def test_settings_and_utilities_have_glass_and_system_transitions(self) -> None:
        settings = (ROOT / "ui" / "SettingsSpace.qml").read_text()
        utilities = (ROOT / "ui" / "UtilitiesHome.qml").read_text()
        self.assertIn('objectName: "settingsGlassSubstrate"', settings)
        self.assertNotIn('MudosCardSurface {', settings)
        self.assertIn('objectName: "utilitiesGlassSubstrate"', utilities)
        self.assertIn('canonicalTexture: root.canonicalTexture', utilities)
        self.assertIn('function beginSystemEntry()', QML)
        self.assertIn('function beginSystemExit()', QML)
        self.assertIn('systemTransitionAnimation.restart()', QML)
        self.assertIn('themeMotion.duration("intro", 360)', QML)

    def test_default_visual_baseline_has_shared_geometry_and_single_glass_roots(self) -> None:
        shell = (ROOT / "ui" / "ConsoleShell.qml").read_text()
        settings = (ROOT / "ui" / "SettingsSpace.qml").read_text()
        utilities = (ROOT / "ui" / "UtilitiesHome.qml").read_text()
        downloads = (ROOT / "ui" / "DownloadsHome.qml").read_text()
        empty = (ROOT / "ui" / "MudosEmptyState.qml").read_text()
        palette = (ROOT / "ui" / "LuluPalette.qml").read_text()
        self.assertIn('property real expandedContentY', shell)
        self.assertIn('property real expandedContentBottom', shell)
        self.assertIn('expandedGeometry.surfaceTopExtension', shell)
        self.assertIn('readonly property rect expandedContentBounds', shell)
        self.assertIn('root.expandedSurfaceY', shell)
        self.assertNotIn('expandedStatusReserve', shell)
        self.assertNotIn('libraryCategoryRightSafeInset', shell)
        self.assertNotIn('categoryTapeRightInset', shell)
        self.assertIn('readonly property real expandedTitleX', shell)
        self.assertIn('readonly property real expandedSurfaceY', shell)
        self.assertIn('readonly property real expandedSurfaceBottom', shell)
        self.assertIn('titleX: root.expandedTitleX', shell)
        self.assertIn('titleY: root.expandedTitleY', shell)
        self.assertIn('fullscreenY: root.expandedSurfaceY', shell)
        self.assertIn('expandedContentY: root.expandedContentY', shell)
        self.assertIn('Math.max(\n        design(72), presentationCoordinator.motionBlurMaxPixels)', shell)
        self.assertIn('width: parent.width + root.recentHorizontalOverscan', shell)
        self.assertIn('objectName: "settingsGlassSubstrate"', settings)
        self.assertEqual(settings.count('MudosPanelSurface {'), 1)
        self.assertEqual(utilities.count('MudosPanelSurface {'), 1)
        self.assertEqual(downloads.count('MudosPanelSurface {'), 1)
        self.assertIn('MudosIcon {', empty)
        self.assertIn('MudosAssetCatalog.icon(root.name)', (ROOT / "ui" / "MudosIcon.qml").read_text())
        for structural in ('glassTint', 'glassBorder', 'backdrop', 'cardSurface',
                           'focusedCardSurface', 'artworkSurface', 'librarySurface',
                           'libraryCardSurface', 'libraryBorder', 'selectionSurface'):
            self.assertIn('property color ' + structural, palette)
        self.assertNotIn('#1d2a49', palette)
        self.assertNotIn('#14213b', palette)

    def test_recent_blur_capture_uses_live_delegate_union_without_changing_layout_bounds(self) -> None:
        recent = (ROOT / "ui" / "RecentHome.qml").read_text()
        capture = (ROOT / "ui" / "RecentCaptureEnvelope.js").read_text()
        self.assertIn('readonly property real rowRightEdge', recent)
        self.assertIn('readonly property var captureRowEnvelope', recent)
        self.assertIn('RecentCaptureEnvelope.union(', recent)
        self.assertIn('card.mapToItem(recentRow, card.width, card.height)', recent)
        self.assertIn('captureRowRightEdge - recentHome.captureRowLeftEdge', recent)
        self.assertIn('sourceRect: Qt.rect(recentHome.captureRowLeftEdge', recent)
        self.assertIn('var itemRight = itemLeft + Number(item.width)', capture)
        self.assertIn('target: recentHome', recent)
        test = (ROOT / "tests" / "qml" / "tst_recent_capture_envelope.qml").read_text()
        self.assertIn('test_retargetCaptureContainsMovingRightmostCardAcrossTransition', test)
        self.assertIn('sample <= 4', test)
        self.assertIn('startX[4] + startWidth[4] > targetRight', test)

    def test_shared_selection_surface_is_used_for_utilities_and_settings_rows(self) -> None:
        palette = (ROOT / "ui" / "LuluPalette.qml").read_text()
        settings = (ROOT / "ui" / "SettingsSpace.qml").read_text()
        utility = (ROOT / "ui" / "UtilitiesHome.qml").read_text()
        embedded = (ROOT / "ui" / "MudosSettingsPage.qml").read_text()
        self.assertIn('property color selectionSurface:', palette)
        self.assertIn('root.luluPalette.selectionSurface', settings)
        self.assertIn('root.luluPalette.selectionSurface', utility)
        self.assertIn('root.luluPalette.selectionSurface', embedded)
        self.assertIn('root.luluPalette.focusIndicator', settings)
        self.assertIn('root.luluPalette.focusIndicator', utility)

        for page_name in (
                "SystemSpace.qml", "InternetSettings.qml", "StorageSettings.qml",
                "DisplaySettings.qml", "AudioSettings.qml", "ControllerSettings.qml"):
            page = (ROOT / "ui" / page_name).read_text()
            self.assertIn("MudosSettingsPage {", page)
            self.assertNotIn("delegate: Rectangle", page)

    def test_controller_navigation_all_is_default_and_shell_accepts_all_gamepads(self) -> None:
        settings = (ROOT / "ui" / "ControllerSettings.qml").read_text()
        native = (ROOT / "native" / "lulu-shell.cpp").read_text()
        registry = (ROOT / "src" / "lulu" / "controllerd.py").read_text()
        self.assertIn('label: "All"', settings)
        self.assertIn('navigation_mode === "all"', settings)
        self.assertIn('self.navigation_mode = "all"', registry)
        self.assertIn('navigationAll_', native)
        self.assertIn('SDL_OpenGamepad(ids[index])', native)
        self.assertIn('if (!navigationAll_ && (!gamepad_', native)

    def test_card_art_uses_global_nerd_font_fallback_and_explicit_store_glyphs(self) -> None:
        catalog = (ROOT / "ui" / "MudosAssetCatalog.js").read_text()
        game_card = (ROOT / "ui" / "GameCard.qml").read_text()
        store = (ROOT / "ui" / "StoreHome.qml").read_text()
        self.assertIn("fallback: nerdGlyph(0xF420)", catalog)
        self.assertNotIn("questarr", catalog.casefold())
        self.assertIn("steam: nerdGlyph(0xF1B6)", catalog)
        self.assertIn("addStore: nerdGlyph(0xF055)", catalog)
        self.assertIn('MudosAssetCatalog.icon("fallback")', game_card)
        self.assertIn("artworkLoadFailed", game_card)
        self.assertIn("MudosAssetCatalog.storeIcon(modelData.id, modelData.kind)", store)
        self.assertIn('return icon("fallback")', catalog)

    def test_navigation_cards_share_the_all_games_surface(self) -> None:
        navigation_card = (ROOT / "ui" / "NavigationCard.qml").read_text()
        navigation_surface = (ROOT / "ui" / "NavigationCardSurface.qml").read_text()
        store = (ROOT / "ui" / "StoreHome.qml").read_text()
        system = (ROOT / "ui" / "SystemHome.qml").read_text()
        library_surface = (ROOT / "ui" / "LibrarySpatialSurface.qml").read_text()
        self.assertIn("NavigationCardSurface {", navigation_card)
        self.assertIn("transmission: 1", navigation_surface)
        self.assertIn("bulgeStrength: 100", navigation_surface)
        self.assertIn("NavigationCard {", store)
        self.assertIn("NavigationCard {", system)
        self.assertIn("NavigationCardSurface {", library_surface)
        self.assertIn("selectionProgress", system)
        self.assertIn("function railX(relativeIndex)", system)
        self.assertIn("presentationStartX", system)
        self.assertIn("captureSelection()", system)
        self.assertIn("onActivated: root.openRequested(index)", system)
        self.assertIn("property url artworkSource", navigation_card)
        self.assertIn('property string artworkRole: "icon"', navigation_card)
        self.assertIn("artworkRole: root.artworkRole", navigation_card)
        self.assertIn('MudosAssetCatalog.storeIcon(modelData.id, modelData.kind)', store)
        self.assertIn('artworkRole: "icon"', store)
        self.assertIn("function categoryArtwork(category)", (ROOT / "ui" / "LibraryHome.qml").read_text())
        self.assertIn("MudosAssetCatalog.systemIcon(modelData)", system)
        self.assertNotIn("border.width", (ROOT / "ui" / "NavigationCard.qml").read_text())
        self.assertNotIn("anchors.margins: -8", (ROOT / "ui" / "NavigationCard.qml").read_text())
        self.assertIn("onOpenRequested: root.openSystemCategory(index)", QML)
        self.assertIn("function openSystemCategory(index)", QML)
        self.assertNotIn("root.activate()\n            }", QML)

    def test_home_store_rail_reuses_selection_motion_and_store_options(self) -> None:
        store = (ROOT / "ui" / "StoreHome.qml").read_text()
        shell = (ROOT / "ui" / "ConsoleShell.qml").read_text()
        options = (ROOT / "ui" / "StoreOptions.qml").read_text()
        self.assertIn("homeSelectionStart", store)
        self.assertIn("homePresentationStartX", store)
        self.assertIn("captureHomeSelection()", store)
        self.assertIn("homeSelectionMotionActive", store)
        self.assertIn("canonicalMappingDependency", store)
        self.assertIn('import "MudosAssetCatalog.js" as MudosAssetCatalog', store)
        self.assertIn("onHomeStoreOptionsRequested", shell)
        self.assertIn('label: "Store Options"', shell)
        self.assertIn("root.selectedHomeStore() !== null", shell)
        self.assertIn('readonly property var entries: ["Change Name", "Update URL", "Remove Store"]', options)
        self.assertEqual(store.count("Component.onCompleted:"), 1)
        self.assertIn("rebuildDisplayCards()\n        captureHomeSelection()", store)
        self.assertIn("readonly property real targetX: root.homeRailX(index - root.homeSelectedIndex)", store)
        self.assertNotIn("(root.width - root.cardWidth) / 2", store)

    def test_browser_compat_uses_native_scroll_tab_and_webengine_zoom(self) -> None:
        browser = (ROOT / "ui" / "MudosBrowser.qml").read_text()
        compat = (ROOT / "config" / "inputplumber" / "profiles" / "compat.yaml").read_text()
        native = (ROOT / "native" / "lulu-shell.cpp").read_text()
        self.assertIn("property real pageZoom: 1.25", browser)
        self.assertIn("zoomFactor: root.pageZoom", browser)
        self.assertIn("RightStick", compat)
        self.assertIn("button: WheelUp", compat)
        self.assertIn("button: WheelDown", compat)
        self.assertIn("button: WheelLeft", compat)
        self.assertIn("button: WheelRight", compat)
        self.assertIn("- keyboard: KeyLeftShift\n      - keyboard: KeyTab", compat)
        self.assertIn("updateBookmarkName", native)
        self.assertIn("updateBookmarkUrl", native)

    def test_store_consumes_normalized_availability_without_install_behavior(self) -> None:
        store = (ROOT / "ui" / "StoreHome.qml").read_text()
        bridge = (ROOT / "scripts" / "console-ui-bridge.py").read_text()
        self.assertIn('request.open("GET", apiUrl + "/available")', QML)
        self.assertIn('property var storeAvailableGames: []', QML)
        self.assertIn('property var storeCategories:', QML)
        self.assertIn('availability_state !== "available"', QML)
        self.assertIn('install_state !== "available"', QML)
        self.assertIn('storeCategories = InstallableProjection.categories(games)', QML)
        self.assertIn('emptyText: root.errorMessage !== "" ? root.errorMessage : "No games ready to install"', store)
        self.assertIn('canonicalGames: root.displayGames', store)
        self.assertNotIn('specialCardId: "steam-store"', store)
        self.assertIn('actionLabel: "Install"', store)
        self.assertIn('signal installGameRequested(var game)', store)
        self.assertIn('installGameRequested(selectedGame)', store)
        self.assertIn('providerId.match(/^[1-9][0-9]*$/)', store)
        self.assertIn('CONTROLLER_ACTIVATE', QML)
        self.assertIn('root.space === "store" ? "Download"', QML)
        library_space = (ROOT / "ui" / "LibrarySpace.qml").read_text()
        self.assertIn("browseCategories: root.categories", store)
        self.assertIn("browseCategoryIndex: root.categoryIndex", store)
        self.assertIn("browseCategoryRequested(externalIndex)", library_space)
        self.assertNotIn("dimensionKey: root.categoryIndex", store)
        self.assertIn('MudosGlassItem {', (ROOT / "ui" / "GameCard.qml").read_text())
        self.assertNotIn('RecentHome {', store)
        self.assertIn('LibrarySpace {', store)
        self.assertIn('function moveVertical(delta)', store)
        self.assertIn('availableGames.length + categories.length + displayCategoryIndex >= 0', store)
        self.assertNotIn('provider: "steam-store"', store)
        self.assertNotIn('result.push({game_id: "steam-store"', store)
        self.assertIn('installGameRequested(game)', store)
        self.assertIn('game.provider === "steam"', store)
        self.assertIn('onInstallGameRequested: root.installGame(game)', QML)
        self.assertIn('onHomeDownloadRequested: root.openInstallableSurface()', QML)
        self.assertIn('function openInstallableSurface()', QML)
        self.assertNotIn('onHomeDownloadRequested: root.activate()', QML)
        self.assertIn('request("/install/"', QML)
        self.assertIn('call_submit_job', bridge)
        self.assertNotIn('steam://install', QML + store)
        self.assertIn('game.provider === "romm"', store)
        self.assertIn('call_list_available_games', bridge)
        self.assertIn('get("provider", [""])', bridge)
        recent = ((ROOT / "ui" / "RecentHome.qml").read_text()
                  + (ROOT / "ui" / "RecentCardPresentation.qml").read_text())
        self.assertIn('actionLabel: root.install_state === "available"', recent)
        self.assertIn('text: card.actionLabel', (ROOT / "ui" / "GameCard.qml").read_text())

    def test_non_game_portrait_artwork_assets_are_replaceable(self) -> None:
        artwork = ROOT / "ui" / "artwork"
        expected = {
            "platform-all.svg", "platform-pc.png", "store.png",
            "platform-nes.png", "platform-snes.png", "platform-genesis.png",
            "platform-gb.png", "platform-gbc.png", "platform-gba.png",
            "platform-nds.png", "platform-gamecube.png", "platform-wii.png",
            "platform-switch.png", "platform-ps1.png", "platform-ps2.png",
            "platform-ps3.png",
            "README.md",
        }
        self.assertTrue(expected.issubset({path.name for path in artwork.iterdir()}))
        self.assertTrue((artwork / "navigation").is_dir())
        self.assertTrue((artwork / "glyphs" / "metadata").is_dir())
        for path in artwork.rglob("*"):
            if not path.is_file():
                continue
            self.assertGreater(path.stat().st_size, 0)

    def test_home_uses_one_fixed_content_stage_and_compact_library_object(self) -> None:
        self.assertIn("readonly property real headingCardGap: design(21)", QML)
        self.assertIn("readonly property real homeHintTopY: height - design(45)", QML)
        self.assertIn("homeContentOriginY: homeHintTopY - acceptedRecentCardHeight - headingCardGap", QML)
        self.assertIn("selectedDomainY: homeActiveContentOriginY - homeHeadingCardClearance", QML)
        self.assertIn("titleHeight * 0.5)", QML)
        self.assertIn("acceptedRecentCardHeight", QML)
        self.assertIn("y: root.titleRailChildY(index)", QML)
        self.assertIn("function domainOffset(index)", QML)
        self.assertIn("y: root.homeActiveContentOriginY", QML)
        self.assertIn("root.homeCategoryTransitioning", QML)
        self.assertIn("homeCategoryTarget === 2", QML)
        self.assertIn("homeCategoryFrom === 2", QML)
        self.assertIn("homeCategoryTarget === 3", QML)
        self.assertIn("homeCategoryRevealHeight(index)", QML)
        self.assertIn("var titleHeight = titleItem ? titleItem.height : activeHeadingHeight", QML)
        self.assertIn("desiredCategoryIndex", QML)
        self.assertIn("function startNextHomeCategoryHop(chained)", QML)
        self.assertIn("homeCategoryHopDuration", QML)
        self.assertIn('homeCategoryHopDuration = themeMotion.duration("navigation", chained ? 100 : 250)', QML)
        self.assertIn("root.titleRailY = root.titleRailTargetY", QML)
        self.assertIn("duration: root.homeCategoryHopDuration", QML)
        self.assertIn("if (homeCategoryAnimation.running)", QML)
        self.assertIn("id: libraryReveal", QML)
        self.assertIn('surfaceVisible: root.space === "library" || root.space === "store"', QML)
        self.assertIn('|| root.libraryTransitioning', QML)
        self.assertIn("x: -root.homeContentRailX", QML)
        self.assertIn("id: homeCardViewport", QML)
        self.assertIn("id: systemReveal\n                    x: -root.homeContentRailX", QML)
        self.assertIn("id: systemHomeRail\n                        x: root.homeContentRailX", QML)
        self.assertIn("id: homeCardViewport\n                x: 0", QML)
        self.assertIn("id: homeContent\n                x: root.homeContentRailX", QML)
        self.assertIn("height: root.homeBottomBandCenterY - root.homeActiveContentOriginY", QML)
        self.assertIn("clip: true", QML)
        self.assertIn("opacity: 1", QML)
        self.assertNotIn("homeCategoryOpacityProgress", QML)
        self.assertNotIn("homeCategoryOpacityAnimation", QML)
        self.assertNotIn("root.domainIndex * 40", QML)
        library_home = (ROOT / "ui" / "LibraryHome.qml").read_text()
        self.assertIn('"PC Games", "scope": "pc"', library_home)
        self.assertIn("NavigationCard", library_home)
        self.assertIn("presentationStartX", library_home)
        self.assertIn("function railX(relativeIndex)", library_home)
        self.assertIn("targetX: libraryHome.railX(index - libraryHome.selectedIndex)", library_home)
        self.assertIn("moveLibraryLanding", QML)
        self.assertIn("selectedIndex: root.libraryHomeIndex", QML)
        self.assertIn("property real cardHeight", library_home)
        self.assertIn("height: libraryHome.cardHeight", library_home)
        self.assertIn("width: libraryHome.compactCardWidth", library_home)
        self.assertIn('modelData.scope === "all"', library_home)
        catalog = (ROOT / "ui" / "MudosAssetCatalog.js").read_text()
        self.assertIn('nes: ["platforms/romm/nes.svg", "raster"]', catalog)
        self.assertIn('all: ["platforms/romm/default.ico", "raster"]', catalog)
        for asset in ("nes.svg", "snes.svg", "genesis.svg", "gb.svg", "gbc.svg",
                      "gba.svg", "nds.svg", "ngc.svg", "wii.svg", "switch.svg",
                      "psx.svg", "ps2.svg", "ps3.svg", "default.ico"):
            self.assertTrue((ROOT / "ui/artwork/platforms/romm" / asset).is_file())
        self.assertIn('artworkRole: modelData.scope === "all" ? "icon"', library_home)
        self.assertIn("canonicalCoordinateRoot", library_home)
        self.assertNotIn("allGamesSceneOrigin", library_home)
        self.assertNotIn("gameCount", library_home)
        self.assertNotIn("selectedGame", library_home)

    def test_cards_preserve_portrait_artwork_and_library_density(self) -> None:
        game_card = (ROOT / "ui" / "GameCard.qml").read_text()
        shell = (ROOT / "ui" / "ConsoleShell.qml").read_text()
        self.assertIn("visible: card.focalChromeOpacity > 0", game_card)
        library_space = (ROOT / "ui" / "LibrarySpace.qml").read_text()
        self.assertIn("compactArtworkWidth * 1.5", game_card)
        self.assertIn("compactArtworkWidth", game_card)
        self.assertIn("compactArtworkHeight", game_card)
        self.assertIn("Image.PreserveAspectFit", game_card)
        self.assertIn("presentationProgress < 1", game_card)
        self.assertIn("property real focusBrightness: 1", game_card)
        self.assertIn("opacity: card.focused ? 1 : 0.84", game_card)
        self.assertIn("focusBrightness: root.focused ? 1 : 0.84", (ROOT / "ui" / "RecentCardPresentation.qml").read_text())
        self.assertIn("focusBrightness: root.selectedOpacityOwner ? 1 : 0.84", (ROOT / "ui" / "NavigationCard.qml").read_text())
        store_home = (ROOT / "ui" / "StoreHome.qml").read_text()
        self.assertIn("browseCategories: root.categories", store_home)
        self.assertIn("browseCategoryIndex: root.categoryIndex", store_home)
        self.assertIn("onBrowseCategoryRequested: root.categoryIndex = index", store_home)
        self.assertNotIn("collectionIndex", store_home)
        self.assertNotIn("collections:", store_home)
        self.assertNotIn("onCollectionChanged", store_home)
        self.assertNotIn("onCategoryContentHidden", store_home)
        dimensions_js = (ROOT / "ui" / "LibraryDimensions.js").read_text()
        self.assertIn('readonly property var libraryDimensions: LibraryDimensions.all', shell)
        for label, mode in (("Platform", "platform"), ("Provider", "provider"),
                            ("Game Mode", "game_mode"), ("Genre", "genre")):
            self.assertIn('{label: "%s", mode: "%s"}' % (label, mode), dimensions_js)
        self.assertIn('property string libraryDimension: "platform"', shell)
        setter = shell[shell.index("function setLibraryDimension(mode)"):
                       shell.index("function openLibraryDimension(mode)")]
        cycling = shell[shell.index("function moveLibraryCollection(delta)"):
                        shell.index("function moveStoreCategory(delta)")]
        self.assertIn("libraryDimension = mode", setter)
        self.assertIn("setLibraryDimension(adjacentLibraryDimension(delta))", cycling)
        self.assertIn("dimensionKey: root.libraryDimension", shell)
        self.assertIn("dimensionLabel: root.libraryDimensionLabel(root.libraryDimension)", shell)
        self.assertNotIn("browseCategory", shell[shell.index("id: librarySpace"):])
        self.assertIn("fullscreenHeight: root.expandedSurfaceHeight", shell)
        self.assertIn("fullscreenY: root.expandedSurfaceY", shell)
        self.assertIn("ListView {", library_space)
        self.assertIn("model: root.categoryTapeValues", library_space)
        self.assertIn("signal browseCategoryRequested(int index)", library_space)
        self.assertIn("property string dimensionKey", library_space)
        self.assertIn("readonly property string categoryMode: projectionState.dimensionKey", library_space)
        self.assertIn("horizontalAlignment: Text.AlignHCenter", game_card)
        self.assertIn("verticalAlignment: Text.AlignVCenter", game_card)
        self.assertIn("elide: Text.ElideRight", game_card)
        self.assertIn("font.weight: card.compact || card.compactEndpointWidth > 0 ? Font.Bold : Font.Normal", game_card)
        self.assertIn("card.compact ? 13 * 0.8 : 16", game_card)
        self.assertIn("layer.enabled: card.librarySurfaceMaterial", game_card)
        self.assertIn("shadowOpacity: 0.35", game_card)

    def test_recent_has_distinct_focal_and_compact_geometry(self) -> None:
        recent = ((ROOT / "ui" / "RecentHome.qml").read_text()
                  + (ROOT / "ui" / "RecentCardPresentation.qml").read_text())
        game_card = (ROOT / "ui" / "GameCard.qml").read_text()
        library_space = (ROOT / "ui" / "LibrarySpace.qml").read_text()
        shell = (ROOT / "ui" / "ConsoleShell.qml").read_text()
        artwork_shader = (ROOT / "ui" / "shaders" / "card-rounded.frag").read_text()
        self.assertIn("property real focalCardHeight", recent)
        self.assertIn("x: startX + (recentHome.railX(toRelativeIndex) - startX) * railProgress", recent)
        self.assertIn("focalChromeOpacity", recent)
        self.assertIn("startChrome", recent)
        self.assertIn("startCompactTitle", recent)
        self.assertIn('console.log("RECENT_RETARGET", "capture"', recent)
        self.assertIn('console.log("RECENT_RETARGET", "target"', recent)
        self.assertIn('themeMotion.duration("navigation", 500)', recent)
        self.assertIn('themeMotion.easing("navigation", "outQuint")', recent)
        self.assertIn('property: "transitionFadeProgress"', recent)
        self.assertIn("z: 2", game_card)
        self.assertIn("property real compactCardWidth", recent)
        self.assertIn("height: compactCardHeight", recent)
        self.assertIn("compactCardWidth + railGap", recent)
        self.assertIn("compactCardWidth: root.compactGameCardWidth", shell)
        self.assertIn("compactCardHeight: root.compactCardHeight", shell)
        self.assertIn("cardHeight: root.homeNavigationCardHeight", shell)
        self.assertIn("readonly property bool recentFocal", game_card)
        self.assertIn("property real compactTitleOpacity", game_card)
        self.assertIn("card.compactEndpointWidth > 0", game_card)
        self.assertIn('Qt.formatDateTime', game_card)
        self.assertIn('text: card.actionLabel || "Play"', game_card)
        self.assertIn('name: "play"', game_card)
        self.assertIn("MudosIcon {", game_card)
        self.assertIn("spacing: 8 * card.uiScale", game_card)
        self.assertIn("maximumLineCount: 2", game_card)
        self.assertIn("wrapMode: Text.WordWrap", game_card)
        self.assertIn("property real focalLayoutCardWidth: 0", game_card)
        self.assertIn("focalTitleLayoutWidth", game_card)
        self.assertIn("id: focalTitleLayoutMeasure", game_card)
        self.assertIn("focalLayoutCardWidth: root.focalCardWidth", recent)
        self.assertIn('property real artworkRadius: card.luluPalette.radius("media"', game_card)
        self.assertIn("card.mix(10 * uiScale, 18 * focalScale * uiScale", game_card)
        self.assertIn("property real artworkRadius", game_card)
        self.assertIn("cornerRadius: artworkFrame.artworkRadius / Math.min(width, height)", game_card)
        self.assertNotIn("diagnosticMode", game_card)
        self.assertNotIn("vec4(vec3(alpha), alpha)", artwork_shader)
        self.assertIn("property real artworkBorderAlpha: 0.15", game_card)
        self.assertIn("property vector2d artworkSize", game_card)
        self.assertIn("float pixelWidth = borderWidthPx / min(artworkSize.x, artworkSize.y)", artwork_shader)
        self.assertIn("float border = smoothstep", artwork_shader)
        self.assertIn("luluPalette.artworkSurface", game_card)
        self.assertIn('card.compact ? 13 * 0.8 : 16', game_card)
        self.assertIn("sourceItem: artworkSource", game_card)
        self.assertIn("hideSource: true", game_card)
        self.assertIn("sourceItem: artworkSource\n            hideSource: true\n            visible: false", game_card)
        self.assertIn("readonly property real focalMargin", game_card)
        self.assertIn("property real focalScale", game_card)
        self.assertIn('property string presentationState: "COMPACT"', game_card)
        self.assertIn('presentationState: game_id === recentHome.selectedGameId ? "FOCUSED" : "COMPACT"', recent)
        self.assertIn("property string selectedGameId", recent)
        self.assertIn('required property var modelData', library_space)
        self.assertIn('transitionState: root.libraryTransitionState', shell)
        self.assertIn('property string libraryTransitionState: "RESTING"', shell)
        self.assertIn("focalScale: 0.67", (ROOT / "ui" / "ConsoleShell.qml").read_text())
        self.assertIn("fragmentShader", game_card)
        self.assertIn("canonicalTexture", game_card)
        self.assertIn("transparentOutsideMask: card.nativeGlassTransparentOutsideMask", game_card)
        self.assertIn("transparentOutsideMask", (ROOT / "ui" / "NavigationCardSurface.qml").read_text())
        self.assertIn("MudosGlassItem", game_card)
        self.assertIn("backdrop: card.canonicalTexture", game_card)
        self.assertIn("canonicalCoordinateRoot", game_card)
        self.assertIn("card.mapToItem(canonicalCoordinateRoot, 0, 0)", game_card)
        self.assertIn("liveSceneCoordinates: true", recent)
        self.assertIn("opticsStage: root.presentationProgress > 0 ? 7 : -1", recent)
        self.assertIn("layoutDependency = card.x + card.y + card.width + card.height", game_card)
        self.assertIn("canonicalRect: card.nativePlayCanonicalRect", game_card)
        self.assertIn("readonly property real focalMargin", game_card)
        self.assertIn("focalMargin + artworkWidth + focalMargin", game_card)
        self.assertIn("readonly property var focalMetadataRows", game_card)
        self.assertNotIn('"Genres  "', game_card)
        self.assertNotIn('"Last Played  "', game_card)
        self.assertIn('GameMetadata.rows(card.game', game_card)
        game_metadata = (ROOT / "ui" / "GameMetadata.js").read_text()
        self.assertIn('var modes = game.game_modes', game_metadata)
        self.assertIn('"Local Multiplayer"', game_metadata)
        self.assertIn('"Online Multiplayer"', game_metadata)
        for semantic in ('genres: "genre"', 'lastPlayed: "clock"',
                         'gameModes: "gameMode"', 'onlineMultiplayer: "wifi"',
                         'platform: "platform"', 'provider: "plug"'):
            self.assertIn(semantic, game_metadata)
        self.assertIn('FocalMetadataRow {', game_card)
        self.assertIn('StatusGlyph {', (ROOT / "ui" / "FocalMetadataRow.qml").read_text())
        self.assertIn("focalMetadataGlyphColumnWidth", game_card)
        self.assertIn('focalMetadataGlyphColumnWidth: 18', game_card)
        self.assertNotIn('namespace: "metadata"', game_card)
        self.assertIn('"Total Playtime  " + formatPlaytime', game_metadata)
        self.assertNotIn("game.provider.toUpperCase()", game_card)

    def test_orbit_backdrop_uses_qsb_and_plain_fallback(self) -> None:
        backdrop = (ROOT / "ui" / "OrbitBackdrop.qml").read_text()
        shader_builder = (ROOT / "scripts" / "build-orbit-shader.sh").read_text()
        adapter = (ROOT / "scripts" / "build-orbit-qsb.py").read_text()
        self.assertIn("fragmentShader: root.themeShader", backdrop)
        self.assertIn("mudosTheme.wallpaperShader", backdrop)
        self.assertIn("color: luluPalette.backdrop", backdrop)
        self.assertIn("ShaderEffect.Compiled", backdrop)
        self.assertIn("--qt6", shader_builder)
        self.assertIn("wave.frag", shader_builder)
        for uniform in ("u_resolution", "u_origin", "u_canvas", "u_time", "u_brightness", "u_visibility", "u_primary", "u_secondary", "u_surface", "u_error"):
            self.assertIn(uniform, adapter)
        self.assertIn('replace("gl_FragColor", "fragColor")', adapter)

    def test_orbit_presentation_uses_coordinator_and_shared_canonical_texture(self) -> None:
        source = (ROOT / "ui" / "OrbitRenderSource.qml").read_text()
        coordinator = (ROOT / "ui" / "PresentationCoordinator.qml").read_text()
        shell = (ROOT / "ui" / "ConsoleShell.qml").read_text()
        self.assertIn("presentationCoordinator", source)
        self.assertIn("onVisibleChanged", shell)
        self.assertIn("orbitShaderTime", source)
        self.assertIn("orbitVisibility", source)
        self.assertNotIn("NumberAnimation on shaderTime", source)
        self.assertIn("orbitBaseTimeAnimation", coordinator)
        self.assertIn("orbitIntroCorrection", coordinator)
        self.assertIn("orbitExitCorrection", coordinator)
        self.assertIn('id: orbitTexture', shell)
        self.assertIn('sourceItem: orbitRenderSource', shell)
        self.assertIn('texture: orbitTexture', shell)
        self.assertIn('canonicalTexture: orbitTexture', shell)
        self.assertIn('canonicalCoordinateRoot: orbitRenderSource', shell)

    def test_startup_intro_waits_for_library_readiness_and_coordinator(self) -> None:
        shell = (ROOT / "ui" / "ConsoleShell.qml").read_text()
        coordinator = (ROOT / "ui" / "PresentationCoordinator.qml").read_text()
        self.assertIn('property string startupLifecycle: "BOOTSTRAPPING"', shell)
        self.assertIn('startupLifecycle = "RECONCILING_LIBRARY"', shell)
        self.assertIn('request("/startup-ready"', shell)
        self.assertIn('startupLifecycle = "READY_FOR_INTRO"', shell)
        self.assertIn('startupLifecycle = "PLAYING_INTRO"', shell)
        self.assertIn('startupLifecycle = "HOME"', shell)
        self.assertIn('!presentationCoordinator.ready', shell)
        self.assertIn('property bool ready: false', coordinator)
        self.assertIn('Component.onCompleted: ready = true', coordinator)
        self.assertNotIn('root.presentationCoordinator.contentState', shell)

    def test_controller_x_routes_to_shared_game_options_action(self) -> None:
        native_shell = (ROOT / "native" / "lulu-shell.cpp").read_text()
        self.assertIn('{SDL_GAMEPAD_BUTTON_WEST, "options"}', native_shell)
        self.assertIn('{SDL_GAMEPAD_BUTTON_EAST, "back"}', native_shell)
        self.assertIn('{SDL_GAMEPAD_BUTTON_NORTH, "downloads"}', native_shell)
        self.assertIn('{"options", "openSelectedGameOptions"}', native_shell)
        self.assertIn("function openSelectedGameOptions()", QML)
        self.assertIn("openGameOptions(selectedGameForOptions)", QML)

    def test_controller_west_dispatches_installable_search_through_shared_action(self) -> None:
        native_shell = (ROOT / "native" / "lulu-shell.cpp").read_text()
        self.assertIn('{SDL_GAMEPAD_BUTTON_WEST, "options"}', native_shell)
        self.assertIn('{"options", "openSelectedGameOptions"}', native_shell)

        action = QML.split("function openSelectedGameOptions() {", 1)[1].split(
            "\n    function ", 1
        )[0]
        self.assertRegex(action, r'if \(space === "store"\)\s*\{\s*beginLutrisSearch\(\)')
        self.assertLess(action.index('space === "store"'), action.index("selectedGameForOptions"))

        key_action = QML.split("if (event.key === Qt.Key_X) {", 1)[1].split(
            "event.accepted = true", 1
        )[0]
        self.assertIn("root.openSelectedGameOptions()", key_action)
        self.assertNotIn('root.space === "store"', key_action)

    def test_lutris_flows_use_shell_http_api_base_url(self) -> None:
        recipe = (ROOT / "ui" / "LutrisRecipeInstall.qml").read_text()
        add_game = (ROOT / "ui" / "LutrisAddGame.qml").read_text()
        picker = (ROOT / "ui" / "MudosFilePicker.qml").read_text()

        self.assertIn('apiUrl: root.apiUrl', QML)
        self.assertIn('xhr.open("GET", root.apiUrl + path)', recipe)
        self.assertIn('xhr.open("POST", root.apiUrl + "/lutris/install-recipe")', recipe)
        self.assertIn('apiUrl: root.apiUrl', recipe)
        self.assertIn('xhr.open("GET", root.apiUrl + "/lutris/local-candidates")', add_game)
        self.assertIn('xhr.open("POST", root.apiUrl + "/lutris/register-local")', add_game)
        self.assertIn('xhr.open("GET", root.apiUrl + "/files?path="', picker)
        self.assertIn('requirements[index].label || requirements[index].filename', recipe)
        self.assertIn('requirement.label || requirement.filename', recipe)

    def test_lutris_install_action_is_a_dedicated_visible_row_after_required_files(self) -> None:
        recipe = (ROOT / "ui" / "LutrisRecipeInstall.qml").read_text()
        self.assertIn('rows = requirements.slice(0)', recipe)
        self.assertIn('var lastIndex = flowStage === 2 ? requirements.length : rows.length - 1', recipe)
        self.assertIn('if (selectedIndex === requirements.length) submitInstall()', recipe)
        self.assertIn('visible: root.flowStage === 2', recipe)
        self.assertIn('text: "Install"', recipe)
        self.assertNotIn('rows.push({installAction:', recipe)

    def test_visible_lutris_window_owns_native_controller_actions(self) -> None:
        shell = (ROOT / "ui" / "ConsoleShell.qml").read_text()

        def body(name):
            return shell.split(f"function {name}(", 1)[1].split(
                "\n    function ", 1
            )[0]

        activate = body("activate")
        back = body("back")
        options = body("openSelectedGameOptions")
        downloads = body("openDownloadsGlobal")
        self.assertLess(activate.index("if (lutrisRecipeInstall.visible)"),
                        activate.index('if (space === "store")'))
        self.assertIn("lutrisRecipeInstall.activate()", activate)
        self.assertIn("lutrisAddGame.activate()", activate)
        self.assertIn("lutrisRecipeInstall.back()", back)
        self.assertIn("lutrisAddGame.back()", back)
        self.assertIn("if (lutrisRecipeInstall.visible || lutrisAddGame.visible)", options)
        self.assertIn("if (lutrisRecipeInstall.visible || lutrisAddGame.visible)", downloads)
        self.assertIn("if (lutrisRecipeInstall.visible || lutrisAddGame.visible) return",
                      body("controllerLeft"))
        self.assertIn("if (lutrisRecipeInstall.visible || lutrisAddGame.visible) return",
                      body("controllerRight"))
        self.assertIn("if (lutrisRecipeInstall.visible || lutrisAddGame.visible)",
                      body("controllerShoulder"))

    def test_navigation_uses_normalized_controller_target_indices(self) -> None:
        native_shell = (ROOT / "native" / "lulu-shell.cpp").read_text()
        self.assertIn('value.value(QStringLiteral("sdl_index"))', native_shell)
        self.assertIn("navigationSdlIndices_", native_shell)
        self.assertIn("allGamepads_.contains(event.gbutton.which)", native_shell)
        self.assertNotIn("std::min(count, navigationControllerCount_)", native_shell)
        strip = (ROOT / "ui" / "SystemStatusStrip.qml").read_text()
        self.assertIn('controller.identity || "player:" + controller.index', strip)

    def test_guide_dbus_relays_follow_sessiond_connected_composites(self) -> None:
        native_shell = (ROOT / "native" / "lulu-shell.cpp").read_text()
        self.assertIn("controllerCompositePaths_.append(iterator.key())", native_shell)
        self.assertIn("for (const QString &compositePath : controllerCompositePaths_)", native_shell)
        self.assertIn("Sessiond's connected controller inventory is authoritative", native_shell)

    def test_home_system_cards_use_home_card_dimensions(self) -> None:
        home_system = QML.split('id: systemHomeRail', 1)[1].split(
            'Component.onCompleted: root.systemHomeRailRef', 1)[0]
        self.assertIn('cardWidth: root.homeNavigationCardWidth', home_system)
        self.assertIn('cardHeight: root.homeNavigationCardHeight', home_system)

    def test_back_from_utilities_returns_to_main_home_like_other_system_pages(self) -> None:
        back = QML.split("function back() {", 1)[1].split("\n    function ", 1)[0]
        self.assertNotIn('systemCategories[systemCategoryIndex] === "Utilities"', back)
        self.assertIn('space = "home"', back)

    def test_game_options_owns_confirm_and_ignores_reopen(self) -> None:
        native_shell = (ROOT / "native" / "lulu-shell.cpp").read_text()
        self.assertIn('{SDL_GAMEPAD_BUTTON_SOUTH, "confirm"}', native_shell)
        self.assertNotIn("nintendoLayout", native_shell)
        self.assertIn("if (gameOptionsOpen) {\n            activateGameOptions()", QML)
        self.assertIn("if (gameOptionsOpen)\n            return\n        if (selectedGameForOptions)", QML)
        self.assertIn('if (gameOptionsOpen) {\n            if (gameOptionsTextEntryActive)', QML)
        self.assertIn('closeGameOptions()', QML)

    def test_shell_profile_routes_semantic_events_to_qt_keys(self) -> None:
        for button, key in (
            ("DPadUp", "KeyUp"),
            ("DPadDown", "KeyDown"),
            ("DPadLeft", "KeyLeft"),
            ("DPadRight", "KeyRight"),
            ("South", "KeyEnter"),
            ("East", "KeyBackspace"),
            ("LeftBumper", "KeyPageUp"),
            ("RightBumper", "KeyPageDown"),
        ):
            self.assertIn(f"button: {button}", SHELL_PROFILE)
            self.assertIn(f"keyboard: {key}", SHELL_PROFILE)
        self.assertIn("button: North", SHELL_PROFILE)
        self.assertIn("keyboard: KeyX", SHELL_PROFILE)

    def test_game_options_exposes_only_four_shallow_actions_and_subflows(self) -> None:
        options = (ROOT / "ui" / "GameOptions.qml").read_text()
        self.assertIn('"Change Artwork"', options)
        self.assertIn('"Change Mapping"', options)
        self.assertIn('"Change Title"', options)
        self.assertIn('"Uninstall"', options)
        self.assertIn('uninstallInProgress ? "Uninstalling…" : "Uninstall"', options)
        self.assertIn('uninstallInProgress: root.uninstallCapability.in_progress === true', QML)
        self.assertNotIn('"Restore Automatic Artwork"', options)
        self.assertNotIn("Edit Metadata", options)
        self.assertNotIn("Change Match", options)
        self.assertIn("/metadata/search?game_id=", QML)
        self.assertNotIn("/artwork/files", QML)
        self.assertIn("property var artworkCandidates: []", QML)
        self.assertIn("function loadGameArtworkCandidates(role)", QML)
        self.assertIn("/artwork/candidates?game_id=", QML)
        self.assertNotIn("Window {", options)
        self.assertIn("function back()", QML)

    def test_recent_game_modes_are_optional_card_metadata(self) -> None:
        game_card = (ROOT / "ui" / "GameCard.qml").read_text()
        metadata = (ROOT / "ui" / "GameMetadata.js").read_text()
        presentation = (ROOT / "ui" / "RecentCardPresentation.qml").read_text()
        self.assertIn("required property var game_modes", presentation)
        self.assertIn("var modes = game.game_modes", metadata)
        self.assertIn('join(" · ")', metadata)
        self.assertIn("if (modes.length)", metadata)
        self.assertNotIn("game_modes.length", presentation)
        for mode in ("Single player", "Multiplayer", "Split screen"):
            self.assertNotIn(mode, game_card)

    def test_recent_card_projection_preserves_library_metadata(self) -> None:
        presentation = (ROOT / "ui" / "RecentCardPresentation.qml").read_text()
        game_card = (ROOT / "ui" / "GameCard.qml").read_text()
        catalogue_header = (ROOT / "native" / "catalogue-model.h").read_text()
        for field in ("release_date", "release_year", "local_multiplayer",
                      "online_multiplayer"):
            self.assertIn(f"required property var {field}", presentation)
            self.assertIn(f"{field}: {field}", presentation)
        self.assertNotIn("DeveloperRole", catalogue_header)
        self.assertNotIn("PublisherRole", catalogue_header)
        self.assertIn("height: metadataRow.implicitHeight", game_card)

    def test_library_navigation_separates_grid_and_collection_controls(self) -> None:
        shell = (ROOT / "ui" / "ConsoleShell.qml").read_text()
        library_space = (ROOT / "ui" / "LibrarySpace.qml").read_text()
        spatial_surface = (ROOT / "ui" / "LibrarySpatialSurface.qml").read_text()
        self.assertIn("function moveLibraryVertical(delta)", shell)
        self.assertIn("function moveLibraryCategory(delta)", shell)
        self.assertIn("librarySpace.moveCategory(delta)", shell)
        self.assertIn("moveLibraryCollection(-1)", shell)
        self.assertIn("moveLibraryCollection(1)", shell)
        self.assertIn('action: "navigation"', shell)
        self.assertIn('action: "previousCollection"', shell)
        self.assertIn('action: "nextCollection"', shell)
        self.assertIn('root.selectedCategoryIndex === 3 ? "Navigation" : "Navigate"', shell)
        self.assertIn('property bool libraryTransitioning: false', shell)
        self.assertIn('property: "libraryTransitionProgress"', shell)
        transition = shell[shell.index('id: libraryTransitionAnimation'):]
        transition = transition.split("    NumberAnimation {", 1)[0]
        self.assertIn('property: "libraryTransitionProgress"', transition)
        self.assertIn('themeMotion.duration("surface", 500)', transition)
        self.assertIn('transitionProgress: root.libraryTransitionProgress', shell)
        self.assertIn('transitionExpanding: root.libraryTransitionExpanding', shell)
        self.assertIn('y: !transitionExpanding ? (1 - transitionProgress) * height : 0', library_space)
        activate = shell.split('if (space === "library") {', 1)[1].split('if (space === "store") {', 1)[0]
        self.assertIn("pendingLibraryLaunch = visibleLibraryGame", activate)
        self.assertIn("startLibraryTransition()", activate)
        self.assertNotIn("launchGame(", activate)
        handoff = shell.split("id: handoffTimer", 1)[1].split("SequentialAnimation", 1)[0]
        self.assertIn('root.pendingHomeLaunchPhase = "exiting"', handoff)
        self.assertIn("presentationCoordinator.beginContentExit()", handoff)
        self.assertNotIn("root.launchGame(game, true)", handoff)
        self.assertIn('pendingHomeLaunchPhase = "launching"', shell)
        activation = shell.split('if (space === "library") {', 1)[1].split('if (space === "store") {', 1)[0]
        self.assertIn("homeFadeIn.stop()", activation)
        self.assertIn("launchExitActive: root.pendingLibraryLaunch !== null", shell)
        geometry = (ROOT / "ui" / "LibrarySpatialGeometry.js").read_text()
        self.assertIn("width: fullscreenWidth", geometry)
        self.assertIn("height: fullscreenHeight", geometry)
        self.assertIn("homeWidth + (fullscreenWidth - homeWidth) * progress", geometry)
        self.assertIn("height: fullscreenHeight", geometry)
        self.assertIn("homeHeight + (fullscreenHeight - homeHeight) * progress", geometry)
        self.assertIn("surfacePresentationProgress: launchExitActive ? 1 : progress", spatial_surface)
        self.assertIn("parent.height : surfaceHeight) * (1 - progress)", spatial_surface)
        library_host = shell.split('LibrarySpace {', 1)[1].split('StoreOptions {', 1)[0]
        self.assertNotIn('anchors.fill: parent', library_host)
        self.assertIn('height: parent.height', library_host)
        self.assertIn('LibrarySpatialSurface {', shell)
        self.assertIn('homeX: root.homeContentRailX', shell)
        self.assertIn('fullscreenWidth: root.expandedShellWidth', shell)
        self.assertIn('contentBottom: root.expandedContentBottom', shell)
        self.assertIn('contentSideMargin: root.expandedContentSideMargin', shell)
        self.assertIn('expandedContentSideMargin: design(120)', shell)
        self.assertIn('expandedGridGap: design(14)', shell)
        self.assertIn('expandedShellSideMargin:', shell)
        self.assertIn('expandedShellSideMargin: 20', shell)
        self.assertIn('expandedShellTop: 20', shell)
        self.assertIn('expandedSurfaceChromeGap: design(8)', shell)
        self.assertIn('expandedHintRowTop: interactionRail.y + expandedHintRow.y', shell)
        self.assertIn('expandedShellBottom: expandedHintRowTop', shell)
        self.assertIn('root.space === "store"', shell)
        self.assertIn('label: root.space === "library" ? "Launch" : "Download"', shell)
        spatial_surface = (ROOT / "ui" / "LibrarySpatialSurface.qml").read_text()
        self.assertNotIn("z: 1", spatial_surface)
        self.assertIn('contentOpacity: root.libraryContentOpacity', shell)
        self.assertNotIn("GlassSurface {", library_space)
        library_home = (ROOT / "ui" / "LibraryHome.qml").read_text()
        self.assertIn("NavigationCard", library_home)
        game_card = (ROOT / "ui" / "GameCard.qml").read_text()
        self.assertIn("card.librarySurfaceMaterial", game_card)
        self.assertIn("card.librarySurfaceMaterial || card.materialEnabled", game_card)
        self.assertIn('action: "confirm"', shell)
        self.assertIn("filteredGames", library_space)
        self.assertIn("categoryTape", library_space)
        self.assertIn("orientation: ListView.Horizontal", library_space)

    def test_library_projection_uses_normalized_dimensions_and_memberships(self) -> None:
        library_space = (ROOT / "ui" / "LibrarySpace.qml").read_text()
        projection = (ROOT / "ui" / "LibraryProjection.js").read_text()
        self.assertIn('label: platformLabel', projection)
        self.assertIn('label: providerLabel(provider)', projection)
        self.assertIn('"steam-aurelia": "Steam"', projection)
        self.assertIn('if (mode === "platform")', projection)
        self.assertIn('if (a.key === "pc") return -1', projection)
        self.assertIn('if (mode === "provider")', projection)
        self.assertIn('platform.toLowerCase() === "pc"', projection)
        self.assertIn('game.genres && game.genres.length ? game.genres : ["Other"]', projection)
        self.assertIn('game.game_modes && game.game_modes.length ? game.game_modes : [game.game_mode || "Other"]', projection)
        self.assertIn('label.trim().toLowerCase()', projection)
        self.assertNotIn('game.platforms && game.platforms.length ? game.platforms', projection)
        self.assertNotIn('join(",")', projection)

        installable_projection = (ROOT / "ui" / "InstallableProjection.js").read_text()
        self.assertIn('var providers = ["steam-aurelia", "epic", "gog"]', installable_projection)
        self.assertIn('if (game.provider === "steam")', installable_projection)

    def test_library_dimensions_are_fixed_and_activation_uses_semantic_identity(self) -> None:
        shell = (ROOT / "ui" / "ConsoleShell.qml").read_text()
        dimensions = (ROOT / "ui" / "LibraryDimensions.js").read_text()
        self.assertEqual(dimensions.count('mode: "'), 4)
        self.assertLess(dimensions.index('mode: "platform"'), dimensions.index('mode: "provider"'))
        self.assertLess(dimensions.index('mode: "provider"'), dimensions.index('mode: "game_mode"'))
        self.assertLess(dimensions.index('mode: "game_mode"'), dimensions.index('mode: "genre"'))
        self.assertIn('property string libraryDimension: "platform"', shell)
        setter = shell[shell.index("function setLibraryDimension(mode)"):
                       shell.index("function openLibraryDimension(mode)")]
        self.assertIn("libraryDimension = mode", setter)
        self.assertNotIn("libraryHomeIndex", setter)
        self.assertNotIn("libraryCategoryMru", shell)
        self.assertNotIn("libraryCollections", shell)
        self.assertIn("function openLibraryDimension(mode)", shell)
        self.assertIn("root.openLibraryDimension(dimensionKey)", shell)
        activation = shell[shell.index("function activate()"):
                           shell.index("function back()")]
        self.assertIn("libraryHomeLandingRef.activateSelected()", activation)
        self.assertIn("function openLibrarySurface()", shell)
        dimension_entry = shell[shell.index("function openLibraryDimension(mode)"):
                                shell.index("function openLibrarySurface()")]
        self.assertIn("openLibrarySurface()", dimension_entry)
        self.assertNotIn("activate()", dimension_entry)
        self.assertIn("openRequested(String(category.mode))", (ROOT / "ui" / "LibraryHome.qml").read_text())
        self.assertIn("categories: root.libraryDimensions", shell)
        self.assertNotIn("collectionIndex", shell)

    def test_library_shoulder_cycling_wraps_canonical_dimensions(self) -> None:
        shell = (ROOT / "ui" / "ConsoleShell.qml").read_text()
        dimensions = (ROOT / "ui" / "LibraryDimensions.js").read_text()
        cycling = shell[shell.index("function adjacentLibraryDimension(delta)"):
                        shell.index("function moveLibraryCollection(delta)")]
        self.assertIn("LibraryDimensions.adjacent(libraryDimension, delta)", cycling)
        self.assertIn("(index + delta + all.length) % all.length", dimensions)
        self.assertIn("setLibraryDimension(adjacentLibraryDimension(delta))", shell)

    def test_library_shoulder_hints_name_dimensions_from_the_switching_sequence(self) -> None:
        shell = (ROOT / "ui" / "ConsoleShell.qml").read_text()
        self.assertIn('label: root.libraryDimensionLabel(root.adjacentLibraryDimension(-1))', shell)
        self.assertIn('label: root.libraryDimensionLabel(root.adjacentLibraryDimension(1))', shell)

    def test_library_header_and_projection_use_one_dimension_and_canonical_games(self) -> None:
        library_space = (ROOT / "ui" / "LibrarySpace.qml").read_text()
        self.assertIn("readonly property string categoryMode: projectionState.dimensionKey", library_space)
        self.assertIn('root.headingText) + ": " + root.dimensionLabel', library_space)
        self.assertNotIn('CATEGORIZE BY', library_space)
        self.assertNotIn('function labelForDimension(', library_space)
        projection = library_space[library_space.index("function commitProjection("):
                                    library_space.index("function moveCategory(delta)")]
        library_projection = (ROOT / "ui" / "LibraryProjection.js").read_text()
        self.assertIn("LibraryProjection.build(canonicalGames, mode, wantedKey", projection)
        self.assertIn("for (var i = 0; i < canonicalGames.length; ++i)", library_projection)
        self.assertIn("valuesFor(game, mode)", library_projection)
        self.assertIn("rememberedSelections[mode]", projection)
        self.assertIn("projectionState = nextState", projection)
        self.assertNotIn("filteredGames.length; ++i", projection)
        self.assertIn("onDimensionKeyChanged: if (projectionInitialized) commitProjection(dimensionKey, \"\", \"\")", library_space)

    def test_library_pass_two_layout_contract_is_contained_and_non_glass(self) -> None:
        library = (ROOT / "ui" / "LibrarySpace.qml").read_text()
        shell = (ROOT / "ui" / "ConsoleShell.qml").read_text()
        artwork = (ROOT / "ui" / "GameArtwork.js").read_text()
        self.assertIn("surfaceBounds: root.expandedSurfaceBounds", shell)
        self.assertIn("innerInset: root.expandedInnerInset", shell)
        self.assertIn("property rect surfaceBounds", library)
        self.assertNotIn("frameMargin", library)
        self.assertIn("readonly property rect contentFrameRect", library)
        self.assertIn("id: contentFrame", library)
        self.assertIn("clip: true", library)
        self.assertIn("property real internalSurfaceOpacity: 0.34", library)
        self.assertIn("(contentFrameRect.width - panelGap) * 0.40", library)
        self.assertIn("GameMetadata.rows(selectedGame", library)
        self.assertIn("DescriptionFit.select(source", library)
        self.assertIn("anchors.bottom: parent.bottom", library)
        self.assertIn("horizontalAlignment: Text.AlignLeft", library)
        self.assertIn("expandedShellSideMargin: 20", shell)
        self.assertIn("expandedShellTop: 20", shell)
        self.assertIn("id: detailTitleRegion", library)
        self.assertIn("id: landscapeArea", library)
        self.assertIn("id: detailMetadata", library)
        self.assertIn("id: descriptionRegion", library)
        self.assertIn("y: detailTitleRegion.y + detailTitleRegion.height + detailSurface.gutter", library)
        self.assertIn("height: Math.max(0, detailSurface.height - y - detailSurface.inset)", library)
        self.assertIn("id: detailMetadata", library)
        self.assertIn("y: detailSurface.rightMetadataY", library)
        self.assertIn("height: implicitHeight", library)
        self.assertIn("wrapText: true", library)
        self.assertIn("maximumLineCount: 0", library)
        self.assertNotIn("fitText: true", library)
        metadata_row = (ROOT / "ui" / "FocalMetadataRow.qml").read_text()
        self.assertIn("leftTextMargin: glyphColumnWidth + 8 * uiScale", metadata_row)
        self.assertIn("wrapMode: root.wrapText ? Text.WordWrap", metadata_row)
        self.assertIn("anchors.rightMargin: root.trailingGlyph ? root.leftTextMargin : 0", metadata_row)
        self.assertIn("maximumLineCount: 4", library)
        self.assertIn("fontSizeMode: Text.Fit", library)
        self.assertIn("property bool fitText: false", metadata_row)
        self.assertIn("fontSizeMode: root.fitText ? Text.Fit", metadata_row)
        self.assertNotIn("GameMetadata.detailRows", library)
        self.assertNotIn("MudosGlassItem", library)
        self.assertNotIn("GlassSurface", library)
        self.assertIn("source: GameArtwork.portraitIcon(gameRow.modelData)", library)
        self.assertIn("source: GameArtwork.previewStill(root.selectedGame)", library)
        self.assertIn("fillMode: Image.PreserveAspectFit", library)
        self.assertIn("height: root.rowHeight", library)
        self.assertIn("font.family: root.libraryFontFamily", library)
        self.assertNotIn('categoryTapeRightInset', library)
        self.assertIn('width: parent.width', library)
        self.assertIn("function previewStill(game)", artwork)
        self.assertNotIn("landscape_artwork_url", artwork)
        self.assertIn("property int previewGeneration", library)
        self.assertIn("FocalMetadataRow {", library)
        self.assertNotIn("GameCard {", library)

    def test_library_first_dimension_and_category_transitions_rebuild_from_canonical_source(self) -> None:
        library_space = (ROOT / "ui" / "LibrarySpace.qml").read_text()
        self.assertIn("property var canonicalGames: []", library_space)
        self.assertIn("property var projectionState:", library_space)
        self.assertIn("readonly property var filteredGames: projectionState.games", library_space)
        self.assertIn("onCanonicalGamesChanged: {", library_space)
        self.assertIn("Qt.callLater(recomputeDescription)", library_space)
        move_category = library_space[library_space.index("function moveCategory(delta)"):
                                      library_space.index("function moveGame(delta)")]
        self.assertIn("projectionState.categories[next].key", move_category)
        self.assertIn("commitProjection(projectionState.dimensionKey", move_category)
        self.assertNotIn("filteredGames =", move_category)
        self.assertIn("categoryKey: built.categoryKey", library_space)
        self.assertIn("rememberedSelections", library_space)
        self.assertIn("canonicalGames.slice(0)", library_space)

    def test_library_projection_qml_round_trip_regressions(self) -> None:
        runner = shutil.which("qmltestrunner") or "/usr/lib/qt6/bin/qmltestrunner"
        if not Path(runner).exists():
            self.skipTest("qmltestrunner is not installed")
        environment = os.environ.copy()
        environment["QT_QPA_PLATFORM"] = "offscreen"
        environment["QT_QUICK_BACKEND"] = "software"
        result = subprocess.run(
            [runner, "-input", str(ROOT / "tests/qml/tst_library_projection.qml")],
            capture_output=True, text=True, env=environment, timeout=20,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_unified_settings_space_qml_regressions(self) -> None:
        runner = shutil.which("qmltestrunner") or "/usr/lib/qt6/bin/qmltestrunner"
        if not Path(runner).exists():
            self.skipTest("qmltestrunner is not installed")
        environment = os.environ.copy()
        environment["QT_QPA_PLATFORM"] = "offscreen"
        environment["QT_QUICK_BACKEND"] = "software"
        result = subprocess.run(
            [runner, "-import", str(ROOT / "tests/qml/fakes"),
             "-input", str(ROOT / "tests/qml/tst_settings_space.qml")],
            capture_output=True, text=True, env=environment, timeout=20,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_game_options_candidate_delegate_qml_regressions(self) -> None:
        runner = shutil.which("qmltestrunner") or "/usr/lib/qt6/bin/qmltestrunner"
        if not Path(runner).exists():
            self.skipTest("qmltestrunner is not installed")
        environment = os.environ.copy()
        environment["QT_QPA_PLATFORM"] = "offscreen"
        environment["QT_QUICK_BACKEND"] = "software"
        result = subprocess.run(
            [runner, "-import", str(ROOT / "tests/qml/fakes"),
             "-input", str(ROOT / "tests/qml/tst_game_options_candidates.qml")],
            capture_output=True, text=True, env=environment, timeout=20,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_storehome_uses_its_scope_categories_without_old_library_collection_api(self) -> None:
        store_home = (ROOT / "ui" / "StoreHome.qml").read_text()
        library_space = (ROOT / "ui" / "LibrarySpace.qml").read_text()
        self.assertIn("browseCategories: root.categories", store_home)
        self.assertIn("browseCategoryIndex: root.categoryIndex", store_home)
        self.assertIn("onBrowseCategoryRequested: root.categoryIndex = index", store_home)
        self.assertIn("displayCategoryIndex = categoryIndex", store_home)
        self.assertNotIn("onCollectionChanged", store_home)
        self.assertNotIn("collectionIndex", store_home)
        self.assertIn("property var browseCategories: []", library_space)
        self.assertIn("signal browseCategoryRequested(int index)", library_space)
        self.assertIn("libraryDimension", (ROOT / "ui" / "ConsoleShell.qml").read_text())

    def test_qmllint_checks_storehome_and_libraryspace_when_available(self) -> None:
        qmllint = shutil.which("qmllint") or "/usr/lib/qt6/bin/qmllint"
        if not Path(qmllint).exists():
            self.skipTest("qmllint is not installed")
        result = subprocess.run(
            [qmllint, "--max-warnings", "-1", "-I", str(ROOT / "ui"),
             str(ROOT / "ui/StoreHome.qml"), str(ROOT / "ui/LibrarySpace.qml")],
            capture_output=True, text=True, timeout=20,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotIn("onCollectionChanged", (ROOT / "ui/StoreHome.qml").read_text())

    def test_library_home_entry_and_in_library_change_use_dimension_identity(self) -> None:
        shell = (ROOT / "ui" / "ConsoleShell.qml").read_text()
        self.assertIn("setLibraryDimension(mode)", shell)
        self.assertIn("root.openLibraryDimension(dimensionKey)", shell)
        self.assertIn("setLibraryDimension(adjacentLibraryDimension(delta))", shell)
        self.assertIn("dimensionKey: root.libraryDimension", shell)

    def test_library_home_landing_qml_behaviour(self) -> None:
        runner = shutil.which("qmltestrunner") or "/usr/lib/qt6/bin/qmltestrunner"
        if not Path(runner).exists():
            self.skipTest("qmltestrunner is not installed")
        environment = os.environ.copy()
        environment["QT_QPA_PLATFORM"] = "offscreen"
        environment["QT_QUICK_BACKEND"] = "software"
        result = subprocess.run(
            [runner, "-import", str(ROOT / "tests/qml/fakes"),
             "-input", str(ROOT / "tests/qml/tst_library_home_landing.qml")],
            capture_output=True, text=True, env=environment, timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_library_provider_dimension_has_one_source_of_truth(self) -> None:
        dimensions = (ROOT / "ui" / "LibraryDimensions.js").read_text()
        for label, mode in (("Platform", "platform"), ("Provider", "provider"),
                            ("Game Mode", "game_mode"), ("Genre", "genre")):
            self.assertIn('label: "%s", mode: "%s"' % (label, mode), dimensions)

    def test_launch_errors_are_not_reported_as_catalogue_failures(self) -> None:
        self.assertIn('encodeURIComponent(game.game_id)', QML)
        self.assertIn('}, "Launch failed", generation, function()', QML)

    def test_home_launch_waits_for_feedback_exit_and_hidden_boundary(self) -> None:
        game_card = (ROOT / "ui" / "GameCard.qml").read_text()
        coordinator = (ROOT / "ui" / "PresentationCoordinator.qml").read_text()
        recent = (ROOT / "ui" / "RecentHome.qml").read_text()
        self.assertIn("signal playFeedbackCompleted()", game_card)
        self.assertIn("card.playFeedbackCompleted()", game_card)
        self.assertIn("function beginPendingHomeLaunch", QML)
        self.assertIn("function completePendingHomeLaunch", QML)
        self.assertIn("function finishHiddenHomeLaunch", QML)
        self.assertIn("beginContentExit()", QML)
        self.assertIn("contentHiddenReached", coordinator)
        self.assertIn("freezePresentation", recent)
        self.assertIn("reconcilePresentation", recent)
        self.assertIn("HOME_HIDDEN_LAUNCH_HANDOFF", QML)
        self.assertNotIn("launchGame(visibleRecentGame)", QML)
        self.assertNotIn("PauseAnimation { duration: 160", QML)

    def test_return_observer_is_independent_of_launch_status_polling(self) -> None:
        self.assertIn("property bool returnWatchActive: false", QML)
        self.assertIn("function startReturnWatch()", QML)
        self.assertIn("function refreshReturnState(generation)", QML)
        self.assertIn("function evaluateReturnReadiness(source)", QML)
        self.assertIn('traceLaunchEvent("RETURN_WATCH_STARTED"', QML)
        self.assertIn('traceLaunchEvent("RETURN_STATE_OBSERVED"', QML)
        self.assertIn('traceLaunchEvent("RETURN_PRESENTATION_OBSERVED"', QML)
        self.assertIn('traceLaunchEvent("RETURN_READY"', QML)
        self.assertIn('traceLaunchEvent("RETURN_WATCH_STOPPED"', QML)
        self.assertIn("startReturnWatch()", QML[QML.index("function finishHiddenHomeLaunch") :])
        self.assertIn("returnObserverTimer.start()", QML)
        self.assertIn("returnObserverTimer.stop()", QML)
        self.assertIn("returnStateObserved && presented", QML)
        self.assertIn("stopReturnWatch(\"launch-failed\")", QML)

    def test_recent_reconcile_is_deferred_until_presented(self) -> None:
        presented = QML.split("function onContentPresentedReached()", 1)[1].split(
            "function traceLaunchMutation", 1)[0]
        prepare = QML.split("function prepareAndPresentHome()", 1)[1].split(
            "function observeGamePresentation", 1)[0]
        handoff = QML.split("function finishHiddenHomeLaunch()", 1)[1].split(
            "function installGame", 1)[0]
        self.assertIn("returnPresentationPending", presented)
        self.assertIn("recentHome.reconcilePresentation()", presented)
        self.assertIn("returnPresentationPending = false", presented)
        self.assertIn("function focusRecentForReturn()", QML)
        self.assertNotIn("recentHome.reconcilePresentation()", prepare)
        self.assertNotIn("recentHome.reconcilePresentation()", handoff)
        self.assertIn("returnPresentationPending = true", prepare)
        self.assertIn("homeContentOpacity = 1", prepare)
        self.assertLess(prepare.index("homeContentOpacity = 1"),
                        prepare.index("presentationCoordinator.beginStartup()"))
        self.assertIn('traceLaunchEvent("PRESENTATION_FREEZE"', QML)
        self.assertIn('traceLaunchEvent("RECENT_PRESENTATION_RELEASED"', QML)
        self.assertIn("returnPresentationPending", QML[QML.index("readonly property bool homeLaunchGated") :])

    def test_launch_focuses_recent_before_showing_overlay(self) -> None:
        launch = QML.split("function launchGame(game, choreographyComplete)", 1)[1].split(
            "function launchProviderMenu", 1)[0]
        self.assertLess(launch.index("focusRecentForReturn()"),
                        launch.index("launchOverlayVisible = true"))

    def test_presented_reconcile_happens_before_input_unlock(self) -> None:
        presented = QML.split("function onContentPresentedReached()", 1)[1].split(
            "function traceLaunchMutation", 1)[0]
        self.assertLess(presented.index("recentHome.reconcilePresentation()"),
                        presented.index("HOME_INPUT_UNLOCKED"))

    def test_recent_reconcile_requests_authority_before_releasing_frozen_rows(self) -> None:
        recent = (ROOT / "ui" / "RecentHome.qml").read_text()
        reconcile = recent.split("function reconcilePresentation()", 1)[1].split(
            "function selectionCardVelocityAt", 1)[0]
        self.assertLess(reconcile.index("selectionIndexRequested(reconciledIndex)"),
                        reconcile.index("presentationFrozen = false"))

    def test_library_and_store_category_rail_uses_content_sized_selected_anchor(self) -> None:
        library_space = (ROOT / "ui" / "LibrarySpace.qml").read_text()
        self.assertIn("id: categoryTape", library_space)
        self.assertIn("orientation: ListView.Horizontal", library_space)
        self.assertIn("positionViewAtIndex(currentIndex, ListView.Contain)", library_space)
        self.assertIn("positionViewAtIndex(root.categoryTapeIndex, ListView.Contain)", library_space)
        self.assertIn("visible: index === root.categoryTapeIndex", library_space)
        self.assertIn("property rect surfaceBounds", library_space)
        self.assertIn("id: contentFrame", library_space)
        self.assertIn("clip: true", library_space)
        self.assertNotIn("GlassSurface {", library_space)
        self.assertIn("LibrarySpace {", (ROOT / "ui" / "StoreHome.qml").read_text())
        store_home = (ROOT / "ui" / "StoreHome.qml").read_text()
        self.assertIn('title: "Installable"', store_home)
        self.assertIn('"No games ready to install"', store_home)
        self.assertIn('title: "Installable"', store_home)
        self.assertIn('root.space === "store"', QML)
        self.assertIn("text: themeText.homeTitle(root.domains[index])", QML)
        self.assertIn("themeText.homeTitleSpacing(root.uiScale)", QML)
        self.assertIn("luluPalette.headingAccent", QML)
        self.assertIn('progress: root.libraryTransitionProgress', QML)
        self.assertIn('property bool storeTransitioning: false', QML)
        self.assertIn('presentationTarget = "store"', QML)

    def test_expanded_substrate_extension_preserves_content_and_full_rail_width(self) -> None:
        geometry = (ROOT / "ui" / "ExpandedSurfaceGeometry.qml").read_text()
        shell = (ROOT / "ui" / "ConsoleShell.qml").read_text()
        library = (ROOT / "ui" / "LibrarySpace.qml").read_text()
        self.assertIn("surfaceLead - surfaceTopExtension", geometry)
        self.assertIn("contentY: surfaceY + surfaceTopExtension", geometry)
        self.assertIn("expandedContentBounds: expandedGeometry.contentBounds", shell)
        self.assertNotIn("expandedStatusReserve", shell)
        self.assertNotIn("libraryCategoryRightSafeInset", shell)
        self.assertNotIn("expandedHeaderRightMargin", shell)
        self.assertNotIn("categoryTapeRightInset", library)
        self.assertIn("width: parent.width", library)
        self.assertIn("positionViewAtIndex(root.categoryTapeIndex, ListView.Contain)", library)
        self.assertIn('space = settled.space', QML)

    def test_launch_status_is_transactional_and_catalogue_focus_is_identity_based(self) -> None:
        self.assertIn('property string launchStatus: "idle"', QML)
        self.assertIn('"[Launch] " + failureDetail', QML)
        self.assertIn('String(state.last_failure_reason).replace(/\\s+/g, " ").slice(0, 320)', QML)
        self.assertIn("property int launchGeneration: 0", QML)
        self.assertIn("property string launchToken: \"\"", QML)
        self.assertIn("property int launchStateSerial: 0", QML)
        self.assertIn("property int launchStateRank: 0", QML)
        self.assertIn("function applyLaunchState(state, generation)", QML)
        self.assertIn("state.launch_token", QML)
        self.assertIn('readonly property string recentSelectedGameId:', QML)
        self.assertIn("onSelectionGameChanged", QML)
        self.assertNotIn('message = "Launch requested"', QML)
        self.assertIn("if (stateRank < launchStateRank)", QML)
        self.assertIn('state.lifecycle === "presentation_pending"', QML)
        self.assertNotIn('launchStatus === "launching" || launchStatus === "running"', QML)
        self.assertIn("anchors.fill: parent", QML)
        self.assertIn("launchOverlayRetired = true", QML)
        self.assertIn("visible: root.launchScreenVisible", QML)
        self.assertIn("launchToken = data.token", QML)

        self.assertIn("refreshLaunchLog(root.launchGeneration)", QML)
        self.assertLess(QML.index("launchToken = data.token"), QML.index("            refreshLaunchState(generation)"))
        self.assertLess(QML.index("retireLaunchOverlay(generation)"), QML.index("function refreshLaunchLog(generation)"))
        self.assertIn('request("/cancel", "POST"', QML)
        self.assertIn('action === "back"', QML)
        self.assertIn('launchTitle = "Steam Store"', QML)
        bridge = (ROOT / "scripts" / "console-ui-bridge.py").read_text()
        self.assertIn('self.launch_logs.start("steam-store")', bridge)


    def test_steam_overlay_has_game_presentation_shell_return_failsafe(self) -> None:
        self.assertIn("property bool shellWasLeft: false", QML)
        self.assertIn("function finishLaunchOnShellReturn()", QML)
        self.assertIn("root.shellWasLeft = true", QML)
        self.assertIn("root.shellWasLeft = true", QML)
        self.assertIn("if (root.shellWasLeft)", QML)
        self.assertIn("function prepareAndPresentHome()", QML)
        self.assertIn("launchLifecycle !== \"shell\"", QML)
        self.assertIn("launchLogTimer.stop()", QML)
        self.assertIn("launchLogLines = []", QML)
        self.assertIn("launchGeneration++", QML)
        self.assertIn('root.launchGameId.indexOf("steam:") === 0', QML)

    def test_ui_audio_engine_has_semantic_voices_and_safety_rules(self) -> None:
        engine = (ROOT / "ui" / "UiAudioEngine.qml").read_text()
        self.assertIn("function play(semantic)", engine)
        self.assertIn("debounceInterval: 55", engine)
        self.assertIn("function audioBridge()", engine)
        self.assertIn('typeof bridge.playUiSound !== "function"', engine)
        self.assertNotIn("QtMultimedia", engine)
        self.assertNotIn('source: "UiAudioEngine.qml"', (ROOT / "ui" / "MudosGuide.qml").read_text())
        self.assertIn("UiAudioEngine { id: uiAudioEngine }", QML)
        self.assertNotIn("onValueChanged", engine)

    def test_ui_audio_assets_are_canonical_and_replaceable(self) -> None:
        manifest = (ROOT / "ui" / "sounds" / "README.md").read_text()
        for filename in ("ui-navigate.wav", "ui-confirm.wav", "ui-back.wav", "ui-error.wav"):
            self.assertIn(f"`{filename}`", manifest)
        self.assertIn("audio-only playback path", manifest)

if __name__ == "__main__":
    unittest.main()
