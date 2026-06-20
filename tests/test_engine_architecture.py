import sys
import unittest
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_DIR / "src"
sys.path.insert(0, str(SRC_DIR))

from switch_refresh_config_import_tool.engine_models import InvalidSchemaElementError
from switch_refresh_config_import_tool.mapping_engine import build_target_refresh_plan
from switch_refresh_config_import_tool.profile_schema import build_profile_schema
from switch_refresh_config_import_tool.source_parser import parse_source_config


SANITIZED_CONFIG = """hostname DEMO-SW01
vtp domain DEMO-LAB
aaa authentication dot1x default group DEMO-RADIUS-GROUP
!
vlan 20
 name DEMO_USERS
!
vlan 99
 name DEMO_MANAGEMENT
!
interface GigabitEthernet1/0/1
 description DEMO_ACCESS_PORT
 switchport access vlan 20
 switchport mode access
 switchport voice vlan 30
!
interface GigabitEthernet1/0/49
 description DEMO_PORT_CHANNEL_MEMBER_A
 switchport trunk allowed vlan 20,30,99
 switchport mode trunk
 channel-group 1 mode active
!
interface GigabitEthernet1/0/52
 description DEMO_PORT_CHANNEL_MEMBER_B
 switchport trunk allowed vlan 20,30,99
 switchport mode trunk
 channel-group 1 mode active
!
interface Vlan99
 description DEMO_MANAGEMENT
 ip address 192.0.2.10 255.255.255.0
!
ip default-gateway 192.0.2.1
!
"""


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
                1: 2,
            },
        },
        "interface_translation": {
            "access_ports": {
                "mode": "same_member_same_port",
                "target_pattern": "GigabitEthernet{member}/0/{port}",
            },
            "explicit_mappings": {
                "GigabitEthernet1/0/49": "TenGigabitEthernet1/1/1",
                "GigabitEthernet1/0/52": "TenGigabitEthernet2/1/1",
            },
        },
        "uplinks": {
            "detection": {
                "known_source_ports": [
                    "GigabitEthernet1/0/49",
                    "GigabitEthernet1/0/52",
                ],
                "description_contains": ["UPLINK"],
                "treat_trunks_as_candidates": True,
            },
            "destination": {
                "mode": "explicit",
                "mappings": {
                    "GigabitEthernet1/0/49": "TenGigabitEthernet1/1/1",
                    "GigabitEthernet1/0/52": "TenGigabitEthernet2/1/1",
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
            "always_review": ["stack_member_mapping"],
            "fail_closed_on": ["ambiguous_stack_mapping"],
        },
        "template_mapping": {
            "hostname": "HOSTNAME",
            "access_port_configs": "ACCESS_PORT_CONFIGS",
            "port_channel_interfaces": "PORT_CHANNEL_INTERFACES",
        },
    }


class EngineArchitectureTests(unittest.TestCase):
    def test_source_parser_returns_source_dataclasses_without_target_assumptions(self):
        source = parse_source_config(SANITIZED_CONFIG)

        self.assertEqual(source.hostname, "DEMO-SW01")
        self.assertEqual(source.vtp_domain, "DEMO-LAB")
        self.assertEqual(source.management.vlan_id, "99")
        self.assertEqual(source.management.ip_address, "192.0.2.10")
        self.assertTrue(source.radius_detected)
        self.assertEqual(len(source.vlans), 2)
        self.assertEqual(len(source.interfaces), 4)
        self.assertEqual(source.flagged_blocks, ())

    def test_mapping_engine_returns_structured_target_plan(self):
        source = parse_source_config(SANITIZED_CONFIG)
        schema = build_profile_schema(make_profile_dict())

        plan = build_target_refresh_plan(source, schema)

        self.assertEqual(plan.hostname, "DEMO-SW01")
        self.assertEqual(len(plan.access_ports), 1)
        self.assertEqual(plan.access_ports[0].source_interface, "GigabitEthernet1/0/1")
        self.assertEqual(plan.access_ports[0].target_interface, "GigabitEthernet2/0/1")
        self.assertEqual(len(plan.port_channels), 1)
        self.assertEqual(plan.port_channels[0].channel_group, "1")
        self.assertEqual(len(plan.port_channels[0].member_interfaces), 2)
        self.assertEqual(len(plan.ignored_interfaces), 0)
        self.assertIn("port_channels", plan.review_flags)
        self.assertIn("trunk_allowed_vlans", plan.review_flags)
        self.assertIn("stack_member_mapping", plan.review_flags)
        self.assertEqual(plan.audit_summary.member_shifts_count, 1)
        self.assertFalse(plan.audit_summary.is_completely_clean)

    def test_audit_summary_reports_completely_clean_plan(self):
        config = """hostname DEMO-CLEAN
!
interface GigabitEthernet1/0/1
 switchport access vlan 20
 switchport mode access
!
"""
        raw_profile = make_profile_dict()
        raw_profile["stack_translation"]["member_mapping"] = {1: 1}
        raw_profile["review_gates"]["always_review"] = []
        raw_profile["interface_translation"]["explicit_mappings"] = {}
        raw_profile["uplinks"]["detection"]["known_source_ports"] = []
        raw_profile["uplinks"]["destination"]["mappings"] = {}
        source = parse_source_config(config)
        schema = build_profile_schema(raw_profile)

        plan = build_target_refresh_plan(source, schema)

        self.assertEqual(plan.audit_summary.collisions_count, 0)
        self.assertEqual(plan.audit_summary.unmapped_count, 0)
        self.assertEqual(plan.audit_summary.member_shifts_count, 0)
        self.assertEqual(plan.audit_summary.total_flags_count, 0)
        self.assertTrue(plan.audit_summary.is_completely_clean)

    def test_unrecognized_schema_element_raises_descriptive_exception(self):
        raw_profile = make_profile_dict()
        raw_profile["unsupported_magic"] = {}

        with self.assertRaisesRegex(
            InvalidSchemaElementError,
            "Unsupported top-level schema element: 'unsupported_magic'",
        ):
            build_profile_schema(raw_profile)

    def test_unrecognized_mapping_mode_raises_descriptive_exception(self):
        source = parse_source_config(SANITIZED_CONFIG)
        raw_profile = make_profile_dict()
        raw_profile["interface_translation"]["access_ports"]["mode"] = "magic_reflect"
        schema = build_profile_schema(raw_profile)

        with self.assertRaisesRegex(
            InvalidSchemaElementError,
            "Unsupported access port translation mode: 'magic_reflect'",
        ):
            build_target_refresh_plan(source, schema)

    def test_target_interface_collision_creates_review_flag_and_warning(self):
        config = """hostname DEMO-SW01
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
        raw_profile = make_profile_dict()
        raw_profile["stack_translation"]["member_mapping"] = {1: 1}
        raw_profile["interface_translation"]["explicit_mappings"] = {
            "GigabitEthernet1/0/1": "GigabitEthernet1/0/10",
            "GigabitEthernet1/0/2": "GigabitEthernet1/0/10",
        }
        source = parse_source_config(config)
        schema = build_profile_schema(raw_profile)

        plan = build_target_refresh_plan(source, schema)

        self.assertIn("target_interface_collision", plan.review_flags)
        self.assertEqual(len(plan.warnings), 1)
        self.assertIn("GigabitEthernet1/0/10", plan.warnings[0])
        self.assertIn("GigabitEthernet1/0/1", plan.warnings[0])
        self.assertIn("GigabitEthernet1/0/2", plan.warnings[0])
        self.assertTrue(plan.access_ports[0].mapping_evidence.is_collision)
        self.assertEqual(
            plan.access_ports[0].mapping_evidence.review_urgency,
            "CRITICAL_COLLISION",
        )
        self.assertEqual(
            plan.access_ports[0].mapping_evidence.collision_group,
            "GROUP_GigabitEthernet1/0/10",
        )
        self.assertEqual(
            plan.access_ports[0].mapping_evidence.collision_partners,
            ("GigabitEthernet1/0/2",),
        )
        self.assertEqual(plan.audit_summary.collisions_count, 1)
        self.assertEqual(plan.audit_summary.unmapped_count, 0)
        self.assertEqual(plan.audit_summary.total_flags_count, 2)
        self.assertFalse(plan.audit_summary.is_completely_clean)

    def test_missing_stack_member_mapping_leaves_target_unassigned(self):
        config = """hostname DEMO-SW01
!
interface GigabitEthernet4/0/1
 switchport access vlan 20
 switchport mode access
!
"""
        raw_profile = make_profile_dict()
        raw_profile["stack_translation"]["enabled"] = True
        raw_profile["stack_translation"]["member_mapping"] = {1: 1, 2: 2}
        source = parse_source_config(config)
        schema = build_profile_schema(raw_profile)

        plan = build_target_refresh_plan(source, schema)

        self.assertEqual(len(plan.access_ports), 1)
        self.assertIsNone(plan.access_ports[0].target_interface)
        self.assertIn("missing_stack_member_mapping", plan.access_ports[0].review_flags)
        self.assertIn("unmapped_interfaces", plan.review_flags)
        self.assertEqual(
            plan.access_ports[0].mapping_evidence.applied_rule_type,
            "MISSING_STACK_MEMBER_MAPPING",
        )
        self.assertEqual(
            plan.access_ports[0].mapping_evidence.review_urgency,
            "WARNING_UNMAPPED",
        )
        self.assertEqual(plan.audit_summary.unmapped_count, 1)
        self.assertFalse(plan.audit_summary.is_completely_clean)

    def test_unmapped_uplink_creates_review_flag(self):
        config = """hostname DEMO-SW01
!
interface GigabitEthernet1/0/49
 description DEMO_UPLINK_TO_DIST
 switchport trunk allowed vlan 20,99
 switchport mode trunk
!
"""
        raw_profile = make_profile_dict()
        raw_profile["interface_translation"]["explicit_mappings"] = {}
        raw_profile["uplinks"]["destination"]["mappings"] = {}
        source = parse_source_config(config)
        schema = build_profile_schema(raw_profile)

        plan = build_target_refresh_plan(source, schema)

        self.assertEqual(len(plan.uplinks), 1)
        self.assertIsNone(plan.uplinks[0].target_interface)
        self.assertIn("uplinks", plan.review_flags)
        self.assertIn("unmapped_interfaces", plan.review_flags)
        self.assertIn("unmapped_interfaces", plan.uplinks[0].review_flags)

    def test_standalone_legacy_access_interface_maps_as_member_one(self):
        config = """hostname DEMO-STANDALONE
!
interface GigabitEthernet0/5
 switchport access vlan 20
 switchport mode access
!
"""
        raw_profile = make_profile_dict()
        raw_profile["stack_translation"]["member_mapping"] = {1: 1}
        raw_profile["review_gates"]["always_review"] = []
        raw_profile["interface_translation"]["explicit_mappings"] = {}
        source = parse_source_config(config)
        schema = build_profile_schema(raw_profile)

        plan = build_target_refresh_plan(source, schema)

        self.assertEqual(len(plan.access_ports), 1)
        self.assertEqual(
            plan.access_ports[0].target_interface,
            "GigabitEthernet1/0/5",
        )
        self.assertEqual(
            plan.access_ports[0].mapping_evidence.applied_rule_type,
            "STACK_IDENTITY",
        )
        self.assertIn(
            "source_format='standalone_port'",
            plan.access_ports[0].mapping_evidence.rule_details,
        )

    def test_collision_and_unmapped_uplink_survive_in_same_plan(self):
        config = """hostname DEMO-SW01
!
interface GigabitEthernet1/0/1
 switchport access vlan 20
 switchport mode access
!
interface GigabitEthernet1/0/2
 switchport access vlan 20
 switchport mode access
!
interface GigabitEthernet1/0/3
 switchport access vlan 20
 switchport mode access
!
interface GigabitEthernet1/0/49
 description DEMO_UNMAPPED_UPLINK
 switchport trunk allowed vlan 20,99
 switchport mode trunk
!
"""
        raw_profile = make_profile_dict()
        raw_profile["stack_translation"]["member_mapping"] = {1: 1}
        raw_profile["review_gates"]["always_review"] = []
        raw_profile["interface_translation"]["explicit_mappings"] = {
            "GigabitEthernet1/0/1": "GigabitEthernet1/0/10",
            "GigabitEthernet1/0/2": "GigabitEthernet1/0/10",
        }
        raw_profile["uplinks"]["destination"]["mappings"] = {}
        raw_profile["uplinks"]["detection"]["known_source_ports"] = [
            "GigabitEthernet1/0/49",
        ]
        source = parse_source_config(config)
        schema = build_profile_schema(raw_profile)

        plan = build_target_refresh_plan(source, schema)

        self.assertEqual(plan.review_flags.count("target_interface_collision"), 1)
        self.assertEqual(plan.review_flags.count("unmapped_interfaces"), 1)
        self.assertIn("uplinks", plan.review_flags)
        self.assertEqual(len(plan.warnings), 1)
        self.assertIn("GigabitEthernet1/0/10", plan.warnings[0])
        self.assertEqual(len(plan.access_ports), 3)
        self.assertEqual(len(plan.uplinks), 1)
        self.assertIsNone(plan.uplinks[0].target_interface)
        self.assertEqual(plan.uplinks[0].review_flags.count("unmapped_interfaces"), 1)

    def test_empty_interfaces_are_explicitly_accounted_as_ignored(self):
        config = """hostname DEMO-SW01
!
interface GigabitEthernet1/0/1
!
interface GigabitEthernet1/0/2
 switchport access vlan 20
 switchport mode access
!
"""
        source = parse_source_config(config)
        schema = build_profile_schema(make_profile_dict())

        plan = build_target_refresh_plan(source, schema)

        self.assertEqual(len(plan.access_ports), 1)
        self.assertEqual(len(plan.ignored_interfaces), 1)
        self.assertEqual(
            plan.ignored_interfaces[0].source_interface,
            "GigabitEthernet1/0/1",
        )
        self.assertEqual(plan.ignored_interfaces[0].reason, "empty_interface")

    def test_malformed_interface_declaration_is_flagged_not_guessed(self):
        config = """hostname DEMO-SW01
!
interface
 description DEMO_MALFORMED_BLOCK
 switchport access vlan 20
!
interface GigabitEthernet1/0/2
 switchport access vlan 20
 switchport mode access
!
"""
        source = parse_source_config(config)
        schema = build_profile_schema(make_profile_dict())

        plan = build_target_refresh_plan(source, schema)

        self.assertEqual(len(source.interfaces), 1)
        self.assertEqual(len(source.flagged_blocks), 1)
        self.assertEqual(
            source.flagged_blocks[0].reason,
            "unparseable_interface_declaration",
        )
        self.assertEqual(len(plan.access_ports), 1)

    def test_port_channel_parent_excluded_from_uplink_bucket_by_default(self):
        config = """hostname DEMO-SW01
!
interface Port-channel1
 description DEMO_PORT_CHANNEL_TO_DIST
 switchport trunk allowed vlan 20,99
 switchport mode trunk
!
interface GigabitEthernet1/0/49
 description DEMO_PORT_CHANNEL_MEMBER_A
 switchport trunk allowed vlan 20,99
 switchport mode trunk
 channel-group 1 mode active
!
interface GigabitEthernet1/0/52
 description DEMO_PORT_CHANNEL_MEMBER_B
 switchport trunk allowed vlan 20,99
 switchport mode trunk
 channel-group 1 mode active
!
"""
        source = parse_source_config(config)
        schema = build_profile_schema(make_profile_dict())

        plan = build_target_refresh_plan(source, schema)

        unmapped_uplinks = [
            uplink
            for uplink in plan.uplinks
            if uplink.target_interface is None
        ]

        self.assertEqual(len(plan.uplinks), 0)
        self.assertEqual(unmapped_uplinks, [])
        self.assertEqual(len(plan.port_channels), 1)
        self.assertEqual(plan.port_channels[0].channel_group, "1")
        self.assertEqual(len(plan.port_channels[0].member_interfaces), 2)
        self.assertEqual(
            plan.port_channels[0].member_interfaces[0].source_interface,
            "GigabitEthernet1/0/49",
        )
        self.assertEqual(
            plan.port_channels[0].member_interfaces[1].source_interface,
            "GigabitEthernet1/0/52",
        )
        self.assertNotIn("unmapped_interfaces", plan.review_flags)

    def test_trunk_allowed_vlan_statements_preserve_all_source_lines(self):
        config = """hostname DEMO-SW01
!
interface GigabitEthernet1/0/10
 switchport trunk allowed vlan 20,30,99
 switchport trunk allowed vlan add 100,101
 switchport trunk allowed vlan add 102,103
 switchport mode trunk
!
"""
        source = parse_source_config(config)

        trunk = source.interfaces[0]

        self.assertEqual(
            trunk.trunk_allowed_vlan_lines,
            (
                "switchport trunk allowed vlan 20,30,99",
                "switchport trunk allowed vlan add 100,101",
                "switchport trunk allowed vlan add 102,103",
            ),
        )
        self.assertEqual(trunk.trunk_allowed_vlans, "add 102,103")

    def test_malformed_trunk_allowed_vlan_syntax_is_distinct_from_unrestricted_trunk(self):
        config = """hostname DEMO-SW01
!
interface GigabitEthernet1/0/10
 switchport mode trunk
!
interface GigabitEthernet1/0/50
 switchport trunk allowed vlans 20,30,99
 switchport mode trunk
!
"""
        raw_profile = make_profile_dict()
        raw_profile["review_gates"]["always_review"] = []
        raw_profile["uplinks"]["destination"]["mappings"] = {}
        raw_profile["uplinks"]["detection"]["known_source_ports"] = []
        source = parse_source_config(config)
        schema = build_profile_schema(raw_profile)

        unrestricted_trunk = source.interfaces[0]
        malformed_trunk = source.interfaces[1]
        plan = build_target_refresh_plan(source, schema)

        self.assertEqual(unrestricted_trunk.trunk_allowed_vlan_lines, ())
        self.assertEqual(unrestricted_trunk.malformed_trunk_allowed_vlan_lines, ())
        self.assertEqual(malformed_trunk.trunk_allowed_vlan_lines, ())
        self.assertEqual(
            malformed_trunk.malformed_trunk_allowed_vlan_lines,
            ("switchport trunk allowed vlans 20,30,99",),
        )
        self.assertIn("malformed_trunk_allowed_vlans", plan.review_flags)
        self.assertIn("malformed_trunk_allowed_vlans", plan.uplinks[1].review_flags)
        self.assertEqual(len(plan.warnings), 1)
        self.assertIn("GigabitEthernet1/0/50", plan.warnings[0])

    def test_stack_member_remap_preserves_grouping_and_trunk_evidence(self):
        config = """hostname DEMO-STACK-SW01
!
interface GigabitEthernet1/0/1
 description DEMO_ACCESS_RENUMBERED
 switchport access vlan 20
 switchport mode access
!
interface GigabitEthernet2/0/1
 description DEMO_ACCESS_UNCHANGED_COLLISION
 switchport access vlan 20
 switchport mode access
!
interface Ethernet1
 description DEMO_UNSUPPORTED_ACCESS_NAME
 switchport access vlan 20
 switchport mode access
!
interface Port-channel10
 description DEMO_PORT_CHANNEL_PARENT
 switchport trunk allowed vlan 20,30,99
 switchport mode trunk
!
interface GigabitEthernet1/0/47
 description DEMO_PORT_CHANNEL_MEMBER_A
 switchport trunk allowed vlan 20,30,99
 switchport trunk allowed vlan add 120
 switchport mode trunk
 channel-group 10 mode active
!
interface GigabitEthernet2/0/48
 description DEMO_PORT_CHANNEL_MEMBER_B
 switchport trunk allowed vlan 20,30,99
 switchport mode trunk
 channel-group 10 mode active
!
interface GigabitEthernet3/0/48
 description DEMO_KNOWN_UPLINK
 switchport trunk allowed vlan 20,30,99
 switchport mode trunk
!
interface GigabitEthernet1/0/24
 description DEMO_MALFORMED_TRUNK_AFTER_MEMBER_REMAP
 switchport trunk allowed vlans 20,30,99
 switchport mode trunk
!
interface GigabitEthernet1/0/25
 description DEMO_UNRESTRICTED_TRUNK_AFTER_MEMBER_REMAP
 switchport mode trunk
!
"""
        raw_profile = make_profile_dict()
        raw_profile["stack_translation"]["member_mapping"] = {1: 2, 2: 2, 3: 3}
        raw_profile["review_gates"]["always_review"] = []
        raw_profile["interface_translation"]["explicit_mappings"] = {
            "GigabitEthernet3/0/48": "TenGigabitEthernet3/1/1",
        }
        raw_profile["uplinks"]["detection"]["known_source_ports"] = [
            "GigabitEthernet3/0/48",
        ]
        raw_profile["uplinks"]["destination"]["mappings"] = {
            "GigabitEthernet3/0/48": "TenGigabitEthernet3/1/1",
        }
        source = parse_source_config(config)
        schema = build_profile_schema(raw_profile)

        plan = build_target_refresh_plan(source, schema)
        source_interfaces = {interface.name: interface for interface in source.interfaces}
        access_targets = {
            access_port.source_interface: access_port
            for access_port in plan.access_ports
        }
        uplinks = {
            uplink.source_interface: uplink
            for uplink in plan.uplinks
        }

        self.assertEqual(
            access_targets["GigabitEthernet1/0/1"].target_interface,
            "GigabitEthernet2/0/1",
        )
        self.assertIn(
            "stack_member_mapping",
            access_targets["GigabitEthernet1/0/1"].review_flags,
        )
        self.assertEqual(
            access_targets["GigabitEthernet2/0/1"].target_interface,
            "GigabitEthernet2/0/1",
        )
        self.assertIsNone(access_targets["Ethernet1"].target_interface)
        self.assertIn(
            "unsupported_interface_name",
            access_targets["Ethernet1"].review_flags,
        )
        self.assertEqual(
            access_targets["Ethernet1"].mapping_evidence.review_urgency,
            "WARNING_UNMAPPED",
        )

        self.assertEqual(len(plan.port_channels), 1)
        self.assertEqual(plan.port_channels[0].channel_group, "10")
        self.assertNotIn("Port-channel10", uplinks)
        self.assertEqual(
            [
                (member.source_interface, member.target_interface)
                for member in plan.port_channels[0].member_interfaces
            ],
            [
                ("GigabitEthernet1/0/47", "GigabitEthernet2/0/47"),
                ("GigabitEthernet2/0/48", "GigabitEthernet2/0/48"),
            ],
        )
        self.assertEqual(
            plan.port_channels[0].member_interfaces[0].trunk_allowed_vlan_lines,
            (
                "switchport trunk allowed vlan 20,30,99",
                "switchport trunk allowed vlan add 120",
            ),
        )
        self.assertTrue(plan.port_channels[0].member_interfaces[0].is_trunk)
        self.assertEqual(
            plan.port_channels[0].member_interfaces[0].channel_group_mode,
            "active",
        )
        self.assertEqual(
            source_interfaces["GigabitEthernet1/0/47"].trunk_allowed_vlan_lines,
            (
                "switchport trunk allowed vlan 20,30,99",
                "switchport trunk allowed vlan add 120",
            ),
        )

        self.assertEqual(
            uplinks["GigabitEthernet3/0/48"].target_interface,
            "TenGigabitEthernet3/1/1",
        )
        self.assertEqual(
            uplinks["GigabitEthernet1/0/24"].malformed_trunk_allowed_vlan_lines,
            ("switchport trunk allowed vlans 20,30,99",),
        )
        self.assertEqual(
            uplinks["GigabitEthernet1/0/25"].trunk_allowed_vlan_lines,
            (),
        )
        self.assertEqual(
            uplinks["GigabitEthernet1/0/25"].malformed_trunk_allowed_vlan_lines,
            (),
        )
        self.assertIn("malformed_trunk_allowed_vlans", plan.review_flags)
        self.assertIn("target_interface_collision", plan.review_flags)
        self.assertIn("unmapped_interfaces", plan.review_flags)
        self.assertTrue(
            any("GigabitEthernet2/0/1" in warning for warning in plan.warnings)
        )
        self.assertEqual(
            access_targets["GigabitEthernet1/0/1"].mapping_evidence.applied_rule_type,
            "STACK_REMAP",
        )
        self.assertEqual(
            access_targets["GigabitEthernet2/0/1"].mapping_evidence.applied_rule_type,
            "STACK_IDENTITY",
        )
        self.assertTrue(
            access_targets["GigabitEthernet1/0/1"].mapping_evidence.is_collision
        )
        self.assertEqual(
            access_targets["GigabitEthernet1/0/1"].mapping_evidence.collision_group,
            "GROUP_GigabitEthernet2/0/1",
        )
        self.assertEqual(
            access_targets["GigabitEthernet1/0/1"].mapping_evidence.collision_partners,
            ("GigabitEthernet2/0/1",),
        )
        self.assertTrue(
            access_targets["GigabitEthernet2/0/1"].mapping_evidence.is_collision
        )
        self.assertEqual(
            access_targets["GigabitEthernet2/0/1"].mapping_evidence.collision_partners,
            ("GigabitEthernet1/0/1",),
        )

    def test_clean_stack_member_remap_warns_without_collisions(self):
        config = """hostname DEMO-CLEAN-STACK
!
interface GigabitEthernet1/0/1
 description DEMO_MEMBER_1_ACCESS_A
 switchport access vlan 20
 switchport mode access
!
interface GigabitEthernet1/0/2
 description DEMO_MEMBER_1_ACCESS_B
 switchport access vlan 20
 switchport mode access
!
interface GigabitEthernet2/0/1
 description DEMO_MEMBER_2_ACCESS_A
 switchport access vlan 30
 switchport mode access
!
interface GigabitEthernet2/0/2
 description DEMO_MEMBER_2_ACCESS_B
 switchport access vlan 30
 switchport mode access
!
"""
        raw_profile = make_profile_dict()
        raw_profile["stack_translation"]["member_mapping"] = {1: 3, 2: 4}
        raw_profile["review_gates"]["always_review"] = []
        raw_profile["interface_translation"]["explicit_mappings"] = {}
        raw_profile["uplinks"]["detection"]["known_source_ports"] = []
        raw_profile["uplinks"]["destination"]["mappings"] = {}
        source = parse_source_config(config)
        schema = build_profile_schema(raw_profile)

        plan = build_target_refresh_plan(source, schema)
        target_by_source = {
            access_port.source_interface: access_port
            for access_port in plan.access_ports
        }

        self.assertEqual(len(plan.access_ports), 4)
        self.assertEqual(
            target_by_source["GigabitEthernet1/0/1"].target_interface,
            "GigabitEthernet3/0/1",
        )
        self.assertEqual(
            target_by_source["GigabitEthernet1/0/2"].target_interface,
            "GigabitEthernet3/0/2",
        )
        self.assertEqual(
            target_by_source["GigabitEthernet2/0/1"].target_interface,
            "GigabitEthernet4/0/1",
        )
        self.assertEqual(
            target_by_source["GigabitEthernet2/0/2"].target_interface,
            "GigabitEthernet4/0/2",
        )

        for access_port in plan.access_ports:
            self.assertFalse(access_port.mapping_evidence.is_collision)
            self.assertIsNone(access_port.mapping_evidence.collision_group)
            self.assertEqual(access_port.mapping_evidence.collision_partners, ())
            self.assertEqual(
                access_port.mapping_evidence.review_urgency,
                "WARNING_STACK_REMAP",
            )
            self.assertEqual(
                access_port.mapping_evidence.applied_rule_type,
                "STACK_REMAP",
            )

        self.assertNotIn("target_interface_collision", plan.review_flags)
        self.assertIn("stack_member_mapping", plan.review_flags)
        self.assertEqual(plan.warnings, ())
        self.assertEqual(plan.audit_summary.collisions_count, 0)
        self.assertEqual(plan.audit_summary.member_shifts_count, 4)
        self.assertFalse(plan.audit_summary.is_completely_clean)

    def test_ordered_port_ranges_support_mixed_target_interface_names(self):
        config = """hostname DEMO-MIXED-RANGE
!
interface GigabitEthernet1/0/1
 switchport access vlan 20
 switchport mode access
!
interface GigabitEthernet1/0/36
 switchport access vlan 20
 switchport mode access
!
interface GigabitEthernet1/0/37
 switchport access vlan 30
 switchport mode access
!
interface GigabitEthernet1/0/48
 switchport access vlan 30
 switchport mode access
!
"""
        raw_profile = make_profile_dict()
        raw_profile["stack_translation"]["member_mapping"] = {1: 1}
        raw_profile["review_gates"]["always_review"] = []
        raw_profile["interface_translation"]["explicit_mappings"] = {}
        raw_profile["interface_translation"]["access_ports"] = {
            "mode": "ordered_port_ranges",
            "range_rules": [
                {
                    "rule_name": "C9300-48UXM candidate ports 1-36",
                    "source_ports": "1-36",
                    "target_pattern": "FiveGigabitEthernet{member}/0/{port}",
                    "verification_level": "cisco_derived_candidate",
                },
                {
                    "rule_name": "C9300-48UXM candidate ports 37-48",
                    "source_ports": "37-48",
                    "target_pattern": "TenGigabitEthernet{member}/0/{port}",
                    "verification_level": "cisco_derived_candidate",
                },
            ],
        }
        source = parse_source_config(config)
        schema = build_profile_schema(raw_profile)

        plan = build_target_refresh_plan(source, schema)
        targets = {
            access_port.source_interface: access_port
            for access_port in plan.access_ports
        }

        self.assertEqual(
            targets["GigabitEthernet1/0/1"].target_interface,
            "FiveGigabitEthernet1/0/1",
        )
        self.assertEqual(
            targets["GigabitEthernet1/0/36"].target_interface,
            "FiveGigabitEthernet1/0/36",
        )
        self.assertEqual(
            targets["GigabitEthernet1/0/37"].target_interface,
            "TenGigabitEthernet1/0/37",
        )
        self.assertEqual(
            targets["GigabitEthernet1/0/48"].target_interface,
            "TenGigabitEthernet1/0/48",
        )

        for access_port in plan.access_ports:
            self.assertEqual(
                access_port.mapping_evidence.applied_rule_type,
                "ACCESS_PORT_RANGE_RULE",
            )
            self.assertIn("target_profile_verification", access_port.review_flags)
            self.assertEqual(
                access_port.mapping_evidence.review_urgency,
                "WARNING_PROFILE_REVIEW",
            )
            self.assertIn(
                "verification_level='cisco_derived_candidate'",
                access_port.mapping_evidence.rule_details,
            )
        self.assertIn("target_profile_verification", plan.review_flags)

    def test_ordered_port_ranges_support_target_port_offsets_for_expansion_layouts(self):
        config = """hostname DEMO-EXPANSION-LAYOUT
!
interface GigabitEthernet1/0/1
 switchport access vlan 20
 switchport mode access
!
interface GigabitEthernet1/0/8
 switchport access vlan 20
 switchport mode access
!
interface GigabitEthernet1/0/9
 switchport access vlan 30
 switchport mode access
!
interface GigabitEthernet1/0/16
 switchport access vlan 30
 switchport mode access
!
"""
        raw_profile = make_profile_dict()
        raw_profile["stack_translation"]["enabled"] = False
        raw_profile["review_gates"]["always_review"] = []
        raw_profile["interface_translation"]["explicit_mappings"] = {}
        raw_profile["interface_translation"]["access_ports"] = {
            "mode": "ordered_port_ranges",
            "range_rules": [
                {
                    "rule_name": "base access block",
                    "source_ports": "1-8",
                    "target_pattern": "GigabitEthernet1/2/{target_port}",
                    "target_start": 1,
                },
                {
                    "rule_name": "expansion module slot 3",
                    "source_ports": "9-16",
                    "target_pattern": "GigabitEthernet1/3/{target_port}",
                    "target_start": 1,
                },
            ],
        }
        source = parse_source_config(config)
        schema = build_profile_schema(raw_profile)

        plan = build_target_refresh_plan(source, schema)
        targets = {
            access_port.source_interface: access_port
            for access_port in plan.access_ports
        }

        self.assertEqual(
            targets["GigabitEthernet1/0/1"].target_interface,
            "GigabitEthernet1/2/1",
        )
        self.assertEqual(
            targets["GigabitEthernet1/0/8"].target_interface,
            "GigabitEthernet1/2/8",
        )
        self.assertEqual(
            targets["GigabitEthernet1/0/9"].target_interface,
            "GigabitEthernet1/3/1",
        )
        self.assertEqual(
            targets["GigabitEthernet1/0/16"].target_interface,
            "GigabitEthernet1/3/8",
        )

    def test_explicit_mapping_overrides_ordered_port_range_rule(self):
        config = """hostname DEMO-EXPLICIT-OVERRIDE
!
interface GigabitEthernet1/0/12
 switchport access vlan 20
 switchport mode access
!
"""
        raw_profile = make_profile_dict()
        raw_profile["stack_translation"]["member_mapping"] = {1: 1}
        raw_profile["review_gates"]["always_review"] = []
        raw_profile["interface_translation"]["explicit_mappings"] = {
            "GigabitEthernet1/0/12": "TenGigabitEthernet1/1/8",
        }
        raw_profile["interface_translation"]["access_ports"] = {
            "mode": "ordered_port_ranges",
            "range_rules": [
                {
                    "source_ports": "1-48",
                    "target_pattern": "GigabitEthernet{member}/0/{port}",
                },
            ],
        }
        source = parse_source_config(config)
        schema = build_profile_schema(raw_profile)

        plan = build_target_refresh_plan(source, schema)

        self.assertEqual(len(plan.access_ports), 1)
        self.assertEqual(
            plan.access_ports[0].target_interface,
            "TenGigabitEthernet1/1/8",
        )
        self.assertEqual(
            plan.access_ports[0].mapping_evidence.applied_rule_type,
            "EXPLICIT_INTERFACE",
        )

    def test_ordered_port_ranges_leave_unmatched_ports_unmapped_without_default(self):
        config = """hostname DEMO-UNMATCHED-RANGE
!
interface GigabitEthernet1/0/49
 switchport access vlan 20
 switchport mode access
!
"""
        raw_profile = make_profile_dict()
        raw_profile["stack_translation"]["member_mapping"] = {1: 1}
        raw_profile["review_gates"]["always_review"] = []
        raw_profile["interface_translation"]["explicit_mappings"] = {}
        raw_profile["interface_translation"]["access_ports"] = {
            "mode": "ordered_port_ranges",
            "range_rules": [
                {
                    "source_ports": "1-48",
                    "target_pattern": "GigabitEthernet{member}/0/{port}",
                },
            ],
        }
        raw_profile["uplinks"]["detection"]["known_source_ports"] = []
        raw_profile["uplinks"]["detection"]["treat_trunks_as_candidates"] = False
        source = parse_source_config(config)
        schema = build_profile_schema(raw_profile)

        plan = build_target_refresh_plan(source, schema)

        self.assertEqual(len(plan.access_ports), 1)
        self.assertIsNone(plan.access_ports[0].target_interface)
        self.assertIn("no_access_port_range_rule", plan.access_ports[0].review_flags)
        self.assertIn("unmapped_interfaces", plan.review_flags)
        self.assertEqual(
            plan.access_ports[0].mapping_evidence.applied_rule_type,
            "NO_ACCESS_PORT_RANGE_RULE",
        )
        self.assertEqual(
            plan.access_ports[0].mapping_evidence.review_urgency,
            "WARNING_UNMAPPED",
        )

    def test_ordered_port_ranges_can_use_default_target_pattern_after_overrides(self):
        config = """hostname DEMO-DEFAULT-RANGE-FALLBACK
!
interface GigabitEthernet1/0/1
 switchport access vlan 20
 switchport mode access
!
interface GigabitEthernet1/0/48
 switchport access vlan 30
 switchport mode access
!
"""
        raw_profile = make_profile_dict()
        raw_profile["stack_translation"]["member_mapping"] = {1: 1}
        raw_profile["review_gates"]["always_review"] = []
        raw_profile["interface_translation"]["explicit_mappings"] = {}
        raw_profile["interface_translation"]["access_ports"] = {
            "mode": "ordered_port_ranges",
            "default_target_pattern": "GigabitEthernet{member}/0/{port}",
            "range_rules": [
                {
                    "source_ports": "48",
                    "target_pattern": "TenGigabitEthernet{member}/0/{port}",
                },
            ],
        }
        source = parse_source_config(config)
        schema = build_profile_schema(raw_profile)

        plan = build_target_refresh_plan(source, schema)
        targets = {
            access_port.source_interface: access_port
            for access_port in plan.access_ports
        }

        self.assertEqual(
            targets["GigabitEthernet1/0/1"].target_interface,
            "GigabitEthernet1/0/1",
        )
        self.assertEqual(
            targets["GigabitEthernet1/0/1"].mapping_evidence.applied_rule_type,
            "DEFAULT_ACCESS_PATTERN",
        )
        self.assertEqual(
            targets["GigabitEthernet1/0/48"].target_interface,
            "TenGigabitEthernet1/0/48",
        )
        self.assertEqual(
            targets["GigabitEthernet1/0/48"].mapping_evidence.applied_rule_type,
            "ACCESS_PORT_RANGE_RULE",
        )


if __name__ == "__main__":
    unittest.main()
