import asyncio
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from lulu.audio_manager import AudioManagerAdapter


class AudioManagerTests(unittest.TestCase):
    def test_snapshot_normalizes_defaults_devices_volume_and_monitors(self):
        sink = {"name": "alsa_output.hdmi", "description": "HDMI / DisplayPort [TV]",
                "state": "IDLE", "mute": False,
                "volume": {"front-left": {"value_percent": "40%"}, "front-right": {"value_percent": "40%"}},
                "properties": {"media.class": "Audio/Sink"}}
        monitor = {"name": "alsa_output.hdmi.monitor", "description": "Monitor of TV",
                   "state": "SUSPENDED", "mute": False, "volume": {}, "properties": {}}
        source = {"name": "mic.usb", "description": "USB Microphone", "state": "RUNNING", "mute": True,
                  "volume": {"front-left": {"value_percent": "80%"}},
                  "properties": {"media.class": "Audio/Source"}}
        values = {"info": json.dumps({"default_sink_name": "alsa_output.hdmi", "default_source_name": "mic.usb"}),
                  "sinks": json.dumps([sink]), "sources": json.dumps([monitor, source])}
        calls = []
        # The adapter invokes info as --format=json info and list as ... list sinks.
        def runner(*args):
            calls.append(args)
            return values["info"] if args[-1] == "info" else values[args[-1]]
        state = asyncio.run(AudioManagerAdapter(runner, Path("/dev/null/audio-state.json")).snapshot())
        self.assertEqual(state["current_output"]["id"], "alsa_output.hdmi")
        self.assertEqual(state["current_output"]["volume"], 40)
        self.assertEqual(state["inputs"][0]["volume"], 80)
        self.assertTrue(state["inputs"][0]["mute"])
        self.assertEqual(len(state["inputs"]), 1)

    def test_mutations_clamp_and_use_pactl_authority(self):
        calls = []
        def runner(*args):
            calls.append(args)
            if args[-1] == "info":
                return json.dumps({"default_sink_name": "sink", "default_source_name": "source"})
            if args[-1] == "sinks":
                return "[]"
            return "[]"
        adapter = AudioManagerAdapter(runner)
        asyncio.run(adapter.set_volume("sink", 150))
        asyncio.run(adapter.set_mute("sink", True))
        asyncio.run(adapter.set_default_output("sink"))
        self.assertIn(("set-sink-volume", "sink", "100%"), calls)
        self.assertIn(("set-sink-mute", "sink", "1"), calls)
        self.assertIn(("set-default-sink", "sink"), calls)

    def test_service_unavailable_is_navigable(self):
        def runner(*args):
            raise OSError("no audio server")
        state = asyncio.run(AudioManagerAdapter(runner).snapshot())
        self.assertFalse(state["available"])
        self.assertEqual(state["outputs"], [])

    def test_saved_volume_is_restored_once_for_stack_without_native_restore(self):
        with TemporaryDirectory() as directory:
            state_path = Path(directory) / "audio-state.json"
            state_path.write_text(json.dumps({"volume": 40, "mute": False}))
            calls = []
            current_volume = [100]
            def runner(*args):
                calls.append(args)
                if args and args[0] == "set-sink-volume":
                    current_volume[0] = int(args[-1].rstrip("%"))
                    return ""
                if args[-1] == "info":
                    return json.dumps({"default_sink_name": "sink", "default_source_name": "source"})
                if args[-1] == "sinks":
                    return json.dumps([{"name": "sink", "description": "HDMI", "state": "IDLE", "mute": False,
                                        "volume": {"left": {"value_percent": f"{current_volume[0]}%"}}, "properties": {}}])
                return "[]"
            state = asyncio.run(AudioManagerAdapter(runner, state_path).snapshot())
            self.assertEqual(state["current_output"]["volume"], 40)
            self.assertIn(("set-sink-volume", "sink", "40%"), calls)


if __name__ == "__main__":
    unittest.main()
