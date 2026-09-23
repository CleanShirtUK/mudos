import asyncio
from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest

from lulu.jobs import DownloadJob, JobOperation, JobState
from lulu.notifications import Notification, NotificationBroker, NotificationPresenter


def job(job_id: str = "job-1", *, state: JobState = JobState.QUEUED,
        operation: JobOperation = JobOperation.INSTALL) -> DownloadJob:
    return DownloadJob(job_id=job_id, provider="synthetic", title="Example Game",
                       content_identity="synthetic:example", state=state,
                       operation=operation, progress=1.0 if state is JobState.COMPLETED else None)


class NotificationBrokerTests(unittest.IsolatedAsyncioTestCase):
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
                await asyncio.sleep(0.05)
            finally:
                if old is None:
                    os.environ.pop("OUTPUT", None)
                else:
                    os.environ["OUTPUT"] = old
            self.assertEqual(json.loads(output.read_text())["event_id"], "event-1")


if __name__ == "__main__":
    unittest.main()
