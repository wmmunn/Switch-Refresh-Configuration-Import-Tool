import sys
import unittest
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_DIR / "src"
sys.path.insert(0, str(SRC_DIR))

from generic_lab_notes_extractor import app as MODULE


BASELINE_PATH = (
    SRC_DIR
    / "generic_lab_notes_extractor"
    / "assets"
    / "generic_baseline_lab_sheet.txt"
)
SAMPLE_CONFIG_PATH = (
    SRC_DIR
    / "generic_lab_notes_extractor"
    / "assets"
    / "generic_sample_running_config.txt"
)


class SanitizedDistributionTests(unittest.TestCase):
    def test_baseline_contains_every_supported_placeholder(self):
        baseline = BASELINE_PATH.read_text(encoding="utf-8")
        for placeholder in MODULE.PLACEHOLDERS:
            with self.subTest(placeholder=placeholder):
                self.assertIn(placeholder, baseline)

    def test_baseline_contains_no_example_network_values(self):
        baseline = BASELINE_PATH.read_text(encoding="utf-8").lower()
        forbidden = (
            "10.0.0.",
            "192.168.",
            "example.com",
            "corp",
        )
        for value in forbidden:
            with self.subTest(value=value):
                self.assertNotIn(value, baseline)

    def test_sanitized_extraction_uses_generic_baseline(self):
        config = """hostname SANITIZED-SW
vtp domain GENERIC
ip default-gateway 198.51.100.1
!
interface Vlan100
 ip address 198.51.100.2 255.255.255.0
!
vlan 100
 name USERS
!
interface GigabitEthernet0/1
 description USER_PORT
 switchport access vlan 100
 spanning-tree portfast edge
!
"""
        values = MODULE.extract_config_values(config)
        output = MODULE.apply_template(MODULE.load_bundled_baseline_text(), values)

        self.assertIn("SANITIZED-SW", output)
        self.assertIn("interface G1/0/1", output)
        self.assertNotIn("{{HOSTNAME}}", output)

    def test_generic_sample_config_is_sanitized_and_exercises_extraction(self):
        config = SAMPLE_CONFIG_PATH.read_text(encoding="utf-8")
        lowered = config.lower()

        self.assertIn("hostname demo-switch-01", lowered)
        self.assertNotIn("10.", lowered)
        self.assertNotIn("172.16.", lowered)
        self.assertNotIn("192.168.", lowered)

        values = MODULE.extract_config_values(config)
        self.assertEqual(values["{{HOSTNAME}}"], "DEMO-SWITCH-01")
        self.assertEqual(values["{{MGMT_VLAN}}"], "99")
        self.assertEqual(values["{{MGMT_IP}}"], "192.0.2.10")
        self.assertIn("vlan 20", values["{{VLAN_LIST}}"])
        self.assertIn("interface G1/0/1", values["{{ACCESS_PORT_CONFIGS}}"])
        self.assertIn("RADIUS detected: YES", values["{{RADIUS_STATUS}}"])


if __name__ == "__main__":
    unittest.main()
