import sys
import unittest
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_DIR / "src"
sys.path.insert(0, str(SRC_DIR))

from switch_refresh_config_import_tool.mapping_engine import build_target_refresh_plan
from switch_refresh_config_import_tool.plan_renderer import (
    ENGINE_ACCESS_PORTS,
    ENGINE_COLLISIONS,
    ENGINE_REVIEW_SUMMARY,
    render_access_ports,
    render_collisions,
    render_plan_placeholders,
    render_plan_template,
    render_unmapped_interfaces,
)
from switch_refresh_config_import_tool.profile_schema import build_profile_schema
from switch_refresh_config_import_tool.source_parser import parse_source_config


def make_profile_dict():
    return {
        "profile": {
            "name": "Renderer Test Profile",
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


def build_plan(config_text, profile_dict=None):
    source = parse_source_config(config_text)
    schema = build_profile_schema(profile_dict or make_profile_dict())
    return build_target_refresh_plan(source, schema)


class PlanRendererTests(unittest.TestCase):
    def test_unmapped_access_port_renders_comment_safe_review_lines(self):
        config = """hostname DEMO-RENDER
!
interface GigabitEthernet4/0/1
 switchport access vlan 20
 switchport mode access
!
"""
        profile = make_profile_dict()
        profile["stack_translation"]["member_mapping"] = {1: 1}
        plan = build_plan(config, profile)

        rendered = render_access_ports(plan)

        self.assertIn("GigabitEthernet4/0/1 -> UNMAPPED", rendered)
        for line in rendered.splitlines():
            if line.strip():
                self.assertTrue(line.startswith("!"), line)

    def test_mapped_access_port_renders_commands_and_comment_safe_review_notes(self):
        config = """hostname DEMO-RENDER
!
interface GigabitEthernet1/0/25
 description DEMO_ACCESS
 switchport access vlan 30
 switchport mode access
!
"""
        profile = make_profile_dict()
        profile["interface_translation"]["access_ports"] = {
            "mode": "ordered_port_ranges",
            "range_rules": [
                {
                    "source_ports": "1-24",
                    "target_pattern": "GigabitEthernet{member}/0/{port}",
                    "verification_level": "operator_verified",
                },
                {
                    "source_ports": "25-48",
                    "target_pattern": "FiveGigabitEthernet{member}/0/{port}",
                    "verification_level": "cisco_derived_candidate",
                },
            ],
        }
        plan = build_plan(config, profile)

        rendered = render_access_ports(plan)

        self.assertIn("interface FiveGigabitEthernet1/0/25", rendered)
        self.assertIn(" switchport access vlan 30", rendered)
        self.assertIn("! REVIEW: Applied rule: ACCESS_PORT_RANGE_RULE.", rendered)
        self.assertIn("! REVIEW: Review urgency: WARNING_PROFILE_REVIEW.", rendered)
        for line in rendered.splitlines():
            if "REVIEW" in line or "WARNING" in line or "CRITICAL" in line:
                self.assertTrue(line.startswith("!"), line)

    def test_collision_renderer_outputs_only_comment_lines(self):
        config = """hostname DEMO-COLLISION
!
interface GigabitEthernet1/0/1
 switchport access vlan 20
 switchport mode access
!
interface GigabitEthernet1/0/2
 switchport access vlan 20
 switchport mode access
!
"""
        profile = make_profile_dict()
        profile["interface_translation"]["explicit_mappings"] = {
            "GigabitEthernet1/0/1": "GigabitEthernet1/0/10",
            "GigabitEthernet1/0/2": "GigabitEthernet1/0/10",
        }
        plan = build_plan(config, profile)

        rendered = render_collisions(plan)

        self.assertIn("! CRITICAL:", rendered)
        self.assertIn("GROUP_GigabitEthernet1/0/10", rendered)
        for line in rendered.splitlines():
            if line.strip():
                self.assertTrue(line.startswith("!"), line)

    def test_template_renderer_replaces_engine_placeholders(self):
        config = """hostname DEMO-TEMPLATE
!
interface GigabitEthernet1/0/1
 switchport access vlan 20
 switchport mode access
!
"""
        plan = build_plan(config)
        template = "\n".join(
            [
                "SUMMARY",
                ENGINE_REVIEW_SUMMARY,
                "ACCESS",
                ENGINE_ACCESS_PORTS,
                "COLLISIONS",
                ENGINE_COLLISIONS,
            ]
        )

        rendered = render_plan_template(template, plan)
        values = render_plan_placeholders(plan)

        self.assertNotIn(ENGINE_REVIEW_SUMMARY, rendered)
        self.assertNotIn(ENGINE_ACCESS_PORTS, rendered)
        self.assertNotIn(ENGINE_COLLISIONS, rendered)
        self.assertIn(values[ENGINE_REVIEW_SUMMARY], rendered)
        self.assertIn("interface GigabitEthernet1/0/1", rendered)

    def test_unmapped_summary_is_comment_safe(self):
        config = """hostname DEMO-UNMAPPED-SUMMARY
!
interface Ethernet1
 switchport access vlan 20
 switchport mode access
!
"""
        plan = build_plan(config)

        rendered = render_unmapped_interfaces(plan)

        self.assertIn("Ethernet1 is UNMAPPED", rendered)
        for line in rendered.splitlines():
            if line.strip():
                self.assertTrue(line.startswith("!"), line)


if __name__ == "__main__":
    unittest.main()
