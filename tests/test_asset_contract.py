import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]


class AssetContractTests(unittest.TestCase):
    def test_replaceable_asset_contract_has_canonical_inputs(self) -> None:
        self.assertTrue((ROOT / "docs/asset-contract.md").exists())
        self.assertTrue((ROOT / "ui/assets/portrait-artwork/portrait-placeholder.svg").exists())
        self.assertTrue((ROOT / "ui/assets/ui-glyphs/MANIFEST").exists())
        self.assertTrue((ROOT / "ui/assets/ui-sounds/MANIFEST").exists())
        self.assertTrue((ROOT / "ui/assets/steam/MANIFEST").exists())
        self.assertTrue((ROOT / "packaging/plymouth/lulu/MANIFEST").exists())

    def test_existing_consumers_resolve_assets_relative_to_their_qml(self) -> None:
        controller = (ROOT / "ui/ControllerGlyph.qml").read_text()
        game_card = (ROOT / "ui/GameCard.qml").read_text()
        self.assertIn("Qt.resolvedUrl(\"controllerglyphs/\"", controller)
        self.assertIn("assets/portrait-artwork/portrait-placeholder.svg", game_card)

    def test_payload_sync_script_copies_asset_contract(self) -> None:
        refresh = (ROOT / "scripts/refresh-payload.sh").read_text()
        self.assertIn('cp -a "$root"/ui/assets "$payload/ui/"', refresh)
        self.assertIn('cp -a "$root"/packaging/plymouth "$payload/packaging/"', refresh)
