import tempfile
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


if __name__ == "__main__":
    unittest.main()
