import sys
import unittest
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_DIR / "src"
FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
EXAMPLES_DIR = PROJECT_DIR / "examples"
sys.path.insert(0, str(SRC_DIR))

from switch_refresh_config_import_tool.mapping_engine import (
    build_target_refresh_plan,
    classify_interface_role,
)
from switch_refresh_config_import_tool.profile_schema import build_profile_schema
from switch_refresh_config_import_tool.source_parser import parse_source_config


ROLE_TO_PLAN_BUCKET = {
    "uplink": "uplinks",
    "access": "access_ports",
    "ignored": "ignored_interfaces",
    "empty": "ignored_interfaces",
    "port_channel_member": "port_channels",
    "unplaceable": None,
}


def load_fixture(name: str) -> str:
    return (FIXTURES_DIR / name).read_text(encoding="utf-8")


def make_profile_dict():
    return {
        "profile": {
            "name": "Generic Cisco IOS Access Switch Refresh",
            "version": 1,
            "vendor": "cisco",
            "os_family": "ios",
        },
        "stack_translation": {
            "enabled": True,
            "member_mapping": {
                1: 1,
            },
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
                "treat_trunks_as_candidates": True,
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


def plan_bucket_for(interface_name: str, plan) -> str | None:
    if any(item.source_interface == interface_name for item in plan.uplinks):
        return "uplinks"
    if any(item.source_interface == interface_name for item in plan.access_ports):
        return "access_ports"
    if any(item.source_interface == interface_name for item in plan.ignored_interfaces):
        return "ignored_interfaces"
    for group in plan.port_channels:
        if any(
            member.source_interface == interface_name
            for member in group.member_interfaces
        ):
            return "port_channels"
    return None


class InterfaceRoleAgreementTests(unittest.TestCase):
    def assert_classifier_agrees_with_plan(self, config_text: str):
        source = parse_source_config(config_text)
        schema = build_profile_schema(make_profile_dict())
        plan = build_target_refresh_plan(source, schema)

        mismatches = []
        for interface in source.interfaces:
            role = classify_interface_role(interface, schema)
            self.assertIn(
                role,
                ROLE_TO_PLAN_BUCKET,
                f"{interface.name}: classify_interface_role() returned unknown "
                f"role {role!r}",
            )
            expected_bucket = ROLE_TO_PLAN_BUCKET[role]
            actual_bucket = plan_bucket_for(interface.name, plan)
            if role == "unplaceable":
                if actual_bucket is not None:
                    mismatches.append(
                        f"{interface.name}: unplaceable must land in no plan "
                        f"bucket by design, but build_target_refresh_plan() "
                        f"placed it in {actual_bucket}"
                    )
                continue
            if actual_bucket != expected_bucket:
                mismatches.append(
                    f"{interface.name}: classify_interface_role() returned "
                    f"{role!r} (bucket {expected_bucket}) but "
                    f"build_target_refresh_plan() placed it in {actual_bucket}"
                )

        self.assertEqual(mismatches, [])
        return source, plan

    def test_classifier_role_matches_plan_bucket_for_svi_with_uplink_description(self):
        source = parse_source_config(load_fixture("svi_with_uplink_description.txt"))
        parsed_names = [interface.name for interface in source.interfaces]
        self.assertEqual(
            parsed_names,
            ["GigabitEthernet1/0/1", "Vlan99"],
        )
        self.assert_classifier_agrees_with_plan(
            load_fixture("svi_with_uplink_description.txt")
        )

    def test_classifier_role_matches_plan_bucket_for_port_channel_members(self):
        source, plan = self.assert_classifier_agrees_with_plan(
            load_fixture("port_channel_members.txt")
        )
        parsed_names = [interface.name for interface in source.interfaces]
        self.assertEqual(
            parsed_names,
            ["GigabitEthernet1/0/49", "GigabitEthernet1/0/52"],
        )
        member_names = [
            member.source_interface
            for group in plan.port_channels
            for member in group.member_interfaces
        ]
        self.assertEqual(
            member_names,
            ["GigabitEthernet1/0/49", "GigabitEthernet1/0/52"],
        )
        self.assertEqual(
            plan_bucket_for("GigabitEthernet1/0/49", plan),
            "port_channels",
        )
        self.assertEqual(
            plan_bucket_for("GigabitEthernet1/0/52", plan),
            "port_channels",
        )

    def test_classifier_role_matches_plan_bucket_for_generic_existing_switch_config(self):
        config_path = EXAMPLES_DIR / "generic_existing_switch_config.txt"
        self.assert_classifier_agrees_with_plan(
            config_path.read_text(encoding="utf-8")
        )
