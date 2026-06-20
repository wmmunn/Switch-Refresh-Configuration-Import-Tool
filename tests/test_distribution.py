import sys
import tkinter as tk
import unittest
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_DIR / "src"
sys.path.insert(0, str(SRC_DIR))

from switch_refresh_config_import_tool import app as MODULE


TEMPLATE_PATH = (
    SRC_DIR
    / "switch_refresh_config_import_tool"
    / "assets"
    / "generic_refresh_build_template.txt"
)
CONFIG_PATH = (
    SRC_DIR
    / "switch_refresh_config_import_tool"
    / "assets"
    / "generic_existing_switch_config.txt"
)


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


class SanitizedDistributionTests(unittest.TestCase):
    def test_template_contains_every_supported_placeholder(self):
        template = TEMPLATE_PATH.read_text(encoding="utf-8")
        for placeholder in MODULE.PLACEHOLDERS:
            with self.subTest(placeholder=placeholder):
                self.assertIn(placeholder, template)

    def test_template_contains_no_example_network_values(self):
        template = TEMPLATE_PATH.read_text(encoding="utf-8").lower()
        forbidden = (
            "10.0.0.",
            "192.168.",
            "example.com",
            "corp",
        )
        for value in forbidden:
            with self.subTest(value=value):
                self.assertNotIn(value, template)

    def test_sanitized_extraction_uses_generic_template(self):
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
        output = MODULE.apply_template(MODULE.load_bundled_template_text(), values)

        self.assertIn("SANITIZED-SW", output)
        self.assertIn("interface G1/0/1", output)
        self.assertNotIn("{{HOSTNAME}}", output)

    def test_legacy_extraction_skips_empty_physical_interface_blocks(self):
        from switch_refresh_config_import_tool.core import extract_access_port_configs

        config = """hostname SANITIZED-SW
!
interface GigabitEthernet1/0/50
!
interface GigabitEthernet1/0/51
!
interface GigabitEthernet1/0/52
 description DEMO_UNUSED_WITH_CONFIG
 shutdown
!
"""
        output = extract_access_port_configs(config)

        self.assertNotIn("interface G1/0/50", output)
        self.assertNotIn("interface G1/0/51", output)
        self.assertIn("interface G1/0/52", output)
        self.assertIn(" shutdown", output)

    def test_generic_existing_config_is_sanitized_and_exercises_extraction(self):
        config = CONFIG_PATH.read_text(encoding="utf-8")
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

    def test_generic_engine_profile_is_valid_schema(self):
        from switch_refresh_config_import_tool.profile_schema import build_profile_schema

        profile = MODULE.build_generic_engine_profile_dict()
        schema = build_profile_schema(profile)

        self.assertEqual(schema.profile.name, "Generic Cisco IOS Engine Review Profile")
        self.assertEqual(schema.interface_translation.access_ports.mode, "same_member_same_port")

    def test_gui_default_window_width_accommodates_target_build_planner_controls(self):
        root = tk.Tk()
        root.withdraw()
        try:
            app = MODULE.SwitchRefreshConfigImportApp(root)
            root.update_idletasks()

            requested_width = root.winfo_reqwidth()
            current_width = root.winfo_width()

            self.assertGreaterEqual(current_width, 1280)
            self.assertLessEqual(requested_width, current_width)
            self.assertEqual(app.engine_profile_uplink_mode_var.get(), MODULE.UPLINK_MODE_CUSTOM)
        finally:
            root.destroy()

    def test_legacy_workflow_labels_distinguish_engine_profile_controls(self):
        root = tk.Tk()
        root.withdraw()
        try:
            MODULE.SwitchRefreshConfigImportApp(root)
            root.update_idletasks()

            widget_text = "\n".join(_collect_widget_text(root))

            self.assertIn("Legacy output port prefix", widget_text)
            self.assertIn(
                "Extraction Workflow only. Profile Engine uses Target Profile Options.",
                widget_text,
            )
            self.assertNotIn("New access port prefix", widget_text)
            self.assertNotIn("G produces G1/0/5; Fi produces Fi1/0/5.", widget_text)
        finally:
            root.destroy()

    def test_generic_engine_review_output_uses_renderer_placeholders(self):
        config = """hostname SANITIZED-ENGINE-SW
!
interface GigabitEthernet1/0/1
 description DEMO_ACCESS
 switchport access vlan 20
 switchport mode access
!
"""
        output, plan = MODULE.generate_engine_review_output(
            config,
            MODULE.build_generic_engine_profile_dict(),
            MODULE.load_generic_engine_template_text(),
        )

        self.assertIn("SANITIZED-ENGINE-SW", output)
        self.assertIn("! REVIEW: Generated output is review material", output)
        self.assertIn("interface GigabitEthernet1/0/1", output)
        self.assertNotIn("{{ENGINE_REVIEW_SUMMARY}}", output)
        self.assertEqual(len(plan.access_ports), 1)

    def test_engine_profile_json_loader_rejects_non_object(self):
        with self.assertRaisesRegex(ValueError, "must contain an object"):
            MODULE.load_profile_json_text("[]")

    def test_custom_engine_profile_builder_generates_valid_schema(self):
        from switch_refresh_config_import_tool.profile_schema import build_profile_schema

        profile = MODULE.build_custom_engine_profile_dict(
            MODULE.ACCESS_LAYOUT_TENGIGABIT,
            "",
            "1=1, 2=2",
            "GigabitEthernet1/0/49=TenGigabitEthernet1/1/1\n"
            "GigabitEthernet2/0/49=TenGigabitEthernet2/1/1\n",
        )
        schema = build_profile_schema(profile)

        self.assertEqual(schema.profile.name, "Custom Cisco IOS Engine Review Profile")
        self.assertEqual(
            schema.interface_translation.access_ports.target_pattern,
            "TenGigabitEthernet{member}/0/{port}",
        )
        self.assertEqual(schema.stack_translation.member_mapping, {1: 1, 2: 2})
        self.assertEqual(
            schema.uplinks.destination.mappings["GigabitEthernet1/0/49"],
            "TenGigabitEthernet1/1/1",
        )

    def test_custom_engine_profile_builder_supports_mixed_access_layout(self):
        profile = MODULE.build_custom_engine_profile_dict(
            MODULE.ACCESS_LAYOUT_MIXED_GIGABIT_FIVEGIGABIT,
            "",
            "1=1",
            "",
        )
        access_ports = profile["interface_translation"]["access_ports"]

        self.assertEqual(access_ports["mode"], "ordered_port_ranges")
        self.assertEqual(len(access_ports["range_rules"]), 2)
        self.assertEqual(
            access_ports["range_rules"][1]["target_pattern"],
            "FiveGigabitEthernet{member}/0/{port}",
        )

    def test_custom_target_pattern_requires_member_and_port_tokens(self):
        with self.assertRaisesRegex(ValueError, "must include"):
            MODULE.build_custom_engine_profile_dict(
                MODULE.ACCESS_LAYOUT_CUSTOM_PATTERN,
                "TenGigabitEthernet1/0/{port}",
                "1=1",
                "",
            )

    def test_stack_member_mapping_rejects_non_numeric_values(self):
        with self.assertRaisesRegex(ValueError, "numeric member IDs"):
            MODULE.parse_stack_member_mapping_text("1=one")

    def test_stack_member_mapping_rejects_members_outside_one_to_eight(self):
        with self.assertRaisesRegex(ValueError, "between 1 and 8"):
            MODULE.parse_stack_member_mapping_text("1=9")

    def test_site_default_uplink_mode_uses_last_stack_member_token(self):
        profile = MODULE.build_custom_engine_profile_dict(
            MODULE.ACCESS_LAYOUT_TENGIGABIT,
            "",
            "1=1,2=2",
            "GigabitEthernet1/0/49\nGigabitEthernet1/0/50\n",
            MODULE.UPLINK_MODE_SITE_DEFAULT,
        )

        self.assertEqual(
            profile["uplinks"]["destination"]["mappings"]["GigabitEthernet1/0/49"],
            MODULE.SITE_DEFAULT_UPLINK_TARGET,
        )
        self.assertEqual(
            profile["interface_translation"]["explicit_mappings"][
                "GigabitEthernet1/0/50"
            ],
            MODULE.SITE_DEFAULT_UPLINK_TARGET,
        )

    def test_site_default_uplink_token_resolves_to_highest_target_stack_member(self):
        config = """hostname DEMO-SITE-DEFAULT
!
interface GigabitEthernet1/0/49
 description DEMO_UPLINK
 switchport trunk allowed vlan 20
 switchport mode trunk
!
"""
        profile = MODULE.build_custom_engine_profile_dict(
            MODULE.ACCESS_LAYOUT_TENGIGABIT,
            "",
            "1=1,2=4",
            "GigabitEthernet1/0/49\n",
            MODULE.UPLINK_MODE_SITE_DEFAULT,
        )

        self.assertEqual(
            profile["uplinks"]["destination"]["mappings"]["GigabitEthernet1/0/49"],
            MODULE.SITE_DEFAULT_UPLINK_TARGET,
        )

        _output, plan = MODULE.generate_engine_review_output(
            config,
            profile,
            MODULE.load_generic_engine_template_text(),
        )

        self.assertEqual(
            plan.uplinks[0].target_interface,
            "TenGigabitEthernet4/1/8",
        )

    def test_site_default_uplink_mode_accepts_mapping_style_source_lines(self):
        mappings = MODULE.build_uplink_profile_mappings(
            "GigabitEthernet1/0/49=TenGigabitEthernet1/1/1\n",
            MODULE.UPLINK_MODE_SITE_DEFAULT,
        )

        self.assertEqual(
            mappings,
            {"GigabitEthernet1/0/49": MODULE.SITE_DEFAULT_UPLINK_TARGET},
        )

    def test_mapping_text_accepts_equals_or_comma_lines(self):
        mappings = MODULE.parse_interface_mapping_text(
            "GigabitEthernet1/0/49=TenGigabitEthernet1/1/1\n"
            "GigabitEthernet1/0/50,TenGigabitEthernet1/1/2\n"
        )

        self.assertEqual(
            mappings["GigabitEthernet1/0/50"],
            "TenGigabitEthernet1/1/2",
        )

    def test_structured_uplink_rows_build_custom_mapping_text(self):
        text = MODULE.build_structured_uplink_mapping_text(
            (
                ("GigabitEthernet1/0/49", "TenGigabitEthernet1/1/1"),
                ("", ""),
            ),
            MODULE.UPLINK_MODE_CUSTOM,
        )

        self.assertEqual(
            text,
            "GigabitEthernet1/0/49=TenGigabitEthernet1/1/1",
        )

    def test_structured_uplink_rows_build_site_default_source_list(self):
        text = MODULE.build_structured_uplink_mapping_text(
            (
                ("GigabitEthernet1/0/49", ""),
                ("GigabitEthernet2/0/49", "ignored in site default mode"),
            ),
            MODULE.UPLINK_MODE_SITE_DEFAULT,
        )

        self.assertEqual(
            text,
            "GigabitEthernet1/0/49\nGigabitEthernet2/0/49",
        )

    def test_structured_uplink_rows_reject_missing_custom_target(self):
        with self.assertRaisesRegex(ValueError, "missing a target"):
            MODULE.build_structured_uplink_mapping_text(
                (("GigabitEthernet1/0/49", ""),),
                MODULE.UPLINK_MODE_CUSTOM,
            )


if __name__ == "__main__":
    unittest.main()
