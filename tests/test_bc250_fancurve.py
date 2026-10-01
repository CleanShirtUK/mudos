import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / "scripts" / "bc250-fancurve"


def bash_policy(command: str) -> list[str]:
    # Source only declarations; never touch hardware when running host tests.
    result = subprocess.run(
        ["bash", "-c", f"source <(sed '/^FAN_HWMON=/,$d' '{SCRIPT}')\n{command}"],
        check=True, capture_output=True, text=True,
    )
    return result.stdout.splitlines()


class BC250FanCurveTests(unittest.TestCase):
    def test_invalid_sample_escalation_holds_then_increases(self) -> None:
        self.assertEqual(bash_policy('for n in 1 2 3 4 5; do invalid_pwm "$n" 110; done'),
                         ["110", "110", "175", "210", "255"])

    def test_fault_floors_never_reduce_a_higher_last_good_pwm(self) -> None:
        self.assertEqual(bash_policy('for n in 1 2 3 4 5; do invalid_pwm "$n" 235; done'),
                         ["235", "235", "235", "235", "255"])

    def test_fault_escalation_resets_on_valid_sample_and_is_consecutive(self) -> None:
        # Invalid 1, invalid 2, valid (counter reset), then a fresh invalid 1.
        self.assertEqual(bash_policy(
            'count=0; for valid in 0 0 1 0; do '
            'if (( valid )); then count=0; else count=$((count + 1)); fi; '
            'invalid_pwm "$count" 110; done'),
            ["110", "110", "110", "110"])

    def test_intermittent_failures_do_not_reach_full_speed(self) -> None:
        self.assertEqual(bash_policy(
            'count=0; for valid in 0 1 0 1 0 1 0; do '
            'if (( valid )); then count=0; else count=$((count + 1)); fi; '
            'invalid_pwm "$count" 110; done'),
            ["110"] * 7)

    def test_lower_curve_and_requested_gaming_temperature_band(self) -> None:
        self.assertEqual(bash_policy(
            'for t in 50 51 55 56 60 61 65 66 75 76 80 84 85 86 87 88 90; '
            'do curve_pwm "$t"; done'),
            ["90", "100", "100", "110", "110", "120", "120", "128", "128",
             "150", "150", "150", "175", "175", "210", "255", "255"])
        source = SCRIPT.read_text()
        self.assertIn("DOWN_DELAY_SAMPLES=5", source)
        self.assertIn("if (( temp >= 88 )); then", source)
        self.assertIn('sleep "$SAMPLE_INTERVAL"', source)
        self.assertIn("trap restore_firmware EXIT", source)
        self.assertIn('echo 2 > "$ENABLE" 2>/dev/null || true', source)

    def test_provisioning_restarts_only_the_fan_controller(self) -> None:
        provisioner = (ROOT / "scripts" / "provision-bc250-fancurve.sh").read_text()
        self.assertIn("/opt/lulu/current/scripts/bc250-fancurve", provisioner)
        self.assertIn("/usr/local/bin/bc250-fancurve", provisioner)
        self.assertIn("systemctl restart bc250-fancurve.service", provisioner)
        self.assertNotIn("lulu-session", provisioner)


if __name__ == "__main__":
    unittest.main()
