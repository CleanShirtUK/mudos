import asyncio
import unittest

from lulu.sessiond import ConsoleSessionInterface, _wait_for_stop


class SessiondTests(unittest.TestCase):
    def test_cancel_launch_delegates_to_supervisor(self) -> None:
        interface = ConsoleSessionInterface.__new__(ConsoleSessionInterface)

        class Supervisor:
            def __init__(self) -> None:
                self.cancelled = False

            async def cancel_launch(self) -> None:
                self.cancelled = True

        supervisor = Supervisor()
        interface.supervisor = supervisor

        asyncio.run(ConsoleSessionInterface.CancelLaunch.__wrapped__(interface))

        self.assertTrue(supervisor.cancelled)

    def test_idle_session_waits_for_explicit_stop_signal(self) -> None:
        async def exercise() -> None:
            stop_event = asyncio.Event()
            task = asyncio.create_task(_wait_for_stop(stop_event))
            await asyncio.sleep(0)
            self.assertFalse(task.done())
            stop_event.set()
            await task
            self.assertTrue(task.done())

        asyncio.run(exercise())


if __name__ == "__main__":
    unittest.main()
