from pathlib import Path
import unittest
import asyncio

from lulu.consoled import ConsoleInterface


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

    def test_library_refresh_has_completion_notice_not_start_chatter(self):
        shell = (ROOT / "ui/ConsoleShell.qml").read_text()
        self.assertIn('root.notify("Library refreshed", "Your catalogue is up to date", "success")', shell)
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
