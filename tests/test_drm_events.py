import unittest

from lulu.drm_events import is_drm_hotplug_uevent


class DrmHotplugUeventTests(unittest.TestCase):
    def test_recognizes_drm_hotplug_while_ignoring_unrelated_events(self) -> None:
        self.assertTrue(is_drm_hotplug_uevent(
            b"change@/devices/pci0000:00/drm/card1\0ACTION=change\0SUBSYSTEM=drm\0HOTPLUG=1\0"
        ))
        self.assertFalse(is_drm_hotplug_uevent(
            b"change@/devices/pci0000:00/drm/card1\0ACTION=change\0SUBSYSTEM=drm\0HOTPLUG=0\0"
        ))
        self.assertFalse(is_drm_hotplug_uevent(
            b"change@/devices/pci0000:00/input/input0\0ACTION=change\0SUBSYSTEM=input\0HOTPLUG=1\0"
        ))


if __name__ == "__main__":
    unittest.main()
