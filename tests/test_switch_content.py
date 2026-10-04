from pathlib import Path
import unittest

from lulu.switch_content import (
    GameContentComponent, SwitchContentRole, canonical_identity,
    component_from_provider, role_from_metadata, role_from_unstructured_name, title_id,
)


class SwitchContentModelTests(unittest.TestCase):
    def test_components_share_one_parent_identity(self) -> None:
        identity = canonical_identity(parent_game_id="acquisition:game:smash")
        components = [
            GameContentComponent(identity, "switch", role, "acquisition", str(i),
                                 title_id=f"0100152000022{i:03d}", parent_game_id=identity)
            for i, role in enumerate((SwitchContentRole.BASE, SwitchContentRole.UPDATE,
                                      SwitchContentRole.DLC), 1)
        ]
        self.assertEqual({item.game_identity for item in components}, {identity})
        self.assertEqual({item.role for item in components}, set(SwitchContentRole))

    def test_provider_role_wins_over_filename(self) -> None:
        self.assertEqual(role_from_metadata({"downloadType": "update"}), SwitchContentRole.UPDATE)
        self.assertEqual(role_from_metadata({"category": "dlc"}), SwitchContentRole.DLC)
        self.assertIsNone(role_from_metadata({"downloadType": "torrent"}))

    def test_name_is_only_fallback(self) -> None:
        self.assertEqual(role_from_unstructured_name("Mario Kart Update v1.2.nsp"), SwitchContentRole.UPDATE)
        self.assertEqual(role_from_unstructured_name("Booster Course Pass.nsp"), SwitchContentRole.DLC)
        self.assertEqual(role_from_unstructured_name("Mario Kart Base.nsp"), SwitchContentRole.BASE)
        self.assertIsNone(role_from_unstructured_name("Mario Kart NSP + Update + DLC"))

    def test_title_id_and_parent_resolution_are_explicit(self) -> None:
        self.assertEqual(title_id("Mario [0100152000022000][v0].nsp"), "0100152000022000")
        self.assertEqual(canonical_identity(base_title_id="0100152000022000"),
                         "switch:0100152000022000")
        self.assertNotEqual(canonical_identity(base_title_id="0100152000022000"),
                            canonical_identity(base_title_id="0100152000022800"))

    def test_acquisition_protocol_is_not_mistaken_for_content_role(self) -> None:
        component = component_from_provider(
            source="acquisition", source_id="download-1", parent_game_id="acquisition:game:1",
            metadata={"downloadType": "torrent", "role": "update", "downloadHash": "hash-1",
                      "version": "13.0.2"}, filename="release.nsp")
        self.assertEqual(component.role, SwitchContentRole.UPDATE)
        self.assertEqual(component.provider_job_id, "hash-1")
        with self.assertRaises(ValueError):
            component_from_provider(source="acquisition", source_id="download-2",
                                    parent_game_id="acquisition:game:1",
                                    metadata={"downloadType": "torrent"},
                                    filename="NSP + Update + DLC")
