from pathlib import Path
import unittest
import asyncio
import json
from types import SimpleNamespace
import tempfile

from lulu.consoled import ConsoleInterface
from lulu.notification_geometry import geometry_path, write_geometry


ROOT = Path(__file__).resolve().parents[1]


class NotificationConvergenceTests(unittest.TestCase):
    def test_shell_feedback_route_and_confirmation_split(self):
        shell = (ROOT / "ui/ConsoleShell.qml").read_text()
        bridge = (ROOT / "scripts/console-ui-bridge.py").read_text()
        self.assertIn('apiUrl + "/notification"', shell)
        self.assertIn('path == "/notification"', bridge)
        self.assertIn("property string interactionPrompt", shell)
        self.assertIn('"Press A again to confirm "', shell)
        self.assertIn('"Press X again to remove "', shell)
        self.assertIn("text: root.interactionPrompt", shell)
        self.assertNotIn("text: root.message", shell)

    def test_acquisition_transition_forwarding_has_single_consoled_sink(self):
        acquisition = (ROOT / "src/lulu/acquisitiond.py").read_text()
        consoled = (ROOT / "src/lulu/consoled.py").read_text()
        self.assertIn("self._forward_notification", acquisition)
        self.assertIn("call_notify", acquisition)
        self.assertIn("def Notify(", consoled)
        self.assertIn("self._notification_queue", consoled)
        self.assertNotIn("NotificationPresenter()", acquisition)

    def test_startup_and_generation_refreshes_are_silent(self):
        shell = (ROOT / "ui/ConsoleShell.qml").read_text()
        self.assertIn("function refreshCatalogue()", shell)
        refresh = shell.split("function refreshCatalogue()", 1)[1].split("function refreshStore()", 1)[0]
        self.assertNotIn("root.notify(", refresh)
        self.assertIn('root.notify("Library refreshed", "Your catalogue is up to date", "success")',
                      shell[shell.index('if (key === "mudos.library")'):])
        self.assertNotIn('root.notify("Refreshing library"', shell)
        self.assertNotIn('text: root.message', shell)

    def test_presenter_maps_severity_to_palette_roles(self):
        qml = (ROOT / "ui/MudosNotification.qml").read_text()
        palette = (ROOT / "ui/LuluPalette.qml").read_text()
        self.assertIn('notificationModel.severity', qml)
        self.assertIn("notificationInfo", qml)
        for role in ("notificationInfo", "notificationSuccess", "notificationWarning", "notificationError"):
            self.assertIn(role, palette)
        self.assertIn('role("success", focusIndicator)', palette)
        self.assertIn('role("error", warning)', palette)

    def test_presenter_has_native_timeout_and_status_strip_relative_placement(self):
        qml = (ROOT / "ui/MudosNotification.qml").read_text()
        cpp = (ROOT / "native/mudos-notification.cpp").read_text()
        self.assertIn("dismissalTimer.restart()", qml)
        self.assertIn('object.value("duration").toDouble(4.0)', cpp)
        self.assertIn("QCoreApplication::quit()", cpp)
        self.assertIn("model_->insert(\"visible\", false)", cpp)
        self.assertNotIn('process.stdin.write(b\'{"visible":false}',
                          (ROOT / "src/lulu/notifications.py").read_text())

    def test_catalogue_reconciliation_is_deferred_and_coalesced_during_gameplay(self):
        async def exercise():
            state = {"lifecycle": "game"}
            calls = []

            class Session:
                async def call_get_state(self):
                    return json.dumps(state)

            def refresh(stages=None):
                calls.append(stages)
                return []

            interface = object.__new__(ConsoleInterface)
            interface.sessiond = Session()
            interface.catalogue = SimpleNamespace(refresh=refresh, last_delta_batches=[])
            interface._refresh_task = None
            interface._deferred_refresh_task = None
            interface._deferred_refresh_stages = set()
            interface._deferred_refresh_all = False
            interface._deferred_refresh_waiter = None
            interface._publish_delta_batches = lambda batches: None
            interface.CatalogueChanged = lambda: None

            first = asyncio.create_task(interface.refresh_catalogue({"steam"}, source="automatic"))
            second = asyncio.create_task(interface.refresh_catalogue({"local"}, source="acquisition"))
            await asyncio.sleep(0.05)
            self.assertEqual(calls, [])
            self.assertEqual(interface._deferred_refresh_stages, {"steam", "local"})
            state["lifecycle"] = "shell"
            self.assertEqual(await asyncio.gather(first, second), [0, 0])
            self.assertEqual(calls, [{"steam", "local"}])

        asyncio.run(exercise())

    def test_geometry_handoff_is_atomic_scaling_aware_and_consumed_after_presenter_restart(self):
        record = {
            "session_id": "session-current", "coordinate_space": "shell-logical-top-left",
            "x": 1500, "y": 20, "width": 400, "height": 64,
            "viewport_width": 1920, "viewport_height": 1080,
            "display_width": 1920, "display_height": 1080,
            "device_pixel_ratio": 1.5, "ui_scale": 1.5,
        }
        with tempfile.TemporaryDirectory() as directory:
            written = write_geometry(record, directory)
            path = geometry_path(directory)
            stored = json.loads(path.read_text())
            self.assertEqual(stored["session_id"], "session-current")
            self.assertEqual(stored["device_pixel_ratio"], 1.5)
            self.assertEqual(stored["updated_at"], written["updated_at"])
            # Atomic replacement is idempotent and leaves one complete record
            # for a presenter that starts or restarts later.
            next_record = dict(record, session_id="next-session", x=1450)
            write_geometry(next_record, directory)
            self.assertEqual(json.loads(path.read_text())["session_id"], "next-session")
            with self.assertRaises(ValueError):
                write_geometry(dict(record, x=1900), directory)

        shell = (ROOT / "ui/ConsoleShell.qml").read_text()
        presenter = (ROOT / "ui/MudosNotification.qml").read_text()
        cpp = (ROOT / "native/mudos-notification.cpp").read_text()
        bridge = (ROOT / "scripts/console-ui-bridge.py").read_text()
        self.assertIn('apiUrl + "/notification-geometry"', shell)
        self.assertIn('systemStatusStrip.mapToItem(root.contentItem, 0, 0)', shell)
        self.assertIn('"shell-logical-top-left"', shell)
        self.assertIn("notificationModel.statusRight) - notice.width", presenter)
        self.assertIn("notificationModel.statusBottom) + notificationGap", presenter)
        self.assertIn("notificationModel.visible && root.geometryFits", presenter)
        self.assertNotIn("root.width - width - 20", presenter)
        self.assertIn("QFileSystemWatcher", cpp)
        self.assertIn("loadGeometry()", cpp)
        self.assertIn('path == "/notification-geometry"', bridge)

    def test_geometry_is_retained_for_game_overlay_and_invalid_geometry_is_not_guessed(self):
        presenter = (ROOT / "ui/MudosNotification.qml").read_text()
        cpp = (ROOT / "native/mudos-notification.cpp").read_text()
        self.assertIn("WindowTransparentForInput", presenter)
        self.assertIn("Qt.WindowStaysOnTopHint", presenter)
        self.assertIn('return; // retain last valid session layout', cpp)
        self.assertIn("model_->insert(\"geometryValid\", true)", cpp)
        self.assertIn("geometryFits", presenter)

    def test_consoled_serializes_shell_and_acquisition_events_in_one_fifo(self):
        async def exercise():
            interface = object.__new__(ConsoleInterface)
            delivered = []

            async def fake_presenter(event):
                delivered.append((event.title, "start"))
                await asyncio.sleep(0)
                delivered.append((event.title, "end"))

            interface._notification_presenter = fake_presenter
            interface._notification_queue = asyncio.Queue()
            interface._notification_worker = None
            interface.enqueue_notification("Shell result", "Completed", "success", "s:1", "shell")
            interface.enqueue_notification("Download started", "Game", "info", "j:download_started",
                                            "download_started")
            await interface._notification_worker
            self.assertEqual(delivered, [("Shell result", "start"), ("Shell result", "end"),
                                         ("Download started", "start"), ("Download started", "end")])

        asyncio.run(exercise())

    def test_queue_continues_after_presenter_failure_and_keeps_repeated_shell_events(self):
        async def exercise():
            interface = object.__new__(ConsoleInterface)
            delivered = []
            event_ids = []

            async def unreliable_presenter(event):
                event_ids.append(event.event_id)
                if len(event_ids) == 1:
                    raise RuntimeError("presenter unavailable")
                delivered.append(event.title)

            interface._notification_presenter = unreliable_presenter
            interface._notification_queue = asyncio.Queue()
            interface._notification_worker = None
            interface.enqueue_notification("Refresh complete", "Done", "success")
            interface.enqueue_notification("Refresh complete", "Done", "success")
            await interface._notification_worker
            self.assertNotEqual(event_ids[0], event_ids[1])
            self.assertEqual(delivered, ["Refresh complete"])

        asyncio.run(exercise())


if __name__ == "__main__":
    unittest.main()
