import unittest

from lulu.web_credentials import WebCredentialStore, exact_origin


class MemorySecrets:
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


class WebCredentialTests(unittest.TestCase):
    def test_exact_origin_normalization_does_not_expand_trust(self):
        self.assertEqual(exact_origin("http://127.0.0.1:5000/login"), "http://127.0.0.1:5000")
        self.assertEqual(exact_origin("http://127.0.0.1.evil.example:5000/"),
                         "http://127.0.0.1.evil.example:5000")
        self.assertEqual(exact_origin("https://127.0.0.1:5000/"), "https://127.0.0.1:5000")

    def test_questarr_credentials_are_not_exposed_to_the_browser(self):
        secrets = MemorySecrets()
        store = WebCredentialStore(secrets)
        with self.assertRaises(ValueError):
            store.get("questarr", "http://127.0.0.1:5000/")
        with self.assertRaises(ValueError):
            store.save("questarr", "http://127.0.0.1:5000", "user", "password")
        self.assertFalse(secrets.values)

    def test_custom_store_and_wrong_origin_cannot_read_or_write(self):
        store = WebCredentialStore(MemorySecrets())
        for profile, origin in (("", "http://127.0.0.1:5000"),
                                ("questarr", "http://localhost:5000"),
                                ("questarr", "http://127.0.0.1:5001"),
                                ("questarr", "https://127.0.0.1:5000")):
            with self.assertRaises(ValueError):
                store.get(profile, origin)
            with self.assertRaises(ValueError):
                store.save(profile, origin, "user", "password")
