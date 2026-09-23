import tempfile
import shutil
from pathlib import Path
import unittest

from lulu.plugins import PluginRegistry


class PluginRegistryTests(unittest.TestCase):
    def _plugin(self, root: Path, name: str, body: str = "def register(context):\n    context.register('providers', 'fixture')\n", **extra: str) -> None:
        directory = root / name
        directory.mkdir()
        api_version = extra.get("api_version", "1")
        enabled = extra.get("enabled", "true")
        (directory / "plugin.toml").write_text(
            f'id = "{name}"\nname = "{name.title()}"\nversion = "1"\n'
            f'api_version = {api_version}\nenabled = {enabled}\n\n'
            '[capabilities]\nproviders = true\ncatalogue = true\n'
        )
        (directory / "plugin.py").write_text(body)

    def test_discovery_registration_and_deterministic_order(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._plugin(root, "zeta")
            self._plugin(root, "alpha")
            registry = PluginRegistry(root)
            records = registry.discover()
            self.assertEqual([record.manifest.plugin_id for record in records], ["alpha", "zeta"])
            self.assertEqual(registry.with_capability("providers"), ("fixture", "fixture"))

    def test_disabled_unsupported_and_broken_plugins_are_isolated(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._plugin(root, "disabled", enabled="false")
            self._plugin(root, "broken", body="raise RuntimeError('fixture failure')\n")
            self._plugin(root, "unsupported", api_version="99")
            registry = PluginRegistry(root)
            registry.discover()
            status = {item["id"]: item for item in registry.status()}
            self.assertEqual(status["disabled"]["health"], "disabled")
            self.assertEqual(status["broken"]["health"], "degraded")
            self.assertEqual(status["unsupported"]["health"], "unavailable")
            self.assertEqual(registry.with_capability("providers"), ())

    def test_missing_entrypoint_is_isolated(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._plugin(root, "missing")
            (root / "missing" / "plugin.py").unlink()
            record = PluginRegistry(root).discover()[0]
            self.assertEqual(record.health, "degraded")

    def test_provider_contribution_disappears_when_plugin_is_disabled(self) -> None:
        source = Path(__file__).parents[1] / "config/plugins"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "plugins"
            shutil.copytree(source, root)
            manifest = root / "steam/plugin.toml"
            manifest.write_text(manifest.read_text().replace('api_version = 1', 'api_version = 1\nenabled = false'))
            registry = PluginRegistry(root)
            records = {record.manifest.plugin_id: record for record in registry.discover()}
            self.assertEqual(records["steam"].health, "disabled")
            providers = registry.with_capability("providers")
            self.assertFalse(any(str(path).endswith("/steam/providers") for path in providers))
            self.assertTrue(any(str(path).endswith("/gog/providers") for path in providers))

    def test_empty_user_plugin_root_does_not_mask_shipped_plugins(self) -> None:
        """A settings-only user root must still allow shipped discovery."""
        with tempfile.TemporaryDirectory() as directory:
            user_root = Path(directory) / "user"
            installed_root = Path(directory) / "installed"
            user_root.mkdir()
            installed_root.mkdir()
            self._plugin(installed_root, "steam")
            selected = user_root if any(user_root.glob("*/plugin.toml")) else installed_root
            registry = PluginRegistry(selected)
            self.assertEqual([item.manifest.plugin_id for item in registry.discover()], ["steam"])


if __name__ == "__main__":
    unittest.main()
