import sys
import unittest
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_DIR / "src"
FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
sys.path.insert(0, str(SRC_DIR))

from switch_refresh_config_import_tool.mapping_engine import build_target_refresh_plan
from switch_refresh_config_import_tool.profile_schema import build_profile_schema
from switch_refresh_config_import_tool.source_parser import parse_source_config


MEMBER_A = "GigabitEthernet1/0/49"
MEMBER_B = "GigabitEthernet1/0/52"
TARGET_A = "TenGigabitEthernet1/1/1"
TARGET_B = "TenGigabitEthernet1/1/2"


def load_fixture(name: str) -> str:
    return (FIXTURES_DIR / name).read_text(encoding="utf-8")


def make_detection_off_profile():
    return {
        "profile": {
            "name": "Port-Channel Detection Off Review Profile",
            "version": 1,
            "vendor": "cisco",
            "os_family": "ios",
        },
        "stack_translation": {
            "enabled": True,
            "member_mapping": {1: 1},
        },
        "interface_translation": {
            "access_ports": {
                "mode": "same_member_same_port",
                "target_pattern": "GigabitEthernet{member}/0/{port}",
            },
            "explicit_mappings": {},
        },
        "uplinks": {
            "detection": {
                "known_source_ports": [MEMBER_A, MEMBER_B],
                "description_contains": ["UPLINK"],
                "treat_trunks_as_candidates": True,
            },
            "destination": {
                "mode": "explicit",
                "mappings": {
                    MEMBER_A: TARGET_A,
                    MEMBER_B: TARGET_B,
                },
            },
            "preserve": {
                "description": True,
                "trunk_allowed_vlans": "review_required",
            },
        },
        "port_channels": {
            "detect_channel_groups": False,
            "require_review": True,
        },
        "review_gates": {
            "always_review": [],
            "fail_closed_on": ["ambiguous_stack_mapping"],
        },
        "template_mapping": {
            "hostname": "HOSTNAME",
            "access_port_configs": "ACCESS_PORT_CONFIGS",
        },
    }


class PortChannelDetectionOffTests(unittest.TestCase):
    def test_channel_group_present_with_detection_off_is_warned_not_silent(self):
        source = parse_source_config(load_fixture("port_channel_members.txt"))
        plan = build_target_refresh_plan(
            source, build_profile_schema(make_detection_off_profile())
        )

        uplink_pairs = tuple(
            (uplink.source_interface, uplink.target_interface)
            for uplink in plan.uplinks
        )
        self.assertEqual(
            uplink_pairs,
            (
                (MEMBER_A, TARGET_A),
                (MEMBER_B, TARGET_B),
            ),
        )
        self.assertEqual(plan.port_channels, ())

        self.assertTrue(
            any(MEMBER_A in warning for warning in plan.warnings),
            f"channel-group member {MEMBER_A} was flattened with no warning "
            f"naming that interface: warnings={plan.warnings!r}",
        )
        self.assertTrue(
            any(MEMBER_B in warning for warning in plan.warnings),
            f"channel-group member {MEMBER_B} was flattened with no warning "
            f"naming that interface: warnings={plan.warnings!r}",
        )
        self.assertIn("port_channel_detection_disabled", plan.review_flags)
