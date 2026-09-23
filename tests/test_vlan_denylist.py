import sys

import unittest

from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parents[1]

SRC_DIR = PROJECT_DIR / "src"

sys.path.insert(0, str(SRC_DIR))

from switch_refresh_config_import_tool.core import extract_vlans


class TestVlanDenylist(unittest.TestCase):
    def test_internal_allocation_policy_not_emitted(self):
        config = (
            "vlan internal allocation policy ascending\n"
            "vlan 10\n"
            " name DATA\n"
            "vlan 20\n"
            " name VOICE\n"
        )
        output = extract_vlans(config)
        self.assertIn("vlan 10", output)
        self.assertIn("DATA", output)
        self.assertIn("vlan 20", output)
        self.assertIn("VOICE", output)
        self.assertNotIn("internal allocation policy", output)

    def test_vlan_group_stanza_still_emitted(self):
        config = "vlan group DEMO_GROUP vlan-list 10,20\n"
        output = extract_vlans(config)
        self.assertIn("vlan group DEMO_GROUP vlan-list 10,20", output)


if __name__ == "__main__":
    unittest.main()
