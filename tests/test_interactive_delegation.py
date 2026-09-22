import asyncio
from pathlib import Path
import unittest

from lulu.console_sessiond import SessionStateModel
from lulu.contracts import InputMode, Lifecycle, Presentation
from lulu.process_supervisor import ProcessSupervisor


class InteractiveDelegationTests(unittest.TestCase):
    def test_owned_interactive_child_uses_compat_and_restores_state(self):
        async def exercise():
            model = SessionStateModel()
            supervisor = ProcessSupervisor(model)
            command = ["/bin/sh", "-c", "sleep 0.01"]
            token = await supervisor.launch(
                command, 1000, primary_id="provider:lutris:install:fixture",
                presentation=Presentation.FOREIGN_UI, input_mode=InputMode.COMPAT,
                presentation_controller=None,
            )
            model.state.delegated_surface = "install"
            self.assertEqual(model.state.lifecycle, Lifecycle.GAME)
            self.assertEqual(model.state.input_mode, InputMode.COMPAT)
            self.assertEqual(model.state.delegated_surface, "install")
            await supervisor._watch_task
            self.assertEqual(model.state.lifecycle, Lifecycle.SHELL)
            self.assertEqual(model.state.input_mode, InputMode.SHELL)
            self.assertIsNone(model.state.delegated_surface)
            self.assertEqual(model.last_result.token, token)

        asyncio.run(exercise())


if __name__ == "__main__":
    unittest.main()
