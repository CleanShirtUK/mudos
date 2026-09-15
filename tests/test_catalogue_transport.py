import json
import unittest

from dbus_next import Message, MessageType

from lulu.catalogue import CatalogueDelta, CatalogueGame
from lulu.consoled import ConsoleInterface


class CatalogueTransportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.interface = ConsoleInterface(object())
        self.game = CatalogueGame(
            game_id="steam:1", provider="steam", provider_id="1", title="One",
            platform="Steam", install_state="installed", launchable=True,
            install_dir="/games/one", artwork_url="", last_played=0,
        )

    def test_generation_only_advances_for_nonempty_batches(self) -> None:
        self.interface._publish_delta_batches([[]])
        self.assertEqual(self.interface._catalogue_generation, 0)
        self.interface._publish_delta_batches([[
            CatalogueDelta("insert", self.game.game_id, after=self.game)
        ]])
        self.assertEqual(self.interface._catalogue_generation, 1)
        needs_resync, payload = self.interface._get_catalogue_changes(0)
        self.assertFalse(needs_resync)
        batches = json.loads(payload)
        self.assertEqual([batch["generation"] for batch in batches], [1])
        self.assertEqual(batches[0]["deltas"][0]["after"]["game_id"], "steam:1")

    def test_multi_delta_batch_has_one_generation_and_serializes_authoritative_values(self) -> None:
        after = CatalogueGame(
            game_id="steam:1", provider="steam", provider_id="1", title="Updated",
            platform="Steam", install_state="installed", launchable=True,
            install_dir="/games/one", artwork_url="", last_played=42,
        )
        self.interface._publish_delta_batches([[
            CatalogueDelta("update", self.game.game_id, before=self.game, after=after,
                            changed_fields=("last_played", "title")),
            CatalogueDelta("insert", "local:2", after=self.game),
        ]])
        self.assertEqual(self.interface._catalogue_generation, 1)
        _, payload = self.interface._get_catalogue_changes(0)
        batch = json.loads(payload)[0]
        self.assertEqual(batch["generation"], 1)
        self.assertEqual(len(batch["deltas"]), 2)
        self.assertEqual(batch["deltas"][0]["changed_fields"], ["last_played", "title"])
        self.assertEqual(batch["deltas"][0]["after"]["last_played"], 42)

    def test_expired_history_requires_snapshot_resync(self) -> None:
        self.interface._delta_history.clear()
        self.interface._catalogue_generation = 300
        self.interface._delta_history.append((300, []))
        needs_resync, payload = self.interface._get_catalogue_changes(1)
        self.assertTrue(needs_resync)
        self.assertEqual(payload, "[]")

    def test_snapshot_return_body_is_accepted_by_dbus_struct_marshaller(self) -> None:
        class Store:
            def list_catalogue_games(self):
                return []

        self.interface.catalogue = type("Catalogue", (), {"store": Store()})()
        body = self.interface._get_catalogue_snapshot()
        message = Message(
            message_type=MessageType.METHOD_RETURN, reply_serial=1,
            signature="(ts)", body=[body], serial=1,
        )
        message._marshall()

    def test_changes_return_body_is_accepted_by_dbus_struct_marshaller(self) -> None:
        body = self.interface._get_catalogue_changes(0)
        message = Message(
            message_type=MessageType.METHOD_RETURN, reply_serial=1,
            signature="(bs)", body=[body], serial=1,
        )
        message._marshall()


if __name__ == "__main__":
    unittest.main()
