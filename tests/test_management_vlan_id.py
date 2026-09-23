import sys
import unittest
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_DIR / "src"
FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
sys.path.insert(0, str(SRC_DIR))

from switch_refresh_config_import_tool.core import extract_management_vlan_ip


MGMT_SVI_CASES = (
    ("mgmt_svi_pascal_Vlan900.txt", "Vlan900"),
    ("mgmt_svi_lower_vlan900.txt", "vlan900"),
    ("mgmt_svi_upper_VLAN900.txt", "VLAN900"),
    ("mgmt_svi_mixed_VLan900.txt", "VLan900"),
    ("mgmt_svi_spaced_Vlan_900.txt", "Vlan 900"),
)


def load_fixture(name: str) -> str:
    return (FIXTURES_DIR / name).read_text(encoding="utf-8")


class ManagementVlanIdTests(unittest.TestCase):
    def test_extract_management_vlan_ip_strips_vlan_prefix_regardless_of_case(self):
        for fixture_name, interface_spelling in MGMT_SVI_CASES:
            with self.subTest(interface=interface_spelling, fixture=fixture_name):
                vlan_id, ip_address, subnet_mask = extract_management_vlan_ip(
                    load_fixture(fixture_name)
                )
                self.assertEqual(vlan_id, "900")
                self.assertEqual(ip_address, "192.0.2.10")
                self.assertEqual(subnet_mask, "255.255.255.0")
