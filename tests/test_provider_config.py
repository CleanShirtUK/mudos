import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from lulu.credential import SecretStore
from lulu.provider_config import ProviderConfigurationService


class ProviderConfigurationTests(unittest.TestCase):
    def service(self, directory: str, *, system: str = "", user: str = "",
                override: Path | None = None) -> ProviderConfigurationService:
        root = Path(directory)
        system_path = root / "etc.toml"
        user_path = root / "user.toml"
        system_path.write_text(system)
        user_path.write_text(user)
        return ProviderConfigurationService(
            system_path=system_path,
            user_path=user_path,
            override_path=override,
            secrets=SecretStore(root / "secrets", creds="/bin/false"),
        )

    def test_default_missing_provider_is_disabled(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config = self.service(directory).provider("metadata.igdb")
            self.assertEqual(config.status, "disabled")
            self.assertFalse(config.enabled)
            self.assertFalse(config.configured)

    def test_enabled_provider_without_secret_is_unconfigured(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config = self.service(directory, user="""\n[metadata.igdb]\nenabled = true\nendpoint = "https://example.invalid"\n[metadata.igdb.secrets]\napi_key = "igdb/api-key"\n""").provider("metadata.igdb")
            self.assertEqual(config.status, "unconfigured")
            self.assertEqual(config.get("endpoint"), "https://example.invalid")

    def test_secret_reference_makes_provider_configured_without_exposing_secret(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            service = self.service(directory, user="""\n[metadata.igdb]\nenabled = true\nclient_id = "public-client-id"\n[metadata.igdb.secrets]\nclient_secret = "igdb/client-secret"\n""")
            secret_path = root / "secrets" / "igdb" / "client-secret.cred"
            secret_path.parent.mkdir(parents=True)
            secret_path.write_text("encrypted-placeholder")
            config = service.provider("metadata.igdb")
            self.assertEqual(config.status, "configured")
            self.assertTrue(config.secret_available("client_secret"))
            diagnostics = config.diagnostics()
            self.assertTrue(diagnostics["client_id_present"])
            self.assertNotIn("encrypted-placeholder", json.dumps(diagnostics))

    def test_precedence_is_system_then_user_then_environment_override(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            override = root / "override.toml"
            override.write_text("""\n[metadata.igdb]\nenabled = true\nendpoint = "override"\n""")
            config = self.service(
                directory,
                system="""\n[metadata.igdb]\nenabled = false\nendpoint = "system"\ntimeout = 1\n""",
                user="""\n[metadata.igdb]\nenabled = true\nendpoint = "user"\ntimeout = 2\n""",
                override=override,
            ).provider("metadata.igdb")
            self.assertTrue(config.enabled)
            self.assertEqual(config.get("endpoint"), "override")
            self.assertEqual(config.get("timeout"), 2)

    def test_environment_override_path_is_supported(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            override = root / "override.toml"
            override.write_text("""\n[providers.lutris]\nenabled = true\nendpoint = "dev"\n""")
            with patch.dict("os.environ", {"LULU_PROVIDER_CONFIG": str(override)}):
                config = ProviderConfigurationService.from_environment(
                    system_path=root / "missing-system.toml", user_path=root / "missing-user.toml",
                    secrets=SecretStore(root / "secrets", creds="/bin/false"),
                ).provider("providers.lutris")
            self.assertEqual(config.status, "configured")
            self.assertEqual(config.get("endpoint"), "dev")

    def test_malformed_or_missing_file_is_healthy(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            malformed = root / "bad.toml"
            malformed.write_text("[metadata.igdb\n")
            service = ProviderConfigurationService(system_path=malformed,
                                                    user_path=root / "missing.toml",
                                                    secrets=SecretStore(root / "secrets", creds="/bin/false"))
            self.assertEqual(service.provider("metadata.igdb").status, "disabled")

    def test_plaintext_secret_keys_are_ignored_and_not_logged(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "user.toml"
            path.write_text("""\n[metadata.igdb]\nenabled = true\napi_key = "secret-sentinel"\n""")
            with self.assertLogs("lulu.provider-config", level="WARNING") as logs:
                config = ProviderConfigurationService(system_path=root / "missing.toml",
                                                       user_path=path,
                                                       secrets=SecretStore(root / "secrets", creds="/bin/false")).provider("metadata.igdb")
            self.assertNotIn("secret-sentinel", "\n".join(logs.output))
            self.assertNotIn("secret-sentinel", json.dumps(config.diagnostics()))

    def test_provisioning_is_non_destructive_by_contract(self) -> None:
        script = Path(__file__).parents[1] / "scripts/provision-provider-config.sh"
        source = script.read_text()
        self.assertIn('if [ -e "$destination" ]; then', source)
        self.assertIn("provider-services.toml.example", source)
        self.assertNotIn("secret", source.casefold().replace("secrets", ""))


if __name__ == "__main__":
    unittest.main()
