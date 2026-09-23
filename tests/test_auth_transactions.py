import time
import unittest

from lulu.auth_transactions import AuthTransactionState, AuthTransactionStore


class AuthTransactionTests(unittest.TestCase):
    def test_public_state_contains_handoff_metadata_but_not_expiry(self) -> None:
        store = AuthTransactionStore(ttl=60)
        item = store.create("gog", "auth_browser", verification_url="https://example.test/login")
        public = item.public()
        self.assertEqual(public["provider"], "gog")
        self.assertEqual(public["state"], "waiting_for_user")
        self.assertEqual(public["verification_url"], "https://example.test/login")
        self.assertNotIn("expiry", public)

    def test_transactions_are_ephemeral_and_expire(self) -> None:
        store = AuthTransactionStore(ttl=1)
        item = store.create("steam", "auth_credentials")
        store.update(item.transaction_id, AuthTransactionState.WAITING_FOR_2FA)
        self.assertEqual(store.get(item.transaction_id).state, AuthTransactionState.WAITING_FOR_2FA)
        item.expiry = time.time() - 1
        self.assertEqual(store.get(item.transaction_id).state, AuthTransactionState.EXPIRED)
