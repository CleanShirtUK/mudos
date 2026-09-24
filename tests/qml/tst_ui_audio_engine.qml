import QtQuick
import QtTest
import "../../ui"

TestCase {
    name: "UiAudioEngine"

    QtObject {
        id: fakeAudioBridge
        property var played: []
        property bool available: true
        function playUiSound(semantic) {
            played = played.concat([semantic])
            return available
        }
    }

    UiAudioEngine { id: engine; bridgeOverride: fakeAudioBridge }

    function init() {
        fakeAudioBridge.played = []
        fakeAudioBridge.available = true
        engine.lastPlayedAt = ({})
        engine.audioEnabled = true
    }

    function test_disabled_or_unknown_audio_is_safe() {
        engine.audioEnabled = false
        compare(engine.play("navigate"), false)
        compare(engine.play("not-a-sound"), false)
        compare(fakeAudioBridge.played.length, 0)
    }

    function test_semantic_events_route_once_and_navigation_replays() {
        compare(engine.play("navigate"), true)
        compare(engine.play("confirm"), true)
        compare(engine.play("back"), true)
        compare(engine.play("error"), true)
        compare(engine.play("navigate"), false)
        compare(fakeAudioBridge.played, ["navigate", "confirm", "back", "error"])
        wait(60)
        compare(engine.play("navigate"), true)
        compare(fakeAudioBridge.played, ["navigate", "confirm", "back", "error", "navigate"])
    }

    function test_initialization_failure_drops_cue_without_blocking_later_ui() {
        fakeAudioBridge.available = false
        compare(engine.play("navigate"), false)
        wait(60)
        fakeAudioBridge.available = true
        compare(engine.play("navigate"), true)
        compare(fakeAudioBridge.played, ["navigate", "navigate"])
    }
}
