import unittest

from lulu.system_settings import CATEGORIES, SystemSettingsProvider


class SystemSettingsProviderTests(unittest.TestCase):
    def test_categories_are_stable_and_product_facing(self) -> None:
        self.assertEqual(CATEGORIES, ("Display", "Audio", "Network", "Bluetooth", "Controllers", "Storage", "Performance", "System"))

    def test_each_category_returns_normalized_rows(self) -> None:
        provider = SystemSettingsProvider()
        for category in CATEGORIES:
            rows = provider.list_settings(category)
            self.assertTrue(rows)
            for row in rows:
                self.assertEqual(set(row), {"key", "label", "kind", "value", "detail", "writable"})
                if row["key"] == "lulu.reset":
                    self.assertTrue(row["writable"])
                    self.assertEqual(row["kind"], "action")
                elif row["key"] == "statistics-overlay:mode":
                    self.assertTrue(row["writable"])
                    self.assertEqual(row["kind"], "action")
                else:
                    self.assertFalse(row["writable"])

    def test_reset_mudos_is_in_the_visible_system_settings_cards(self) -> None:
        rows = SystemSettingsProvider().list_settings("System")
        reset = next((row for row in rows if row["key"] == "lulu.reset"), None)
        self.assertIsNotNone(reset)
        self.assertEqual(reset["label"], "Reset Mudos")
        self.assertEqual(reset["kind"], "action")
        self.assertTrue(reset["writable"])

    def test_unknown_category_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            SystemSettingsProvider().list_settings("Unknown")


if __name__ == "__main__":
    unittest.main()
