import sys
import tkinter as tk
import unittest
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_DIR / "src"
sys.path.insert(0, str(SRC_DIR))

from switch_refresh_config_import_tool import app as MODULE
from switch_refresh_config_import_tool.mapping_engine import (
    build_target_refresh_plan,
    classify_interface_role,
)
from switch_refresh_config_import_tool.profile_schema import build_profile_schema
from switch_refresh_config_import_tool.source_parser import parse_source_config
from switch_refresh_config_import_tool.visual_mapping import (
    ACCESS_LAYOUT_GIGABIT,
    ACCESS_LAYOUT_TENGIGABIT,
    PortMappingPair,
    ROLE_ACCESS,
    ROLE_PORT_CHANNEL_MEMBER,
    ROLE_UPLINK,
    TARGET_CAGE_UPLINK,
    TargetChassisSpec,
    build_profile_fragments,
    build_target_chassis,
    build_visual_mapping_status,
    chassis_target_members,
    classify_source_ports,
    merge_visual_mappings_into_profile,
    occupancy,
    pairs_from_profile,
    set_mapping,
)
from switch_refresh_config_import_tool.visual_mapping_window import (
    open_visual_mapping_window,
)


TWO_UPLINK_CONFIG = """hostname DEMO-TWO-UPLINKS
!
interface GigabitEthernet1/0/1
 description DEMO_ACCESS
 switchport access vlan 20
 switchport mode access
!
interface GigabitEthernet1/0/23
 description DEMO_UPLINK_A
 switchport trunk allowed vlan 20,99
 switchport mode trunk
!
interface GigabitEthernet1/0/24
 description DEMO_UPLINK_B
 switchport trunk allowed vlan 20,99
 switchport mode trunk
!
"""

PORT_CHANNEL_UPLINK_CONFIG = """hostname DEMO-PC-UPLINKS
!
interface GigabitEthernet1/0/1
 switchport access vlan 20
 switchport mode access
!
interface GigabitEthernet1/0/49
 description DEMO_PORT_CHANNEL_UPLINK_A
 switchport trunk allowed vlan 20,99
 switchport mode trunk
 channel-group 1 mode active
!
interface GigabitEthernet1/0/52
 description DEMO_PORT_CHANNEL_UPLINK_B
 switchport trunk allowed vlan 20,99
 switchport mode trunk
 channel-group 1 mode active
!
"""


def make_profile():
    return MODULE.build_generic_engine_profile_dict()


class VisualMappingTests(unittest.TestCase):
    def test_two_source_trunks_are_uplink_roles_and_one_blank_is_visible(self):
        source = parse_source_config(TWO_UPLINK_CONFIG)
        schema = build_profile_schema(make_profile())
        cells = classify_source_ports(source, schema)
        roles = {cell.name: cell.role for cell in cells}

        self.assertEqual(roles["GigabitEthernet1/0/1"], ROLE_ACCESS)
        self.assertEqual(roles["GigabitEthernet1/0/23"], ROLE_UPLINK)
        self.assertEqual(roles["GigabitEthernet1/0/24"], ROLE_UPLINK)

        target_cells = build_target_chassis(
            TargetChassisSpec(access_layout=ACCESS_LAYOUT_GIGABIT)
        )
        pairs = (
            PortMappingPair(
                "GigabitEthernet1/0/23",
                "TenGigabitEthernet1/1/1",
            ),
        )
        status = build_visual_mapping_status(cells, target_cells, pairs)

        self.assertEqual(status.unmapped_uplink_sources, ("GigabitEthernet1/0/24",))
        self.assertIn("blank second uplink", " ".join(status.warnings))

    def test_port_channel_members_are_not_classified_as_uplinks(self):
        source = parse_source_config(PORT_CHANNEL_UPLINK_CONFIG)
        schema = build_profile_schema(make_profile())

        self.assertEqual(
            classify_interface_role(source.interfaces[1], schema),
            ROLE_PORT_CHANNEL_MEMBER,
        )
        cells = classify_source_ports(source, schema)
        roles = {cell.name: cell.role for cell in cells}
        self.assertEqual(roles["GigabitEthernet1/0/49"], ROLE_PORT_CHANNEL_MEMBER)
        self.assertEqual(roles["GigabitEthernet1/0/52"], ROLE_PORT_CHANNEL_MEMBER)
        self.assertNotIn(ROLE_UPLINK, roles.values())

    def test_port_channel_member_on_uplink_slot_is_called_out(self):
        source = parse_source_config(PORT_CHANNEL_UPLINK_CONFIG)
        schema = build_profile_schema(make_profile())
        cells = classify_source_ports(source, schema)
        target_cells = build_target_chassis(
            TargetChassisSpec(access_layout=ACCESS_LAYOUT_TENGIGABIT)
        )
        pairs = (
            PortMappingPair(
                "GigabitEthernet1/0/49",
                "TenGigabitEthernet1/1/1",
            ),
            PortMappingPair(
                "GigabitEthernet1/0/52",
                "TenGigabitEthernet1/0/52",
            ),
        )
        status = build_visual_mapping_status(cells, target_cells, pairs)

        self.assertEqual(
            status.port_channel_on_uplink_slots,
            (("GigabitEthernet1/0/49", "TenGigabitEthernet1/1/1"),),
        )
        self.assertIn("Port-channel member(s) land on uplink slot(s)", " ".join(status.warnings))

    def test_duplicate_targets_are_reported_as_collisions(self):
        source = parse_source_config(TWO_UPLINK_CONFIG)
        schema = build_profile_schema(make_profile())
        cells = classify_source_ports(source, schema)
        target_cells = build_target_chassis(
            TargetChassisSpec(access_layout=ACCESS_LAYOUT_GIGABIT)
        )
        pairs = (
            PortMappingPair("GigabitEthernet1/0/23", "TenGigabitEthernet1/1/8"),
            PortMappingPair("GigabitEthernet1/0/24", "TenGigabitEthernet1/1/8"),
        )
        status = build_visual_mapping_status(cells, target_cells, pairs)
        claimed = occupancy(pairs)

        self.assertEqual(status.collision_targets, ("TenGigabitEthernet1/1/8",))
        self.assertEqual(len(claimed["TenGigabitEthernet1/1/8"]), 2)

    def test_profile_fragments_keep_uplinks_and_port_channel_overrides_apart(self):
        source = parse_source_config(PORT_CHANNEL_UPLINK_CONFIG)
        schema = build_profile_schema(make_profile())
        source_cells = classify_source_ports(source, schema)
        target_cells = build_target_chassis(
            TargetChassisSpec(access_layout=ACCESS_LAYOUT_TENGIGABIT)
        )
        pairs = (
            PortMappingPair("GigabitEthernet1/0/1", "TenGigabitEthernet1/0/1"),
            PortMappingPair("GigabitEthernet1/0/49", "TenGigabitEthernet1/1/1"),
            PortMappingPair("GigabitEthernet1/0/52", "TenGigabitEthernet1/1/2"),
        )

        fragments = build_profile_fragments(pairs, source_cells, target_cells)

        self.assertEqual(
            fragments.explicit_mappings["GigabitEthernet1/0/1"],
            "TenGigabitEthernet1/0/1",
        )
        self.assertEqual(
            fragments.uplink_mappings["GigabitEthernet1/0/49"],
            "TenGigabitEthernet1/1/1",
        )
        self.assertEqual(
            fragments.uplink_mappings["GigabitEthernet1/0/52"],
            "TenGigabitEthernet1/1/2",
        )
        self.assertNotIn("GigabitEthernet1/0/1", fragments.uplink_mappings)

    def test_applied_visual_pairs_stage_both_uplinks_in_the_engine(self):
        source = parse_source_config(TWO_UPLINK_CONFIG)
        schema = build_profile_schema(make_profile())
        source_cells = classify_source_ports(source, schema)
        target_cells = build_target_chassis(
            TargetChassisSpec(access_layout=ACCESS_LAYOUT_GIGABIT)
        )
        pairs = (
            PortMappingPair("GigabitEthernet1/0/23", "TenGigabitEthernet1/1/1"),
            PortMappingPair("GigabitEthernet1/0/24", "TenGigabitEthernet1/1/2"),
        )
        profile = merge_visual_mappings_into_profile(
            make_profile(),
            build_profile_fragments(pairs, source_cells, target_cells),
        )
        plan = build_target_refresh_plan(source, build_profile_schema(profile))
        uplinks = {
            uplink.source_interface: uplink.target_interface
            for uplink in plan.uplinks
        }

        self.assertEqual(uplinks["GigabitEthernet1/0/23"], "TenGigabitEthernet1/1/1")
        self.assertEqual(uplinks["GigabitEthernet1/0/24"], "TenGigabitEthernet1/1/2")
        self.assertIsNotNone(uplinks["GigabitEthernet1/0/23"])
        self.assertIsNotNone(uplinks["GigabitEthernet1/0/24"])

    def test_target_chassis_includes_uplink_slots_for_each_member(self):
        cells = build_target_chassis(
            TargetChassisSpec(
                access_layout=ACCESS_LAYOUT_TENGIGABIT,
                target_members=chassis_target_members({1: 1, 2: 2}),
            )
        )
        names = {cell.name: cell for cell in cells}

        self.assertEqual(names["TenGigabitEthernet1/0/1"].cage, "access")
        self.assertEqual(names["TenGigabitEthernet2/1/8"].cage, TARGET_CAGE_UPLINK)
        self.assertEqual(names["TenGigabitEthernet1/1/1"].role, ROLE_UPLINK)

    def test_pairs_from_profile_read_explicit_and_uplink_mappings(self):
        profile = make_profile()
        profile["interface_translation"]["explicit_mappings"] = {
            "GigabitEthernet1/0/1": "GigabitEthernet1/0/1",
        }
        profile["uplinks"]["destination"]["mappings"] = {
            "GigabitEthernet1/0/23": "TenGigabitEthernet1/1/1",
        }
        pairs = pairs_from_profile(profile)
        mapped = {pair.source_interface: pair.target_interface for pair in pairs}

        self.assertEqual(mapped["GigabitEthernet1/0/1"], "GigabitEthernet1/0/1")
        self.assertEqual(mapped["GigabitEthernet1/0/23"], "TenGigabitEthernet1/1/1")

    def test_set_mapping_replaces_the_source_target(self):
        pairs = set_mapping((), "GigabitEthernet1/0/23", "TenGigabitEthernet1/1/1")
        pairs = set_mapping(pairs, "GigabitEthernet1/0/23", "TenGigabitEthernet1/1/2")

        self.assertEqual(len(pairs), 1)
        self.assertEqual(pairs[0].target_interface, "TenGigabitEthernet1/1/2")


class VisualMappingWindowTests(unittest.TestCase):
    def test_port_map_window_draws_source_and_target_ports(self):
        source = parse_source_config(TWO_UPLINK_CONFIG)
        schema = build_profile_schema(make_profile())
        source_cells = classify_source_ports(source, schema)
        target_cells = build_target_chassis(
            TargetChassisSpec(access_layout=ACCESS_LAYOUT_GIGABIT)
        )
        applied = []

        root = tk.Tk()
        root.withdraw()
        try:
            window = open_visual_mapping_window(
                root,
                source_cells,
                target_cells,
                (),
                applied.append,
            )
            root.update_idletasks()
            self.assertEqual(window.title(), "Interactive Port Map")
            self.assertTrue(window.winfo_exists())
            window.destroy()
        finally:
            root.destroy()


class VisualMappingGuiWiringTests(unittest.TestCase):
    def test_planner_exposes_open_port_map_control(self):
        root = tk.Tk()
        root.withdraw()
        try:
            app = MODULE.SwitchRefreshConfigImportApp(root)
            root.update_idletasks()
            widget_text = "\n".join(_collect_widget_text(root))
            self.assertIn("Open Port Map", widget_text)
            self.assertTrue(hasattr(app, "open_visual_port_map"))
        finally:
            root.destroy()


def _collect_widget_text(widget):
    values = []
    try:
        text = widget.cget("text")
    except tk.TclError:
        text = ""
    if text:
        values.append(str(text))
    for child in widget.winfo_children():
        values.extend(_collect_widget_text(child))
    return values


if __name__ == "__main__":
    unittest.main()
