import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
QML = (ROOT / "ui" / "ConsoleShell.qml").read_text()
SHELL_PROFILE = (ROOT / "config" / "inputplumber" / "profiles" / "shell.yaml").read_text()


class ConsoleUiTests(unittest.TestCase):
    def test_qml_preserves_card_to_space_shell_interaction(self) -> None:
        self.assertIn('property var domains: ["System", "Store", "Library", "Recent"]', QML)
        self.assertIn("property int domainIndex: 3", QML)
        self.assertIn('property string space: "home"', QML)
        self.assertIn('space = "library"', QML)
        self.assertIn('space = "home"', QML)
        self.assertIn('readonly property string apiUrl:', QML)
        self.assertIn("function activate()", QML)
        self.assertIn("function moveDomain(delta)", QML)
        self.assertIn('message = "Store space is not implemented"', QML)
        self.assertIn('message = "System space is not implemented"', QML)
        self.assertIn('request("/?scope=recent"', QML)
        self.assertIn('readonly property string libraryScope:', QML)
        self.assertNotIn("/dev/input", QML)
        self.assertNotIn("Social", QML)

    def test_extracted_ui_primitives_preserve_real_game_card_data(self) -> None:
        for filename in ("GameCard.qml", "RecentHome.qml", "LibraryHome.qml", "LibrarySpace.qml", "PlaceholderHome.qml"):
            self.assertTrue((ROOT / "ui" / filename).exists())
        game_card = (ROOT / "ui" / "GameCard.qml").read_text()
        library_space = (ROOT / "ui" / "LibrarySpace.qml").read_text()
        self.assertIn("required property var game", game_card)
        self.assertIn("card.game.artwork_url", game_card)
        self.assertIn("signal collectionChanged", library_space)
        self.assertIn("signal launchRequested", library_space)

    def test_home_uses_one_fixed_content_stage_and_compact_library_object(self) -> None:
        self.assertIn("readonly property int headingCardGap: 21", QML)
        self.assertIn("readonly property int homeHintTopY: height - 45", QML)
        self.assertIn("homeContentOriginY: homeHintTopY - acceptedRecentCardHeight - headingCardGap", QML)
        self.assertIn("selectedDomainY: homeContentOriginY - activeHeadingHeight - headingCardGap", QML)
        self.assertIn("acceptedRecentCardHeight", QML)
        self.assertIn("y: root.selectedDomainY + root.domainOffset(index) * 42", QML)
        self.assertIn("function domainOffset(index)", QML)
        self.assertIn("y: root.homeContentOriginY", QML)
        self.assertNotIn("root.domainIndex * 40", QML)
        library_home = (ROOT / "ui" / "LibraryHome.qml").read_text()
        self.assertIn('text: "All Games"', library_home)
        self.assertIn("property real cardHeight", library_home)
        self.assertIn("height: cardHeight", library_home)
        self.assertIn("readonly property real libraryGameCardAspectRatio: 1 / 1.55", library_home)
        self.assertIn("width: cardHeight * libraryGameCardAspectRatio", library_home)
        self.assertIn("libraryHomeCard.width * 0.45", library_home)
        self.assertNotIn("gameCount", library_home)
        self.assertNotIn("selectedGame", library_home)

    def test_cards_preserve_portrait_artwork_and_library_density(self) -> None:
        game_card = (ROOT / "ui" / "GameCard.qml").read_text()
        library_space = (ROOT / "ui" / "LibrarySpace.qml").read_text()
        self.assertIn(": width * 1.5", game_card)
        self.assertIn("Image.PreserveAspectFit", game_card)
        self.assertIn("!recentFocal", game_card)
        self.assertIn("readonly property int gridColumns: 6", library_space)
        self.assertIn("readonly property int headerToGridGap: currentHeaderToGridGap / 2", library_space)
        self.assertIn("y: collectionSelectorBottomY + headerToGridGap", library_space)
        self.assertIn("(usableGridWidth - (gridColumns - 1) * gridGap) / gridColumns", library_space)
        self.assertIn("libraryCardHeight: libraryCardWidth * 1.55", library_space)
        self.assertIn("id: gridViewport", library_space)
        self.assertIn("clip: true", library_space)
        self.assertIn("y: -gridRow * gridRowStep", library_space)
        self.assertIn("visible: gridContentHeight + gameGrid.y > parent.height", library_space)
        self.assertIn("horizontalAlignment: Text.AlignHCenter", game_card)
        self.assertIn("verticalAlignment: Text.AlignVCenter", game_card)
        self.assertIn("elide: card.compact ? Text.ElideNone : Text.ElideRight", game_card)

    def test_recent_has_distinct_focal_and_compact_geometry(self) -> None:
        recent = (ROOT / "ui" / "RecentHome.qml").read_text()
        game_card = (ROOT / "ui" / "GameCard.qml").read_text()
        self.assertIn("property real focalCardHeight", recent)
        self.assertIn("x: index === selectedIndex", recent)
        self.assertIn("readonly property bool recentFocal", game_card)
        self.assertIn('text: "Last played "', game_card)
        self.assertIn('text: "A  Play"', game_card)
        self.assertIn("maximumLineCount: 2", game_card)
        self.assertIn("radius: recentFocal ? 18 * focalScale : 0", game_card)
        self.assertIn("readonly property real focalMargin", game_card)
        self.assertIn("property real focalScale", game_card)
        self.assertIn("focalScale: 0.67", (ROOT / "ui" / "ConsoleShell.qml").read_text())
        self.assertIn("fragmentShader", game_card)
        self.assertIn("ShaderEffectSource", game_card)
        self.assertIn("hideSource: true", game_card)
        self.assertIn("readonly property real focalMargin", game_card)
        self.assertIn("x: focalMargin + artworkWidth + focalMargin", game_card)
        self.assertIn("anchors.right: parent.right", game_card)
        self.assertIn("anchors.bottom: parent.bottom", game_card)
        self.assertNotIn("card.game.provider.toUpperCase()", game_card)

    def test_orbit_backdrop_uses_qsb_and_plain_fallback(self) -> None:
        backdrop = (ROOT / "ui" / "OrbitBackdrop.qml").read_text()
        shader_builder = (ROOT / "scripts" / "build-orbit-shader.sh").read_text()
        adapter = (ROOT / "scripts" / "build-orbit-qsb.py").read_text()
        self.assertIn('fragmentShader: "shaders/orbit-wave.frag.qsb"', backdrop)
        self.assertIn('color: "#060b16"', backdrop)
        self.assertIn("ShaderEffect.Compiled", backdrop)
        self.assertIn("--qt6", shader_builder)
        self.assertIn("wave.frag", shader_builder)
        for uniform in ("u_resolution", "u_origin", "u_canvas", "u_time", "u_brightness", "u_visibility", "u_primary", "u_secondary", "u_surface", "u_error"):
            self.assertIn(uniform, adapter)
        self.assertIn('replace("gl_FragColor", "fragColor")', adapter)

    def test_glass_prototype_is_reusable_and_limited_to_review_surfaces(self) -> None:
        glass = (ROOT / "ui" / "GlassSurface.qml").read_text()
        shader = (ROOT / "ui" / "shaders" / "liquid-glass.frag").read_text()
        recent = (ROOT / "ui" / "RecentHome.qml").read_text()
        library = (ROOT / "ui" / "LibrarySpace.qml").read_text()
        self.assertIn('fragmentShader: "shaders/liquid-glass.frag.qsb"', glass)
        for parameter in ("refractionStrength", "chromaticSeparation", "ior", "snellMagnitudePixels", "dispersionPixels", "sourcePaddingPixels", "diffusion", "focusAmount", "cornerRadius"):
            self.assertIn(parameter, glass)
        self.assertIn("u_refraction", shader)
        self.assertIn("u_chromatic", shader)
        self.assertIn("u_cornerRadius", shader)
        self.assertIn("glassSource", recent)
        self.assertIn("GlassSurface", library)
        self.assertIn("backdropSource", recent)
        self.assertIn("backdropSource", library)

    def test_glass_refraction_uses_bounded_pixel_space_and_symmetric_channels(self) -> None:
        shader = (ROOT / "ui" / "shaders" / "liquid-glass.frag").read_text()
        glass = (ROOT / "ui" / "GlassSurface.qml").read_text()
        validator = ROOT / "scripts" / "validate-glass-field.py"
        self.assertIn("u_snellMagnitudePixels", shader)
        self.assertIn("refract(viewRay, glassNormal", shader)
        self.assertIn("magnitudePixels = u_snellMagnitudePixels", shader)
        self.assertIn("refractedDirection * magnitudePixels / max(u_captureSize, vec2(1.0))", shader)
        self.assertIn("float insideDistance = max(0.0, -distance)", shader)
        self.assertIn("float edgeField = smoothstep(0.0, 6.0, insideDistance)", shader)
        self.assertIn("sourceRect", glass)
        self.assertIn("textureSize: root.captureSize", glass)
        self.assertNotIn("* smoothstep(0.0, 3.0, insideDistance)", shader)
        self.assertIn("roundedDistance(uv + vec2(gradientStep, 0.0)", shader)
        self.assertIn("redUv = clamp(refractedUv + dispersion", shader)
        self.assertIn("blueUv = clamp(refractedUv - dispersion", shader)
        self.assertTrue(validator.exists())

    def test_shell_profile_routes_semantic_events_to_qt_keys(self) -> None:
        for button, key in (
            ("DPadUp", "KeyUp"),
            ("DPadDown", "KeyDown"),
            ("DPadLeft", "KeyLeft"),
            ("DPadRight", "KeyRight"),
            ("South", "KeyEnter"),
            ("East", "KeyBackspace"),
        ):
            self.assertIn(f"button: {button}", SHELL_PROFILE)
            self.assertIn(f"keyboard: {key}", SHELL_PROFILE)

    def test_launch_errors_are_not_reported_as_catalogue_failures(self) -> None:
        self.assertIn('encodeURIComponent(game.game_id)', QML)
        self.assertIn('}, "Launch failed", generation)', QML)

    def test_launch_status_is_transactional_and_catalogue_focus_is_identity_based(self) -> None:
        self.assertIn('property string launchStatus: "idle"', QML)
        self.assertIn("property int launchGeneration: 0", QML)
        self.assertIn("property string launchToken: \"\"", QML)
        self.assertIn("property int launchStateSerial: 0", QML)
        self.assertIn("property int launchStateRank: 0", QML)
        self.assertIn("function applyLaunchState(state, generation)", QML)
        self.assertIn("state.launch_token", QML)
        self.assertIn("var selectedId = visibleRecentGame ? visibleRecentGame.game_id : \"\"", QML)
        self.assertIn("selectedIndex = index", QML)
        self.assertNotIn('message = "Launch requested"', QML)
        self.assertIn("if (stateRank < launchStateRank)", QML)
        self.assertIn('state.lifecycle === "presentation_pending"', QML)
        self.assertIn('launchStatus === "launching" || launchStatus === "running"', QML)


if __name__ == "__main__":
    unittest.main()
