import hashlib
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
        launcher = (ROOT / "scripts/mudos-questarr").read_text()
        self.assertIn("ExecStart=/opt/lulu/current/bin/mudos-questarr", unit)
        self.assertIn("questarr-image-ref", launcher)
        self.assertIn("verified-image-id", launcher)
        self.assertIn("/var/lib/lulu-questarr/data:/app/data", launcher)
        self.assertIn("PATHS.torrent_root", launcher)
        self.assertIn("PATHS.usenet_root", launcher)
        self.assertIn("PATHS.usenet_complete_root", launcher)
        self.assertIn("questarr_library_mounts", launcher)
        self.assertIn("/home/lulu/Games/.acquisition/usenet/complete:rw", launcher)
        self.assertIn('"${library_volumes[@]}"', launcher)
        self.assertIn("PORT=5002", launcher)
        self.assertIn("HOST=127.0.0.1", launcher)

    def test_mudos_questarr_downstream_patch_is_source_pinned_and_reproducible(self) -> None:
        lock = (ROOT / "packages/questarr/IMAGE.lock").read_text()
        patch = (ROOT / "packages/questarr/patches/0001-nzbget-history-destdir-download-dir.patch").read_text()
        builder = (ROOT / "scripts/build-questarr-image.sh").read_text()
        containerfile = (ROOT / "packages/questarr/Containerfile").read_text()
        runtime_verifier = (ROOT / "scripts/verify-questarr-runtime.mjs").read_text()
        firewall = (ROOT / "scripts/configure-questarr-firewall.sh").read_text()
        self.assertIn("upstream_git_commit=0320b6f3123532e77346292a2d0836e6582f6010", lock)
        self.assertIn("upstream_image=ghcr.io/doezer/questarr@sha256:6faaf75f484a20805309315dd9eb9f1550b039a668efb89c13fc028c72b45485", lock)
        self.assertIn("image_digest=sha256:b460c1209c2a6047df58ad4eab35aba5eb20d58a08c86a955f3cce8b1c9e23c6", lock)
        self.assertIn("DestDir", patch)
        self.assertIn("downloadDir", patch)
        locked_patch_sha = next(line.split("=", 1)[1] for line in lock.splitlines()
                                if line.startswith("patch_sha256="))
        self.assertEqual(hashlib.sha256(
            (ROOT / "packages/questarr/patches/0001-nzbget-history-destdir-download-dir.patch")
            .read_bytes()).hexdigest(), locked_patch_sha)
        self.assertIn('apply "$package_root/patches/', builder)
        self.assertIn("--no-cache --timestamp", builder)
        self.assertIn("FROM ${UPSTREAM_IMAGE}", containerfile)
        self.assertIn("--config vitest.config.ts", containerfile)
        self.assertIn("!vitest.config.ts", builder)
        self.assertIn("ufw route allow in on podman0", firewall)
        self.assertIn('from "$podman_subnet"', firewall)
        release = (ROOT / "scripts/release.py").read_text()
        self.assertIn('"packages")', release)
        self.assertIn("getDownloadDetails", runtime_verifier)
        self.assertIn("access(importerPath", runtime_verifier)

    def test_auth_proxy_and_acquisition_gateway_own_the_public_boundaries(self) -> None:
        proxy = (ROOT / "src/lulu/questarr_auth_proxy.py").read_text()
        gateway = (ROOT / "src/lulu/questarr_gateway.py").read_text()
        unit = (ROOT / "packaging/lulu-questarr-auth-proxy.service").read_text()
        pam_unit = (ROOT / "packaging/lulu-questarr-pam-auth.service").read_text()
        acquisitiond = (ROOT / "src/lulu/acquisitiond.py").read_text()
        self.assertIn("_pam_helper_authenticate", proxy)
        self.assertIn("/api/auth/setup", proxy)
        self.assertIn("PUBLIC_PORT = 5000", proxy)
        self.assertIn("UPSTREAM = \"http://127.0.0.1:5002\"", proxy)
        self.assertIn("GetUsenetReadiness", (ROOT / "src/lulu/admin_web.py").read_text())
        self.assertIn("origin=\"questarr\"", gateway)
        self.assertIn('serve_gateway(questarr_gateway)', acquisitiond)
        self.assertIn("User=lulu", unit)
        self.assertIn("LULU_QUESTARR_PAM_ACCOUNT=josh", unit)
        self.assertIn("NoNewPrivileges=true", unit)
        self.assertIn("NoNewPrivileges=true", pam_unit)
        self.assertIn("CAP_DAC_OVERRIDE", pam_unit)
        self.assertIn("Requires=lulu-questarr.service lulu-questarr-pam-auth.service", unit)
        self.assertIn("ReadWritePaths=/run/lulu-questarr-pam /run/faillock", pam_unit)

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
        self.assertIn('"http://127.0.0.1:5001"', reconciler)
        self.assertNotIn('"http://127.0.0.1:9091/transmission/rpc"', reconciler)
        self.assertNotIn('torrent.secret("password")', reconciler)

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
