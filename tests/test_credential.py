import asyncio
from pathlib import Path
import tempfile
import unittest

from lulu.credential import (CredentialBroker, CredentialInput,
                              CredentialPresentation, CredentialStatus)


class CredentialBrokerTests(unittest.TestCase):
    def test_secret_is_masked_and_never_in_public_state(self) -> None:
        async def scenario():
            broker = CredentialBroker()
            session = await broker.request("Steam", "Password", CredentialInput.SECRET,
                                           min_length=3, max_length=100)
            await broker.submit(session.request.request_id, "distinct-secret-sentinel")
            self.assertNotIn("distinct-secret-sentinel", str(broker.state()))
            self.assertTrue(broker.state()["secret"])
            self.assertEqual(await broker.take_value(session.request.request_id), "distinct-secret-sentinel")
        asyncio.run(scenario())

    def test_multistep_waiting_cancel_and_single_active_request(self) -> None:
        async def scenario():
            broker = CredentialBroker()
            session = await broker.request("Steam Guard", "Code", CredentialInput.CODE,
                                           min_length=5, max_length=5)
            with self.assertRaises(RuntimeError):
                await broker.request("Other", "Value", CredentialInput.TEXT)
            await broker.update(session.request.request_id, CredentialStatus.WAITING, "Waiting for approval")
            self.assertEqual(broker.state()["status"], "waiting")
            await broker.cancel(session.request.request_id)
            self.assertEqual(broker.state()["status"], "cancelled")
        asyncio.run(scenario())

    def test_request_shape_distinguishes_single_line_and_multiline(self) -> None:
        async def scenario():
            broker = CredentialBroker()
            single = await broker.request("URL", "Value", CredentialInput.TEXT)
            self.assertFalse(broker.state()["multiline"])
            await broker.cancel(single.request.request_id)
            multi = await broker.request("Notes", "Value", CredentialInput.TEXT,
                                         multiline=True)
            self.assertTrue(broker.state()["multiline"])

    def test_request_explicit_presentation_is_public_but_not_secret_value(self) -> None:
        async def scenario():
            broker = CredentialBroker()
            session = await broker.request("URL", "Prompt", CredentialInput.TEXT,
                                           presentation=CredentialPresentation.ATTACHED)
            self.assertEqual(broker.state()["presentation"], "attached")
            self.assertNotIn("secret-sentinel", str(broker.state()))
        asyncio.run(scenario())
        asyncio.run(scenario())

    def test_submission_is_terminal_and_cannot_fire_twice(self) -> None:
        async def scenario():
            broker = CredentialBroker()
            session = await broker.request("URL", "Value", CredentialInput.TEXT)
            await broker.submit(session.request.request_id, "value")
            with self.assertRaises(ValueError):
                await broker.submit(session.request.request_id, "duplicate")
            self.assertEqual(await broker.take_value(session.request.request_id), "value")
        asyncio.run(scenario())

    def test_invalid_code_is_rejected_without_retaining_value(self) -> None:
        async def scenario():
            broker = CredentialBroker()
            session = await broker.request("Steam Guard", "Code", CredentialInput.CODE,
                                           min_length=5, max_length=5)
            invalid = "invalid-code-sentinel"
            with self.assertRaises(ValueError):
                await broker.submit(session.request.request_id, invalid)
            self.assertNotIn(invalid, str(broker.state()))
        asyncio.run(scenario())

    def test_owned_request_withdrawal_rejects_stale_submission_and_allows_new_owner(self) -> None:
        async def scenario():
            broker = CredentialBroker()
            first = await broker.request(
                "SteamCMD", "Password", CredentialInput.SECRET,
                owner_id="steam:job-1", owner={"job_id": "job-1", "pid": 41},
            )
            self.assertEqual(broker.state()["owner_id"], "steam:job-1")
            with self.assertRaises(PermissionError):
                await broker.withdraw(first.request.request_id, "steam:job-2")
            await broker.withdraw(first.request.request_id, "steam:job-1", "provider exited")
            with self.assertRaises(ValueError):
                await broker.submit(first.request.request_id, "stale")
            second = await broker.request(
                "SteamCMD", "Password", CredentialInput.SECRET,
                owner_id="steam:job-2", owner={"job_id": "job-2", "pid": 42},
            )
            with self.assertRaises(KeyError):
                await broker.submit(first.request.request_id, "must-not-reach-new-request")
            await broker.submit(second.request.request_id, "current")
            self.assertEqual(await broker.take_value(second.request.request_id), "current")
        asyncio.run(scenario())

    def test_secret_store_uses_encrypted_backend_and_never_exposes_status_value(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fake = root / "systemd-creds"
            fake.write_text("#!/bin/sh\nif [ \"$1\" = encrypt ]; then cp \"$5\" \"$6\"; else cp \"$3\" \"$4\"; fi\n")
            fake.chmod(0o700)
            from lulu.credential import SecretStore
            store = SecretStore(root / "secrets", creds=str(fake))
            store.put("romm", "api-key", "secret-sentinel")
            self.assertTrue(store.configured("romm", "api-key"))
            self.assertEqual(store.get("romm", "api-key"), "secret-sentinel")
            self.assertNotIn("secret-sentinel", str({"configured": store.configured("romm", "api-key")}))
            store.clear("romm", "api-key")
            self.assertFalse(store.configured("romm", "api-key"))
        
    
