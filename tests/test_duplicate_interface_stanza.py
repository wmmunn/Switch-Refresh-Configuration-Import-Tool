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


DUPLICATE_INTERFACE = "GigabitEthernet1/0/49"


def load_fixture(name: str) -> str:
    return (FIXTURES_DIR / name).read_text(encoding="utf-8")


def make_uplink_profile():
    return {
        "profile": {
            "name": "Duplicate Stanza Review Profile",
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
                "known_source_ports": [DUPLICATE_INTERFACE],
                "description_contains": ["UPLINK"],
                "treat_trunks_as_candidates": True,
            },
            "destination": {
                "mode": "explicit",
                "mappings": {
                    DUPLICATE_INTERFACE: "TenGigabitEthernet1/1/1",
                },
            },
            "preserve": {
                "description": True,
                "trunk_allowed_vlans": "review_required",
            },
        },
        "port_channels": {
            "detect_channel_groups": True,
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


def make_clean_access_profile():
    return {
        "profile": {
            "name": "Clean Access Review Profile",
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
                "known_source_ports": [],
                "description_contains": ["UPLINK"],
                "treat_trunks_as_candidates": False,
            },
            "destination": {
                "mode": "explicit",
                "mappings": {},
            },
            "preserve": {
                "description": True,
                "trunk_allowed_vlans": "review_required",
            },
        },
        "port_channels": {
            "detect_channel_groups": True,
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


ACCESS_PORT = "GigabitEthernet1/0/1"


class DuplicateInterfaceStanzaTests(unittest.TestCase):
    def test_duplicate_source_interface_stanza_is_surfaced(self):
        config_text = load_fixture("duplicate_uplink_stanza.txt")
        self.assertEqual(config_text.count(f"interface {DUPLICATE_INTERFACE}"), 2)

        source = parse_source_config(config_text)
        plan = build_target_refresh_plan(source, build_profile_schema(make_uplink_profile()))

        uplink_pairs = tuple(
            (uplink.source_interface, uplink.target_interface)
            for uplink in plan.uplinks
        )
        self.assertEqual(
            uplink_pairs,
            (
                (DUPLICATE_INTERFACE, "TenGigabitEthernet1/1/1"),
                (DUPLICATE_INTERFACE, "TenGigabitEthernet1/1/1"),
            ),
        )

        named_warnings = tuple(
            warning for warning in plan.warnings if DUPLICATE_INTERFACE in warning
        )
        named_review_flags = tuple(
            flag for flag in plan.review_flags if DUPLICATE_INTERFACE in flag
        )
        self.assertTrue(
            named_warnings or named_review_flags,
            "duplicate GigabitEthernet1/0/49 was rendered twice with no warning "
            "or review flag naming that interface: "
            f"warnings={plan.warnings!r} review_flags={plan.review_flags!r}",
        )

    def test_duplicate_access_port_stanza_is_not_a_clean_plan(self):
        config_text = load_fixture("duplicate_access_port_stanza.txt")
        self.assertEqual(config_text.count(f"interface {ACCESS_PORT}"), 2)

        source = parse_source_config(config_text)
        plan = build_target_refresh_plan(
            source, build_profile_schema(make_clean_access_profile())
        )

        access_pairs = tuple(
            (port.source_interface, port.target_interface)
            for port in plan.access_ports
        )
        self.assertEqual(
            access_pairs,
            (
                (ACCESS_PORT, ACCESS_PORT),
                (ACCESS_PORT, ACCESS_PORT),
            ),
        )
        self.assertTrue(
            any(ACCESS_PORT in warning for warning in plan.warnings),
            f"duplicate {ACCESS_PORT} was rendered twice with no warning "
            f"naming that interface: warnings={plan.warnings!r}",
        )
        self.assertIn("duplicate_interface_stanza", plan.review_flags)
        self.assertFalse(plan.audit_summary.is_completely_clean)

    def test_unparseable_interface_declaration_is_not_a_clean_plan(self):
        source = parse_source_config(
            load_fixture("unparseable_interface_declaration.txt")
        )
        plan = build_target_refresh_plan(
            source, build_profile_schema(make_clean_access_profile())
        )

        self.assertEqual(
            source.flagged_blocks[0].reason,
            "unparseable_interface_declaration",
        )
        self.assertIn("unparseable_interface_declaration", plan.review_flags)
        self.assertFalse(plan.audit_summary.is_completely_clean)
