from types import SimpleNamespace
import unittest

from lulu.gamescope_observer import _event_window_id


class GamescopeObserverEventTests(unittest.TestCase):
    def test_global_x_events_without_window_are_ignored_safely(self) -> None:
        self.assertIsNone(_event_window_id(SimpleNamespace(type=34)))

    def test_window_events_return_their_xid(self) -> None:
        self.assertEqual(_event_window_id(SimpleNamespace(window=SimpleNamespace(id=1234))), 1234)
