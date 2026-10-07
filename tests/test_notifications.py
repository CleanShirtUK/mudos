import asyncio
from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest

from lulu.jobs import DownloadJob, JobError, JobOperation, JobState
from lulu.notifications import (Notification, NotificationBroker, NotificationPresenter,
                                SEVERITY_LIFETIMES, validate_notification)


def job(job_id: str = "job-1", *, state: JobState = JobState.QUEUED,
        operation: JobOperation = JobOperation.INSTALL) -> DownloadJob:
    return DownloadJob(job_id=job_id, provider="synthetic", title="Example Game",
                       content_identity="synthetic:example", state=state,
                       operation=operation, progress=1.0 if state is JobState.COMPLETED else None)


class NotificationBrokerTests(unittest.IsolatedAsyncioTestCase):
    async def test_severity_payload_validation_and_bounded_policy(self) -> None:
        for severity, duration in {"info": 4, "success": 4, "warning": 6, "error": 8}.items():
            validate_notification("Title", "Body", severity)
            self.assertEqual(SEVERITY_LIFETIMES[severity], duration)
            self.assertLessEqual(duration, 8)
        for title, body, severity in [("", "Body", "info"), ("Title", "", "info"),
                                      ("Title", "Body", "urgent"), ("x" * 121, "Body", "error")]:
            with self.assertRaises(ValueError):
                validate_notification(title, body, severity)

    async def test_shell_notifications_have_unique_ids_and_deterministic_lifetime(self) -> None:
        first = NotificationBroker.shell_event("Library refreshed", "Up to date", "success")
        second = NotificationBroker.shell_event("Library refreshed", "Up to date", "success")
        self.assertNotEqual(first.event_id, second.event_id)
        self.assertEqual(first.duration, 4)
        self.assertEqual(first.severity, "success")

    async def test_presenter_failure_does_not_fail_source_transition(self) -> None:
        async def failing_sink(event: Notification) -> None:
            raise RuntimeError("display unavailable")

        broker = NotificationBroker(failing_sink)
        initial = job(state=JobState.STARTING)
        broker.seed([initial])
        broker.observe([replace(initial, state=JobState.FAILED,
                                error=JobError("failure", "failure"))])
        await broker.drain()
        self.assertEqual(broker.pending, ())

    async def test_failure_notifies_once_with_reason_and_retry_guidance(self) -> None:
        broker = NotificationBroker()
        initial = job(state=JobState.STARTING)
        broker.seed([initial])
        failed = replace(initial, state=JobState.FAILED,
                         error=JobError("unsupported-platform", "No emulator maps this platform"))
        broker.observe([failed])
        broker.observe([failed])
        self.assertEqual(len(broker.pending), 1)
        event = broker.pending[0]
        self.assertEqual(event.event_type, "acquisition_failed")
        self.assertEqual(event.title, "Installation failed")
        self.assertIn("No emulator maps this platform", event.body)
        self.assertNotIn("to retry", event.body)
        broker.seed([failed])
        broker.observe([failed])
        self.assertEqual(len(broker.pending), 1)

    async def test_failed_removal_is_not_reported_as_a_download(self) -> None:
        broker = NotificationBroker()
        initial = replace(job(state=JobState.STARTING), operation=JobOperation.REMOVE)
        broker.seed([initial])
        broker.observe([replace(initial, state=JobState.FAILED,
                                error=JobError("remove-failed", "Cannot remove files.", retryable=True))])
        self.assertEqual(broker.pending[0].title, "Removal failed")
        self.assertIn("Cannot remove files. Open Downloads to retry.", broker.pending[0].body)

    async def test_fifo_and_one_at_a_time_sink(self) -> None:
        received: list[str] = []

        async def sink(event: Notification) -> None:
            received.append(event.event_type + ":" + event.body)

        broker = NotificationBroker(sink)
        broker.enqueue(Notification("1", "download_started", "Download started", "One"))
        broker.enqueue(Notification("2", "download_finished", "Download finished", "Two"))
        await broker.drain()
        self.assertEqual(received, ["download_started:One", "download_finished:Two"])

    async def test_state_transitions_emit_once_and_failures_emit_no_success(self) -> None:
        events: list[Notification] = []

        async def sink(event: Notification) -> None:
            events.append(event)

        broker = NotificationBroker(sink)
        queued = job()
        broker.seed([queued])
        transferring = replace(queued, state=JobState.TRANSFERRING)
        broker.observe([transferring])
        broker.observe([transferring])
        finalizing = replace(transferring, state=JobState.FINALIZING)
        broker.observe([finalizing])
        completed = replace(finalizing, state=JobState.COMPLETED, progress=1.0)
        broker.observe([completed])
        await broker.drain()
        self.assertEqual([event.event_type for event in events], [
            "download_started", "download_finished", "installation_succeeded",
        ])
        self.assertEqual(len({event.event_id for event in events}), 3)

        failed = replace(job("job-failed"), state=JobState.FAILED)
        broker.seed([failed])
        broker.observe([replace(failed, state=JobState.COMPLETED, progress=1.0)])
        await broker.drain()
        self.assertEqual(len(events), 3)

    async def test_startup_completed_jobs_do_not_replay(self) -> None:
        events: list[Notification] = []

        async def sink(event: Notification) -> None:
            events.append(event)

        broker = NotificationBroker(sink)
        broker.seed([job(state=JobState.COMPLETED)])
        broker.observe([job(state=JobState.COMPLETED)])
        await broker.drain()
        self.assertEqual(events, [])

    async def test_acquire_completion_is_download_only(self) -> None:
        events: list[Notification] = []

        async def sink(event: Notification) -> None:
            events.append(event)

        broker = NotificationBroker(sink)
        initial = job(operation=JobOperation.ACQUIRE)
        broker.seed([initial])
        broker.observe([replace(initial, state=JobState.TRANSFERRING)])
        broker.observe([replace(initial, state=JobState.FINALIZING)])
        broker.observe([replace(initial, state=JobState.COMPLETED, progress=1.0)])
        await broker.drain()
        self.assertEqual([event.event_type for event in events], [
            "download_started", "download_finished",
        ])

    async def test_presenter_passes_deployed_ui_path_and_receives_event(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            executable = Path(directory) / "presenter.py"
            output = Path(directory) / "event.json"
            executable.write_text(
                "#!/usr/bin/env python3\n"
                "import json, os, sys\n"
                "assert os.environ['LULU_NOTIFICATION_UI_FILE'].endswith('/ui/MudosNotification.qml')\n"
                "first = sys.stdin.readline()\n"
                "with open(os.environ['OUTPUT'], 'w') as f: f.write(first)\n"
                "sys.stdin.readline()\n"
            )
            executable.chmod(0o755)
            presenter = NotificationPresenter(str(executable), duration=0)
            import os
            old = os.environ.get("OUTPUT")
            os.environ["OUTPUT"] = str(output)
            try:
                await presenter(Notification("event-1", "installation_succeeded",
                                             "Installed successfully", "Example is ready"))
                for _ in range(20):
                    if output.exists():
                        break
                    await asyncio.sleep(0.05)
            finally:
                if old is None:
                    os.environ.pop("OUTPUT", None)
                else:
                    os.environ["OUTPUT"] = old
            self.assertEqual(json.loads(output.read_text())["event_id"], "event-1")


if __name__ == "__main__":
    unittest.main()
