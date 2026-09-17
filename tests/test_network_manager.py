import unittest

from dbus_next import Variant

from lulu.network_manager import _ssid, _unwrap


class NetworkManagerNormalizationTests(unittest.TestCase):
    def test_unwrap_normalizes_nested_dbus_variants(self) -> None:
        value = _unwrap({"strength": Variant("y", 72), "ssid": [Variant("s", "Cafe")]})
        self.assertEqual(value, {"strength": 72, "ssid": ["Cafe"]})

    def test_ssid_decodes_network_manager_byte_array(self) -> None:
        self.assertEqual(_ssid([67, 97, 102, 101]), "Cafe")
        self.assertEqual(_ssid([]), "")


if __name__ == "__main__":
    unittest.main()
