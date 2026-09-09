import unittest

from lulu.system_settings import CATEGORIES, SystemSettingsProvider


class SystemSettingsProviderTests(unittest.TestCase):
    def test_categories_are_stable_and_product_facing(self) -> None:
        self.assertEqual(CATEGORIES, ("Display", "Audio", "Network", "Bluetooth", "Controllers", "Storage", "System", "Lulu"))

    def test_each_category_returns_normalized_rows(self) -> None:
        provider = SystemSettingsProvider()
        for category in CATEGORIES:
            rows = provider.list_settings(category)
            self.assertTrue(rows)
            for row in rows:
                self.assertEqual(set(row), {"key", "label", "kind", "value", "detail", "writable"})
                self.assertFalse(row["writable"])

    def test_unknown_category_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            SystemSettingsProvider().list_settings("Unknown")


if __name__ == "__main__":
    unittest.main()
