from pathlib import Path
import unittest
import wave


ROOT = Path(__file__).resolve().parents[1]


class UiAudioContractTests(unittest.TestCase):
    def test_audio_path_is_lazy_audio_only_and_uses_default_sdl_output(self) -> None:
        engine = (ROOT / "ui/UiAudioEngine.qml").read_text()
        shell = (ROOT / "ui/ConsoleShell.qml").read_text()
        native = (ROOT / "native/lulu-shell.cpp").read_text()
        cmake = (ROOT / "native/CMakeLists.txt").read_text()
        build_script = (ROOT / "scripts/build-lulu-shell.sh").read_text()
        self.assertNotIn("QtMultimedia", engine + shell)
        self.assertNotIn("SoundEffect", engine + shell)
        self.assertNotIn("MediaPlayer", engine + shell)
        self.assertNotIn("VideoOutput", engine + shell)
        self.assertIn("UiAudioEngine { id: uiAudioEngine }", shell)
        self.assertNotIn("uiAudioLoader", shell)
        self.assertIn("SDL_INIT_AUDIO", native)
        self.assertIn("SDL_AUDIO_DEVICE_DEFAULT_PLAYBACK", native)
        self.assertIn("SDL_LoadWAV", native)
        self.assertIn("UI_AUDIO_UNAVAILABLE", native)
        self.assertNotIn("Multimedia", cmake)
        self.assertNotIn("Qt6Multimedia", build_script)

    def test_assets_are_valid_pcm_and_exist_in_deployed_qml_layout(self) -> None:
        native = (ROOT / "native/lulu-shell.cpp").read_text()
        self.assertIn('QDir(uiAudioAssetDirectory_).filePath(*file)', native)
        for semantic in ("navigate", "confirm", "back", "error"):
            filename = f"ui-{semantic}.wav"
            self.assertIn(f'"{semantic}"), QStringLiteral("{filename}")', native)
            with wave.open(str(ROOT / "ui/sounds" / filename), "rb") as audio:
                self.assertEqual(audio.getcomptype(), "NONE")
                self.assertEqual(audio.getsampwidth(), 2)
                self.assertIn(audio.getnchannels(), (1, 2))
                self.assertGreater(audio.getnframes(), 0)
            self.assertTrue((ROOT / "deploy/payload/ui/sounds" / filename).is_file())

    def test_semantic_routes_do_not_dispatch_from_raw_property_changes(self) -> None:
        shell = (ROOT / "ui/ConsoleShell.qml").read_text()
        self.assertIn('root.playAudioEvent(root.audioEventForAction("up"))', shell)
        self.assertIn('root.playAudioEvent(root.audioEventForAction("down"))', shell)
        self.assertIn('playAudioEvent(audioEventForAction("confirm"))', shell)
        self.assertIn('playAudioEvent(audioEventForAction("back"))', shell)
        self.assertIn("uiAudioEngine.play(event)", shell)
        self.assertNotIn('key === "actionSerial"', shell)
        self.assertNotIn('key === "action"', shell)
        native = (ROOT / "native/lulu-shell.cpp").read_text()
        self.assertIn("if (guideProcess_)", native)
        self.assertIn("playUiSound(semantic)", native)


if __name__ == "__main__":
    unittest.main()
