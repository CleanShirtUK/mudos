import tempfile
import unittest
from pathlib import Path

from lulu.plugins import ComponentDescriptor, ComponentRegistry, PluginRegistry, PluginSecretBoundary


class FakeSecrets:
    def __init__(self):
        self.values = {}

    def configured(self, namespace, name):
        return (namespace, name) in self.values

    def get(self, namespace, name):
        return self.values.get((namespace, name))

    def put(self, namespace, name, value):
        self.values[(namespace, name)] = value

    def clear(self, namespace, name):
        self.values.pop((namespace, name), None)


class PluginFrameworkTests(unittest.TestCase):
    def _root(self):
        directory = tempfile.TemporaryDirectory()
        root = Path(directory.name)
        for plugin_id, manifest in {
            "base": '''id = "base"\nname = "Base"\nversion = "1"\napi_version = 1\ntypes = ["service"]\n[capabilities]\nservice = true\n''',
            "alternative": '''id = "alternative"\nname = "Alternative"\nversion = "1"\napi_version = 1\ntypes = ["downloader"]\n[capabilities]\nservice = true\n''',
            "consumer": '''id = "consumer"\nname = "Consumer"\nversion = "1"\napi_version = 1\ndescription = "Synthetic third-party plugin"\ntypes = ["catalogue", "store"]\n[capabilities]\nstore = true\nservice = true\n[dependencies]\nrequires_all = ["base"]\nrequires_any = [["alternative", "missing-downloader"]]\n[[store_cards]]\nid = "synthetic"\nlabel = "Synthetic Store"\nurl = "https://example.test/store"\nremovable = false\n[[secrets]]\nslot = "token"\nlabel = "Private token"\nrequired = true\n[configuration.fields.endpoint]\ntype = "url"\nlabel = "Server address"\nrequired = true\n''',
        }.items():
            path = root / plugin_id
            path.mkdir()
            (path / "plugin.toml").write_text(manifest)
            (path / "plugin.py").write_text("def register(context):\n    context.register('service', {'id': context.manifest.plugin_id})\n")
        return directory, root

    def test_discovery_manifest_schema_and_synthetic_store_contribution(self):
        directory, root = self._root()
        with directory:
            registry = PluginRegistry(root)
            records = registry.discover()
            consumer = next(item for item in records if item.manifest.plugin_id == "consumer")
            self.assertEqual(consumer.health, "available")
            self.assertEqual(consumer.manifest.configuration[0].label, "Server address")
            self.assertTrue(consumer.manifest.secrets[0].required)
            self.assertEqual(registry.store_cards()[0].card_id, "synthetic")
            self.assertNotIn("token", str(registry.status()))

    def test_dependency_requires_all_and_any_are_directional(self):
        directory, root = self._root()
        with directory:
            registry = PluginRegistry(root)
            registry.discover()
            plan = registry.resolve_selection({"consumer"})
            self.assertEqual(plan.selected, ("alternative", "base", "consumer"))
            self.assertEqual(plan.ordered[-1], "consumer")
            components = ComponentRegistry(registry)
            components.discover()
            self.assertEqual(components.resolve_selection({"consumer"}), plan)
            self.assertEqual(registry.resolve_selection({"base"}).selected, ("base",))

    def test_missing_any_group_is_reported_without_selecting_reverse_dependents(self):
        directory, root = self._root()
        with directory:
            (root / "alternative" / "plugin.toml").unlink()
            registry = PluginRegistry(root)
            registry.discover()
            plan = registry.resolve_selection({"consumer"})
            components = ComponentRegistry(registry)
            components.discover()
            self.assertEqual(components.resolve_selection({"consumer"}), plan)
            self.assertEqual(plan.missing_any, (("consumer", ("alternative", "missing-downloader")),))
            self.assertEqual(registry.resolve_selection({"base"}).selected, ("base",))

    def test_generic_secret_boundary_uses_plugin_namespace_without_exposure(self):
        secrets = FakeSecrets()
        boundary = PluginSecretBoundary("synthetic", secrets)
        self.assertEqual(boundary.reference("token"), "synthetic/token")
        boundary.put("token", "not-rendered")
        self.assertTrue(boundary.configured("token"))
        self.assertNotIn("not-rendered", repr(boundary.reference("token")))
        boundary.clear("token")
        self.assertFalse(boundary.configured("token"))

    def test_real_plugin_manifests_declare_core_contributions(self):
        registry = PluginRegistry(Path(__file__).parents[1] / "config" / "plugins")
        registry.discover()
        self.assertEqual({card.card_id for card in registry.store_cards()}, {"flathub"})
        self.assertEqual(next(card for card in registry.store_cards() if card.card_id == "flathub").glyph, "f324")
        services = {service.service_id for service in registry.services()}
        self.assertTrue({"transmission", "nzbget"} <= services)
        self.assertNotIn("questarr", services)
        components = ComponentRegistry(registry)
        components.discover()
        self.assertNotIn("questarr", {item.component_id for item in components.all()})
        self.assertTrue({"transmission", "nzbget"} <= {item.service_id for item in registry.services()})
        from lulu.onboarding import provider_manifest
        providers = {row["id"] for row in provider_manifest(components)}
        self.assertNotIn("questarr", providers)
        self.assertTrue({"torrent", "usenet"} <= providers)

    def test_flatpak_is_a_plugin_component_without_core_store_ui_assumptions(self):
        registry = PluginRegistry(Path(__file__).parents[1] / "config" / "plugins")
        registry.discover()
        components = ComponentRegistry(registry)
        components.discover()
        flatpak = components.get("flatpak")
        self.assertEqual(flatpak.kind, "plugin")
        self.assertIn("launch", flatpak.capabilities)
        self.assertEqual(flatpak.secrets, ())
        self.assertEqual(components.resolve_selection({"flatpak"}).selected, ("flatpak",))
        disabled = PluginRegistry(Path(__file__).parents[1] / "config" / "plugins", enabled={"flatpak": False})
        disabled.discover()
        disabled_components = ComponentRegistry(disabled)
        disabled_components.discover()
        self.assertNotIn("flathub", {card.card_id for card in disabled_components.store_cards()})

    def test_browser_handoff_claim_is_declarative_and_origin_scoped(self):
        registry = PluginRegistry(Path(__file__).parents[1] / "config" / "plugins")
        registry.discover()
        trusted = registry.claim_browser_handoff(
            "flatpak+https://dl.flathub.org/repo/appstream/org.openttd.OpenTTD.flatpakref",
            "https://flathub.org")
        self.assertIsNotNone(trusted)
        self.assertTrue(trusted[3])
        self.assertFalse(registry.claim_browser_handoff(
            "unknown+https://example.test/file", "https://example.test"))
        untrusted = registry.claim_browser_handoff(
            "flatpak+https://example.test/file.flatpakref", "https://example.test")
        self.assertIsNotNone(untrusted)
        self.assertFalse(untrusted[3])

    def test_unified_component_registry_combines_builtin_and_plugin_components(self):
        directory, root = self._root()
        with directory:
            plugins = PluginRegistry(root)
            plugins.discover()
            builtin = ComponentDescriptor("builtin-test", "Built-in test provider", "A synthetic built-in.", "builtin_provider")
            components = ComponentRegistry(plugins, builtins=(builtin,))
            discovered = components.discover()
            self.assertEqual({item.component_id for item in discovered}, {"builtin-test", "base", "alternative", "consumer"})
            self.assertEqual(components.get("builtin-test").kind, "builtin_provider")
            self.assertEqual(components.get("consumer").kind, "plugin")
            self.assertEqual(components.store_cards()[0].card_id, "synthetic")
            setup = components.setup_records(FakeSecrets())
            consumer_setup = next(item for item in setup if item["id"] == "consumer")
            self.assertEqual(consumer_setup["configuration"][0]["label"], "Server address")
            self.assertIn("configured", consumer_setup["secrets"][0])
            self.assertEqual(components.resolve_selection({"builtin-test"}).selected, ("builtin-test",))
