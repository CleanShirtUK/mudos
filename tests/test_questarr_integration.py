from pathlib import Path
import tempfile
import unittest

from lulu.provider_config import ProviderConfigurationService
from lulu.prowlarr_admin import migrate_temporary_key


ROOT = Path(__file__).parents[1]


class QuestarrIntegrationTests(unittest.TestCase):
    def test_fixed_home_card_uses_existing_browser_store_path(self) -> None:
        store = (ROOT / "ui/StoreHome.qml").read_text()
        shell = (ROOT / "ui/ConsoleShell.qml").read_text()
        card = (ROOT / "config/plugins/questarr/store-card.json").read_text()
        self.assertIn('"id":"questarr"', card)
        self.assertIn('"url":"http://127.0.0.1:5000/"', card)
        self.assertNotIn('id: "questarr", title: "Questarr"', store)
        admin = (ROOT / "src/lulu/admin_web.py").read_text()
        self.assertIn('("questarr", "Questarr", "lulu-questarr.service", "http", 5000, "/", True', admin)
        self.assertIn("function launchHomeStore", shell)

    def test_questarr_service_is_pinned_and_persistent(self) -> None:
        unit = (ROOT / "packaging/lulu-questarr.service").read_text()
        self.assertIn("ghcr.io/doezer/questarr@sha256:", unit)
        self.assertIn("/var/lib/lulu-questarr/data:/app/data", unit)
        self.assertIn("/home/lulu/Games/.acquisition/torrents", unit)
        self.assertIn("/home/lulu/Games/.acquisition/usenet", unit)

    def test_admin_registry_exposes_questarr_health_and_ui(self) -> None:
        admin = (ROOT / "src/lulu/admin_web.py").read_text()
        self.assertIn('("questarr", "Questarr", "lulu-questarr.service"', admin)
        self.assertIn('"/api/health"', admin)
        self.assertIn("service_health", admin)

    def test_persistent_prowlarr_config_uses_secret_reference(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            class FakeSecrets:
                def __init__(self):
                    self.values = {}

                def put(self, namespace, name, value):
                    self.values[(namespace, name)] = value

                def configured(self, namespace, name):
                    return (namespace, name) in self.values

                def get(self, namespace, name):
                    return self.values.get((namespace, name))

            secrets = FakeSecrets()
            service = ProviderConfigurationService(
                system_path=root / "missing-system.toml",
                user_path=root / "provider-services.toml",
                secrets=secrets,
            )
            handoff = root / "handoff.rtf"
            handoff.write_text(r"{\rtf1 AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA}")
            migrate_temporary_key(handoff, service)
            configured = service.provider("providers.prowlarr")
            self.assertEqual(configured.get("endpoint"), "http://192.168.0.197:9696/")
            self.assertEqual(configured.secret_refs["api_key"], "prowlarr/api-key")
            self.assertTrue(configured.secret_available("api_key"))
            self.assertNotIn("AAAAAAAA", (root / "provider-services.toml").read_text())

    def test_admin_exposes_prowlarr_without_secret_value(self) -> None:
        admin = (ROOT / "src/lulu/admin_web.py").read_text()
        self.assertIn('("providers.prowlarr", "Prowlarr")', admin)
        self.assertIn('"/api/v1/system/status"', admin)
        self.assertNotIn("PROWLARR_API_KEY", admin)

    def test_downloader_markers_match_mudos_provenance_contract(self) -> None:
        transmission = (ROOT / "src/lulu/plugins/torrent/transmission.py").read_text()
        nzbget = (ROOT / "src/lulu/plugins/usenet/nzbget.py").read_text()
        self.assertIn('label.casefold() == "questarr"', transmission)
        self.assertIn('item.category.casefold() == "questarr"', nzbget)

    def test_reconciler_uses_supported_api_and_stable_ownership_markers(self) -> None:
        reconciler = (ROOT / "src/lulu/questarr_reconciler.py").read_text()
        unit = (ROOT / "packaging/lulu-questarr-reconcile.service").read_text()
        self.assertIn('"/api/auth/login"', reconciler)
        self.assertIn('"/api/downloaders"', reconciler)
        self.assertIn('"/api/indexers/prowlarr/sync"', reconciler)
        self.assertIn('"mudos.questarr"', reconciler)
        self.assertIn("User=lulu", unit)
        self.assertNotIn("sqlite", reconciler.lower())

    def test_reconciler_has_no_secret_logging_or_public_token_state(self) -> None:
        reconciler = (ROOT / "src/lulu/questarr_reconciler.py").read_text()
        self.assertNotIn("print(token", reconciler)
        self.assertNotIn("LOGGER.info(token", reconciler)
        self.assertIn("self.token", reconciler)

    def test_questarr_credential_trigger_has_narrow_polkit_authority(self) -> None:
        rule = (ROOT / "packaging/polkit-1/rules.d/53-lulu-questarr-reconcile.rules").read_text()
        self.assertIn('subject.user == "lulu"', rule)
        self.assertIn('unit") == "lulu-questarr-reconcile.service"', rule)
        self.assertIn('verb") == "start"', rule)


if __name__ == "__main__":
    unittest.main()
