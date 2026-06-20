from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

import tkinter as tk
from tkinter import messagebox, ttk

from .core import (
    PLACEHOLDERS,
    TTKBOOTSTRAP_AVAILABLE,
    LabNotesExtractorApp,
    apply_template,
    extract_config_values,
    read_text_file,
    tb,
    write_text_file,
)
from .mapping_engine import build_target_refresh_plan
from .plan_renderer import (
    ENGINE_ACCESS_PORTS,
    ENGINE_COLLISIONS,
    ENGINE_PORT_CHANNELS,
    ENGINE_REVIEW_SUMMARY,
    ENGINE_UNMAPPED_INTERFACES,
    ENGINE_UPLINKS,
    ENGINE_WARNINGS,
    render_plan_template,
)
from .profile_schema import build_profile_schema
from .source_parser import parse_source_config


APP_NAME = "Switch Refresh Configuration Import Tool"
APP_VERSION = "1.1.0"
TEMPLATE_DISPLAY_NAME = "Bundled Generic Refresh Build Template"
TEMPLATE_FILENAME = "generic_refresh_build_template.txt"
CONFIG_DISPLAY_NAME = "Bundled Generic Existing Switch Config"
CONFIG_FILENAME = "generic_existing_switch_config.txt"
ENGINE_PROFILE_DISPLAY_NAME = "Built-in Default Target Profile"
ENGINE_TEMPLATE_DISPLAY_NAME = "Built-in Review Output Template"
MAX_STACK_MEMBERS = 8
ACCESS_LAYOUT_GIGABIT = "48-port GigabitEthernet access"
ACCESS_LAYOUT_TENGIGABIT = "48-port TenGigabitEthernet access"
ACCESS_LAYOUT_FIVEGIGABIT = "48-port FiveGigabitEthernet access"
ACCESS_LAYOUT_MIXED_GIGABIT_FIVEGIGABIT = "Mixed Gi 1-24, Five 25-48"
ACCESS_LAYOUT_CUSTOM_PATTERN = "Custom target pattern"
UPLINK_MODE_CUSTOM = "Custom uplink mappings"
UPLINK_MODE_SITE_DEFAULT = "Use Site Default"
SITE_DEFAULT_UPLINK_TARGET = "TenGigabitEthernet{last_stack_member}/1/8"

ACCESS_LAYOUT_TARGET_PATTERNS = {
    ACCESS_LAYOUT_GIGABIT: "GigabitEthernet{member}/0/{port}",
    ACCESS_LAYOUT_TENGIGABIT: "TenGigabitEthernet{member}/0/{port}",
    ACCESS_LAYOUT_FIVEGIGABIT: "FiveGigabitEthernet{member}/0/{port}",
}
ACCESS_LAYOUT_OPTIONS = (
    ACCESS_LAYOUT_GIGABIT,
    ACCESS_LAYOUT_TENGIGABIT,
    ACCESS_LAYOUT_FIVEGIGABIT,
    ACCESS_LAYOUT_MIXED_GIGABIT_FIVEGIGABIT,
    ACCESS_LAYOUT_CUSTOM_PATTERN,
)
UPLINK_MODE_OPTIONS = (
    UPLINK_MODE_CUSTOM,
    UPLINK_MODE_SITE_DEFAULT,
)
STRUCTURED_UPLINK_ROW_COUNT = 4


def build_generic_engine_profile_dict() -> dict:
    return {
        "profile": {
            "name": "Generic Cisco IOS Engine Review Profile",
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
            "preserve_trunk_allowed_vlans": "review_required",
        },
        "review_gates": {
            "always_review": [],
            "fail_closed_on": ["ambiguous_stack_mapping"],
        },
        "template_mapping": {
            "hostname": "HOSTNAME",
            "access_port_configs": "ACCESS_PORT_CONFIGS",
            "port_channel_interfaces": "PORT_CHANNEL_INTERFACES",
            "port_channel_members": "PORT_CHANNEL_MEMBERS",
            "radius_status": "RADIUS_STATUS",
        },
    }


def build_custom_engine_profile_dict(
    access_layout: str,
    custom_target_pattern: str,
    stack_mapping_text: str,
    uplink_mapping_text: str,
    uplink_mode: str = UPLINK_MODE_CUSTOM,
) -> dict:
    profile = build_generic_engine_profile_dict()
    profile["profile"]["name"] = "Custom Cisco IOS Engine Review Profile"
    profile["stack_translation"]["member_mapping"] = parse_stack_member_mapping_text(
        stack_mapping_text
    )

    access_ports = build_access_port_profile_rules(
        access_layout,
        custom_target_pattern,
    )
    profile["interface_translation"]["access_ports"] = access_ports

    uplink_mappings = build_uplink_profile_mappings(uplink_mapping_text, uplink_mode)
    profile["interface_translation"]["explicit_mappings"] = dict(uplink_mappings)
    profile["uplinks"]["detection"]["known_source_ports"] = list(uplink_mappings)
    profile["uplinks"]["destination"]["mappings"] = dict(uplink_mappings)

    return profile


def build_access_port_profile_rules(
    access_layout: str,
    custom_target_pattern: str,
) -> dict:
    if access_layout in ACCESS_LAYOUT_TARGET_PATTERNS:
        return {
            "mode": "same_member_same_port",
            "target_pattern": ACCESS_LAYOUT_TARGET_PATTERNS[access_layout],
        }

    if access_layout == ACCESS_LAYOUT_MIXED_GIGABIT_FIVEGIGABIT:
        return {
            "mode": "ordered_port_ranges",
            "range_rules": [
                {
                    "source_ports": "1-24",
                    "target_pattern": "GigabitEthernet{member}/0/{port}",
                    "rule_name": "candidate mixed target ports 1-24",
                    "verification_level": "custom_user_defined",
                },
                {
                    "source_ports": "25-48",
                    "target_pattern": "FiveGigabitEthernet{member}/0/{port}",
                    "rule_name": "candidate mixed target ports 25-48",
                    "verification_level": "custom_user_defined",
                },
            ],
        }

    if access_layout == ACCESS_LAYOUT_CUSTOM_PATTERN:
        pattern = custom_target_pattern.strip()
        if not pattern:
            raise ValueError("Custom target pattern is required.")
        if "{member}" not in pattern or "{port}" not in pattern:
            raise ValueError(
                "Custom target pattern must include {member} and {port}."
            )
        return {
            "mode": "same_member_same_port",
            "target_pattern": pattern,
        }

    raise ValueError(f"Unsupported access layout: {access_layout}")


def parse_stack_member_mapping_text(mapping_text: str) -> dict[int, int]:
    normalized_lines = []
    for raw_line in mapping_text.splitlines():
        line = raw_line.strip()
        if "=" in line and "," in line:
            normalized_lines.extend(part.strip() for part in line.split(","))
        else:
            normalized_lines.append(raw_line)

    mapping = parse_key_value_mapping_text("\n".join(normalized_lines))
    if not mapping:
        raise ValueError("At least one stack member mapping is required.")

    member_mapping: dict[int, int] = {}
    for source_member, target_member in mapping.items():
        try:
            source_number = int(source_member)
            target_number = int(target_member)
        except ValueError as exc:
            raise ValueError(
                "Stack member mappings must use numeric member IDs."
            ) from exc

        if source_number < 1 or target_number < 1:
            raise ValueError("Stack member IDs must be positive integers.")
        if source_number > MAX_STACK_MEMBERS or target_number > MAX_STACK_MEMBERS:
            raise ValueError(
                f"Stack member IDs must be between 1 and {MAX_STACK_MEMBERS}."
            )

        member_mapping[source_number] = target_number

    return member_mapping


def build_uplink_profile_mappings(mapping_text: str, uplink_mode: str) -> dict[str, str]:
    if uplink_mode == UPLINK_MODE_CUSTOM:
        return parse_interface_mapping_text(mapping_text)

    if uplink_mode == UPLINK_MODE_SITE_DEFAULT:
        return {
            source_port: SITE_DEFAULT_UPLINK_TARGET
            for source_port in parse_source_interface_list_text(mapping_text)
        }

    raise ValueError(f"Unsupported uplink mode: {uplink_mode}")


def parse_source_interface_list_text(mapping_text: str) -> tuple[str, ...]:
    source_ports = []
    for line_number, raw_line in enumerate(mapping_text.splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#") or line.startswith("!"):
            continue

        if "=" in line:
            source, _target = line.split("=", 1)
        elif "," in line:
            source, _target = line.split(",", 1)
        else:
            source = line

        source = source.strip()
        if not source:
            raise ValueError(f"Uplink line {line_number} has an empty source port.")
        source_ports.append(source)

    return tuple(source_ports)


def build_structured_uplink_mapping_text(
    rows: tuple[tuple[str, str], ...],
    uplink_mode: str,
) -> str:
    lines = []
    for row_number, (source_interface, target_interface) in enumerate(rows, start=1):
        source_interface = source_interface.strip()
        target_interface = target_interface.strip()

        if not source_interface and not target_interface:
            continue
        if not source_interface:
            raise ValueError(f"Uplink row {row_number} is missing a source port.")
        if uplink_mode == UPLINK_MODE_CUSTOM and not target_interface:
            raise ValueError(f"Uplink row {row_number} is missing a target port.")

        if uplink_mode == UPLINK_MODE_SITE_DEFAULT:
            lines.append(source_interface)
        else:
            lines.append(f"{source_interface}={target_interface}")

    return "\n".join(lines)


def parse_interface_mapping_text(mapping_text: str) -> dict[str, str]:
    return parse_key_value_mapping_text(mapping_text)


def parse_key_value_mapping_text(mapping_text: str) -> dict[str, str]:
    mappings: dict[str, str] = {}
    for line_number, raw_line in enumerate(mapping_text.splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#") or line.startswith("!"):
            continue

        if "=" in line:
            source, target = line.split("=", 1)
        elif "," in line:
            source, target = line.split(",", 1)
        else:
            raise ValueError(
                f"Mapping line {line_number} must use source=target or source,target."
            )

        source = source.strip()
        target = target.strip()
        if not source or not target:
            raise ValueError(f"Mapping line {line_number} has an empty value.")
        mappings[source] = target

    return mappings


def load_profile_json_text(profile_text: str) -> dict:
    loaded = json.loads(profile_text)
    if not isinstance(loaded, dict):
        raise ValueError("Target profile file must contain an object at the top level.")
    return loaded


def load_generic_engine_profile_text() -> str:
    return json.dumps(build_generic_engine_profile_dict(), indent=2) + "\n"


def load_generic_engine_template_text() -> str:
    return "\n".join(
        [
            "GENERIC SWITCH REFRESH ENGINE REVIEW",
            "====================================",
            "",
            "This worksheet contains generated review material.",
            "Review every section before using any configuration.",
            "",
            "1. ENGINE REVIEW SUMMARY",
            "------------------------",
            ENGINE_REVIEW_SUMMARY,
            "",
            "2. WARNINGS",
            "-----------",
            ENGINE_WARNINGS,
            "",
            "3. UNMAPPED INTERFACES",
            "----------------------",
            ENGINE_UNMAPPED_INTERFACES,
            "",
            "4. COLLISIONS",
            "-------------",
            ENGINE_COLLISIONS,
            "",
            "5. ACCESS PORT CONFIGURATION",
            "----------------------------",
            ENGINE_ACCESS_PORTS,
            "",
            "6. UPLINK CONFIGURATION",
            "-----------------------",
            ENGINE_UPLINKS,
            "",
            "7. PORT-CHANNEL CONFIGURATION",
            "-----------------------------",
            ENGINE_PORT_CHANNELS,
            "",
            "8. FINAL OPERATOR VALIDATION",
            "----------------------------",
            "[ ] Interface naming was confirmed on the destination platform.",
            "[ ] Uplink destinations were confirmed against physical cabling.",
            "[ ] All lines beginning with ! REVIEW, ! WARNING, or ! CRITICAL were reviewed.",
            "[ ] Generated text is approved for controlled execution.",
            "",
        ]
    )


def generate_engine_review_output(
    config_text: str,
    profile_dict: dict,
    template_text: str,
) -> tuple[str, object]:
    source_config = parse_source_config(config_text)
    schema = build_profile_schema(profile_dict)
    plan = build_target_refresh_plan(source_config, schema)
    return render_plan_template(template_text, plan), plan


def bundled_resource_path(filename: str) -> Path:
    if hasattr(sys, "_MEIPASS"):
        return (
            Path(sys._MEIPASS)
            / "switch_refresh_config_import_tool"
            / "assets"
            / filename
        )
    return Path(__file__).resolve().parent / "assets" / filename


def load_bundled_template_text() -> str:
    return read_text_file(bundled_resource_path(TEMPLATE_FILENAME))


def load_bundled_config_text() -> str:
    return read_text_file(bundled_resource_path(CONFIG_FILENAME))


class SwitchRefreshConfigImportApp(LabNotesExtractorApp):
    app_name = APP_NAME
    app_version = APP_VERSION
    template_button_text = "Save Refresh Template"
    credit_text = "Sanitized distribution"

    def __init__(self, root):
        self.engine_config_file_var = tk.StringVar()
        self.engine_profile_file_var = tk.StringVar()
        self.engine_template_file_var = tk.StringVar()
        self.engine_output_file_var = tk.StringVar()
        self.engine_profile_layout_var = tk.StringVar(value=ACCESS_LAYOUT_GIGABIT)
        self.engine_profile_custom_pattern_var = tk.StringVar(
            value="GigabitEthernet{member}/0/{port}"
        )
        self.engine_profile_stack_mapping_var = tk.StringVar(value="1=1")
        self.engine_profile_uplink_mode_var = tk.StringVar(value=UPLINK_MODE_CUSTOM)
        self.engine_profile_uplink_rows = tuple(
            (tk.StringVar(), tk.StringVar())
            for _row in range(STRUCTURED_UPLINK_ROW_COUNT)
        )
        self.engine_profile_uplink_mapping_text = None
        self.engine_profile_options_visible = tk.BooleanVar(value=False)
        self.engine_profile_summary_var = tk.StringVar(
            value="Using default target profile: 48-port GigabitEthernet, stack member 1 -> 1, custom uplinks optional."
        )
        self.engine_profile_toggle_button = None
        self.engine_profile_details_frame = None
        self.engine_audit_collision_var = tk.StringVar(value="0")
        self.engine_audit_unmapped_var = tk.StringVar(value="0")
        self.engine_audit_member_shift_var = tk.StringVar(value="0")
        self.engine_audit_flag_var = tk.StringVar(value="0")
        self.engine_audit_status_var = tk.StringVar(
            value="PENDING - GENERATE REVIEW OUTPUT"
        )
        self.engine_audit_status_label = None
        self.engine_preview_text = None
        super().__init__(root)
        self._bind_engine_profile_summary_updates()
        self.config_file_var.set(CONFIG_DISPLAY_NAME)
        self.template_file_var.set(TEMPLATE_DISPLAY_NAME)
        self.engine_config_file_var.set(CONFIG_DISPLAY_NAME)
        self.engine_profile_file_var.set(ENGINE_PROFILE_DISPLAY_NAME)
        self.engine_template_file_var.set(ENGINE_TEMPLATE_DISPLAY_NAME)
        self.status_var.set(
            "Ready. Both generic input files are selected; choose an output file."
        )

    def _bind_engine_profile_summary_updates(self):
        watched_vars = (
            self.engine_profile_layout_var,
            self.engine_profile_stack_mapping_var,
            self.engine_profile_uplink_mode_var,
        )
        for watched_var in watched_vars:
            watched_var.trace_add("write", self._update_engine_profile_summary)
        for source_var, target_var in self.engine_profile_uplink_rows:
            source_var.trace_add("write", self._update_engine_profile_summary)
            target_var.trace_add("write", self._update_engine_profile_summary)
        self._update_engine_profile_summary()

    def _update_engine_profile_summary(self, *_args):
        layout = self.engine_profile_layout_var.get() or ACCESS_LAYOUT_GIGABIT
        stack_mapping = self.engine_profile_stack_mapping_var.get().strip() or "1=1"
        uplink_mode = self.engine_profile_uplink_mode_var.get() or UPLINK_MODE_CUSTOM
        populated_uplinks = sum(
            1
            for source_var, target_var in self.engine_profile_uplink_rows
            if source_var.get().strip() or target_var.get().strip()
        )
        uplink_summary = (
            "site default uplink rule"
            if uplink_mode == UPLINK_MODE_SITE_DEFAULT
            else f"{populated_uplinks} custom uplink row(s)"
        )
        self.engine_profile_summary_var.set(
            f"Target profile: {layout}; stack {stack_mapping}; {uplink_summary}."
        )

    def browse_template_file(self):
        super().browse_template_file()

    def add_distribution_buttons(self, parent):
        self._button(
            parent,
            "Save Generic Config",
            self.save_config,
            "secondary-outline",
        ).grid(row=4, column=2, sticky="e", pady=(8, 2))

    def add_extra_tabs(self, notebook):
        engine_tab = ttk.Frame(notebook, padding=12)
        notebook.add(engine_tab, text="Target Build Planner")

        content = ttk.LabelFrame(
            engine_tab,
            text="Engine Inputs",
            padding=12,
            style="Tool.TLabelframe" if TTKBOOTSTRAP_AVAILABLE else "",
        )
        content.pack(fill="x")

        self.add_file_row(
            content,
            0,
            "Source running-config",
            self.engine_config_file_var,
            self.browse_engine_config_file,
        )
        self.add_file_row(
            content,
            1,
            "Target profile",
            self.engine_profile_file_var,
            self.browse_engine_profile_file,
        )
        self.add_file_row(
            content,
            2,
            "Review output template",
            self.engine_template_file_var,
            self.browse_engine_template_file,
        )
        self.add_file_row(
            content,
            3,
            "New switch build sheet",
            self.engine_output_file_var,
            self.browse_engine_output_file,
        )

        self._button(
            content,
            "Save Default Target Profile",
            self.save_generic_engine_profile,
            "primary-outline",
        ).grid(row=4, column=1, sticky="w", padx=8, pady=(8, 2))
        self._button(
            content,
            "Save Review Template",
            self.save_generic_engine_template,
            "secondary-outline",
        ).grid(row=4, column=2, sticky="e", pady=(8, 2))
        content.columnconfigure(1, weight=1)

        profile_builder = self._build_engine_profile_builder(engine_tab)
        profile_builder.pack(fill="x", pady=(12, 0))

        actions = ttk.Frame(engine_tab, padding=(0, 12, 0, 10))
        actions.pack(fill="x")
        self._button(
            actions,
            "Generate New Switch Build Sheet",
            self.run_engine_review_output,
            "success",
        ).pack(side="left", padx=(0, 6))
        self._button(
            actions,
            "Open New Switch Build Sheet",
            self.open_engine_output_file,
            "primary-outline",
        ).pack(side="left", padx=6)
        self._button(
            actions,
            "Open Build Sheet Folder",
            self.open_engine_output_folder,
            "primary-outline",
        ).pack(side="left", padx=6)
        self._button(
            actions,
            "Clear",
            self.clear_engine,
            "secondary-outline",
        ).pack(side="left", padx=6)

        audit_frame = self._build_engine_audit_panel(engine_tab)
        audit_frame.pack(fill="x", pady=(0, 12))

        preview_frame = ttk.LabelFrame(
            engine_tab,
            text="Review Findings / Output Preview",
            padding=12,
            style="Tool.TLabelframe" if TTKBOOTSTRAP_AVAILABLE else "",
        )
        preview_frame.pack(fill="both", expand=True)
        self.engine_preview_text = tk.Text(
            preview_frame,
            wrap="none",
            font=("Consolas", 10),
            relief="flat",
            borderwidth=1,
        )
        self.engine_preview_text.pack(fill="both", expand=True)
        self._set_engine_preview(
            "Generate review output to preview the new switch build sheet here.\n\n"
            "Planner note: public builds should use operator-supplied target profiles "
            "and explicit uplink mappings."
        )
        self._set_engine_audit_summary(None)

    def save_config(self):
        from tkinter import filedialog

        filename = filedialog.asksaveasfilename(
            title="Save Generic Existing Switch Config",
            initialfile="generic_existing_switch_config.txt",
            defaultextension=".txt",
            filetypes=[
                ("Text / Config Files", "*.txt *.cfg *.conf"),
                ("All Files", "*.*"),
            ],
        )
        if not filename:
            return

        try:
            write_text_file(filename, load_bundled_config_text())
            self.config_file_var.set(filename)
            self.status_var.set(f"Generic existing switch config saved: {filename}")
            messagebox.showinfo(
                "Generic Config Saved",
                f"Generic existing switch config saved to:\n{filename}",
            )
        except Exception as exc:
            messagebox.showerror("Generic Config Error", str(exc))

    def save_blank_template(self):
        from tkinter import filedialog

        filename = filedialog.asksaveasfilename(
            title="Save Generic Refresh Build Template",
            initialfile="generic_refresh_build_template.txt",
            defaultextension=".txt",
            filetypes=[
                ("Text Files", "*.txt"),
                ("Markdown Files", "*.md"),
                ("All Files", "*.*"),
            ],
        )
        if not filename:
            return

        try:
            write_text_file(filename, load_bundled_template_text())
            self.template_file_var.set(filename)
            self.status_var.set(f"Generic refresh build template saved: {filename}")
            messagebox.showinfo(
                "Template Saved",
                f"Generic refresh build template saved to:\n{filename}",
            )
        except Exception as exc:
            messagebox.showerror("Template Error", str(exc))

    def save_generic_engine_profile(self):
        from tkinter import filedialog

        filename = filedialog.asksaveasfilename(
            title="Save Default Target Profile",
            initialfile="default_target_profile.json",
            defaultextension=".json",
            filetypes=[
                ("JSON Files", "*.json"),
                ("All Files", "*.*"),
            ],
        )
        if not filename:
            return

        try:
            write_text_file(filename, load_generic_engine_profile_text())
            self.engine_profile_file_var.set(filename)
            self.status_var.set(f"Default target profile saved: {filename}")
            messagebox.showinfo(
                "Target Profile Saved",
                f"Default target profile saved to:\n{filename}",
            )
        except Exception as exc:
            messagebox.showerror("Target Profile Error", str(exc))

    def save_custom_engine_profile(self):
        from tkinter import filedialog

        filename = filedialog.asksaveasfilename(
            title="Save Custom Target Profile",
            initialfile="custom_target_profile.json",
            defaultextension=".json",
            filetypes=[
                ("JSON Files", "*.json"),
                ("All Files", "*.*"),
            ],
        )
        if not filename:
            return

        try:
            profile = build_custom_engine_profile_dict(
                self.engine_profile_layout_var.get(),
                self.engine_profile_custom_pattern_var.get(),
                self.engine_profile_stack_mapping_var.get(),
                self._get_engine_profile_uplink_mapping_text(),
                self.engine_profile_uplink_mode_var.get(),
            )
            build_profile_schema(profile)
            write_text_file(filename, json.dumps(profile, indent=2) + "\n")
            self.engine_profile_file_var.set(filename)
            self.status_var.set(f"Custom target profile saved: {filename}")
            messagebox.showinfo(
                "Target Profile Saved",
                f"Custom target profile saved to:\n{filename}",
            )
        except Exception as exc:
            messagebox.showerror("Target Profile Error", str(exc))

    def export_and_apply_custom_engine_profile(self):
        try:
            profile = build_custom_engine_profile_dict(
                self.engine_profile_layout_var.get(),
                self.engine_profile_custom_pattern_var.get(),
                self.engine_profile_stack_mapping_var.get(),
                self._get_engine_profile_uplink_mapping_text(),
                self.engine_profile_uplink_mode_var.get(),
            )
            build_profile_schema(profile)
            profile_file = self._write_temp_engine_profile(profile)
            self.engine_profile_file_var.set(str(profile_file))
            self._run_engine_review_output(allow_preview_without_output=True)
        except Exception as exc:
            messagebox.showerror("Target Profile Error", str(exc))
            self.status_var.set("Target profile apply failed. See error message.")

    def save_generic_engine_template(self):
        from tkinter import filedialog

        filename = filedialog.asksaveasfilename(
            title="Save Generic Review Output Template",
            initialfile="generic_engine_review_template.txt",
            defaultextension=".txt",
            filetypes=[
                ("Text Files", "*.txt"),
                ("Markdown Files", "*.md"),
                ("All Files", "*.*"),
            ],
        )
        if not filename:
            return

        try:
            write_text_file(filename, load_generic_engine_template_text())
            self.engine_template_file_var.set(filename)
            self.status_var.set(f"Generic review output template saved: {filename}")
            messagebox.showinfo(
                "Review Template Saved",
                f"Generic review output template saved to:\n{filename}",
            )
        except Exception as exc:
            messagebox.showerror("Review Template Error", str(exc))

    def clear(self):
        self.config_file_var.set(CONFIG_DISPLAY_NAME)
        self.template_file_var.set(TEMPLATE_DISPLAY_NAME)
        self.output_file_var.set("")
        self.access_port_type_var.set("G")
        self.status_var.set(
            "Ready. Both generic input files are selected; choose an output file."
        )

    def clear_engine(self):
        self.engine_config_file_var.set(CONFIG_DISPLAY_NAME)
        self.engine_profile_file_var.set(ENGINE_PROFILE_DISPLAY_NAME)
        self.engine_template_file_var.set(ENGINE_TEMPLATE_DISPLAY_NAME)
        self.engine_output_file_var.set("")
        self._set_engine_preview(
            "Generate review output to preview the profile-engine lab sheet here."
        )
        self._set_engine_audit_summary(None)
        self.status_var.set(
            "Ready. Generic engine inputs are selected; choose an output file."
        )

    def validate_inputs(self):
        config_file = self.config_file_var.get().strip()
        template_file = self.template_file_var.get().strip()
        output_file = self.output_file_var.get().strip()

        if not config_file:
            messagebox.showerror(
                "Missing File",
                "Please select a sanitized existing switch configuration file.",
            )
            return None
        if not output_file:
            messagebox.showerror(
                "Missing File",
                "Please choose the completed refresh build output file.",
            )
            return None
        if config_file != CONFIG_DISPLAY_NAME and not Path(config_file).exists():
            messagebox.showerror(
                "File Not Found",
                f"Existing switch configuration file not found:\n{config_file}",
            )
            return None
        if template_file != TEMPLATE_DISPLAY_NAME and not Path(template_file).exists():
            messagebox.showerror(
                "File Not Found",
                f"Template file not found:\n{template_file}",
            )
            return None

        return config_file, template_file, output_file

    def validate_engine_inputs(self):
        config_file = self.engine_config_file_var.get().strip()
        profile_file = self.engine_profile_file_var.get().strip()
        template_file = self.engine_template_file_var.get().strip()
        output_file = self.engine_output_file_var.get().strip()

        if not config_file:
            messagebox.showerror(
                "Missing File",
                "Please select a sanitized source running-config file.",
            )
            return None
        if not profile_file:
            messagebox.showerror(
                "Missing File",
                "Please select a target profile.",
            )
            return None
        if not template_file:
            messagebox.showerror(
                "Missing File",
                "Please select a review output template.",
            )
            return None
        if not output_file:
            messagebox.showerror(
                "Missing File",
                "Please choose the rendered review output file.",
            )
            return None
        if config_file != CONFIG_DISPLAY_NAME and not Path(config_file).exists():
            messagebox.showerror(
                "File Not Found",
                f"Source running-config file not found:\n{config_file}",
            )
            return None
        if (
            profile_file != ENGINE_PROFILE_DISPLAY_NAME
            and not Path(profile_file).exists()
        ):
            messagebox.showerror(
                "File Not Found",
                f"Target profile file not found:\n{profile_file}",
            )
            return None
        if (
            template_file != ENGINE_TEMPLATE_DISPLAY_NAME
            and not Path(template_file).exists()
        ):
            messagebox.showerror(
                "File Not Found",
                f"Review output template file not found:\n{template_file}",
            )
            return None

        return config_file, profile_file, template_file, output_file

    def validate_engine_inputs_for_preview(self):
        config_file = self.engine_config_file_var.get().strip()
        profile_file = self.engine_profile_file_var.get().strip()
        template_file = self.engine_template_file_var.get().strip()

        if not config_file:
            messagebox.showerror(
                "Missing File",
                "Please select a sanitized source running-config file.",
            )
            return None
        if not profile_file:
            messagebox.showerror(
                "Missing File",
                "Please select a target profile.",
            )
            return None
        if not template_file:
            messagebox.showerror(
                "Missing File",
                "Please select a review output template.",
            )
            return None
        if config_file != CONFIG_DISPLAY_NAME and not Path(config_file).exists():
            messagebox.showerror(
                "File Not Found",
                f"Source running-config file not found:\n{config_file}",
            )
            return None
        if (
            profile_file != ENGINE_PROFILE_DISPLAY_NAME
            and not Path(profile_file).exists()
        ):
            messagebox.showerror(
                "File Not Found",
                f"Target profile file not found:\n{profile_file}",
            )
            return None
        if (
            template_file != ENGINE_TEMPLATE_DISPLAY_NAME
            and not Path(template_file).exists()
        ):
            messagebox.showerror(
                "File Not Found",
                f"Review output template file not found:\n{template_file}",
            )
            return None

        return config_file, profile_file, template_file, ""

    def run_extraction(self):
        validated = self.validate_inputs()
        if not validated:
            return

        config_file, template_file, output_file = validated
        try:
            if config_file == CONFIG_DISPLAY_NAME:
                config_text = load_bundled_config_text()
            else:
                config_text = read_text_file(config_file)
            if template_file == TEMPLATE_DISPLAY_NAME:
                template_text = load_bundled_template_text()
            else:
                template_text = read_text_file(template_file)

            values = extract_config_values(
                config_text,
                access_port_prefix=self.access_port_type_var.get(),
            )
            completed_notes = apply_template(template_text, values)
            write_text_file(output_file, completed_notes)

            found_count = sum(
                1 for value in values.values() if value != "NOT FOUND"
            )
            self.status_var.set(
                f"Complete. Extracted {found_count} of {len(values)} fields. Saved: {output_file}"
            )
            messagebox.showinfo(
                "Extraction Complete",
                "Refresh build template imported successfully.\n\n"
                f"Fields extracted: {found_count} of {len(values)}\n\n"
                f"Saved to:\n{output_file}",
            )
        except Exception as exc:
            messagebox.showerror("Extraction Failed", str(exc))
            self.status_var.set("Extraction failed. See error message.")

    def run_engine_review_output(self):
        self._run_engine_review_output(allow_preview_without_output=False)

    def _run_engine_review_output(self, allow_preview_without_output):
        if allow_preview_without_output:
            validated = self.validate_engine_inputs_for_preview()
        else:
            validated = self.validate_engine_inputs()
        if not validated:
            return

        config_file, profile_file, template_file, output_file = validated

        try:
            config_text = (
                load_bundled_config_text()
                if config_file == CONFIG_DISPLAY_NAME
                else read_text_file(config_file)
            )
            profile_dict = (
                build_generic_engine_profile_dict()
                if profile_file == ENGINE_PROFILE_DISPLAY_NAME
                else load_profile_json_text(read_text_file(profile_file))
            )
            template_text = (
                load_generic_engine_template_text()
                if template_file == ENGINE_TEMPLATE_DISPLAY_NAME
                else read_text_file(template_file)
            )

            rendered_output, plan = generate_engine_review_output(
                config_text,
                profile_dict,
                template_text,
            )
            if output_file:
                write_text_file(output_file, rendered_output)
            self._set_engine_preview(rendered_output)
            self._set_engine_audit_summary(plan)
            audit = plan.audit_summary
            if output_file:
                self.status_var.set(
                    "Complete. Engine review output saved: "
                    f"{output_file} | collisions={audit.collisions_count} "
                    f"unmapped={audit.unmapped_count} "
                    f"member_shifts={audit.member_shifts_count} "
                    f"flags={audit.total_flags_count} warnings={len(plan.warnings)}"
                )
                messagebox.showinfo(
                    "Engine Review Complete",
                    "Profile engine review output generated successfully.\n\n"
                    f"Collisions: {audit.collisions_count}\n"
                    f"Unmapped interfaces: {audit.unmapped_count}\n"
                    f"Member shifts: {audit.member_shifts_count}\n"
                    f"Review flags: {audit.total_flags_count}\n"
                    f"Warnings: {len(plan.warnings)}\n"
                    f"Status: {self._engine_audit_status_text(audit)}\n\n"
                    f"Saved to:\n{output_file}",
                )
            else:
                self.status_var.set(
                    "Complete. Customized profile applied to preview: "
                    f"collisions={audit.collisions_count} "
                    f"unmapped={audit.unmapped_count} "
                    f"member_shifts={audit.member_shifts_count} "
                    f"flags={audit.total_flags_count} warnings={len(plan.warnings)}"
                )
        except Exception as exc:
            messagebox.showerror("Engine Review Failed", str(exc))
            self.status_var.set("Engine review failed. See error message.")

    def browse_engine_config_file(self):
        from tkinter import filedialog

        filename = filedialog.askopenfilename(
            title="Select Source Running-Config",
            filetypes=[
                ("Text / Config Files", "*.txt *.cfg *.conf"),
                ("All Files", "*.*"),
            ],
        )
        if filename:
            self.engine_config_file_var.set(filename)

    def browse_engine_profile_file(self):
        from tkinter import filedialog

        filename = filedialog.askopenfilename(
            title="Select Target Profile",
            filetypes=[
                ("Target Profile Files", "*.json"),
                ("All Files", "*.*"),
            ],
        )
        if filename:
            self.engine_profile_file_var.set(filename)

    def browse_engine_template_file(self):
        from tkinter import filedialog

        filename = filedialog.askopenfilename(
            title="Select Review Output Template",
            filetypes=[
                ("Text / Markdown Files", "*.txt *.md"),
                ("All Files", "*.*"),
            ],
        )
        if filename:
            self.engine_template_file_var.set(filename)

    def browse_engine_output_file(self):
        from tkinter import filedialog

        filename = filedialog.asksaveasfilename(
            title="Save Rendered Engine Review As",
            defaultextension=".txt",
            filetypes=[
                ("Text Files", "*.txt"),
                ("Markdown Files", "*.md"),
                ("All Files", "*.*"),
            ],
        )
        if filename:
            self.engine_output_file_var.set(filename)

    def open_engine_output_file(self):
        import os

        output_file = Path(self.engine_output_file_var.get().strip())
        if not output_file.is_file():
            messagebox.showwarning(
                "Output Not Found",
                "Generate engine review output or select an existing output file first.",
            )
            return
        os.startfile(output_file)

    def open_engine_output_folder(self):
        import os

        output_value = self.engine_output_file_var.get().strip()
        folder = Path(output_value).parent if output_value else Path.cwd()
        if not folder.exists():
            messagebox.showwarning(
                "Folder Not Found",
                f"Output folder not found:\n{folder}",
            )
            return
        os.startfile(folder)

    def _set_engine_preview(self, text):
        if self.engine_preview_text is None:
            return
        self.engine_preview_text.configure(state="normal")
        self.engine_preview_text.delete("1.0", "end")
        self.engine_preview_text.insert("1.0", text)
        self.engine_preview_text.configure(state="disabled")

    def _build_engine_audit_panel(self, parent):
        frame = ttk.LabelFrame(
            parent,
            text="Staging Bench Audit Status",
            padding=12,
            style="Tool.TLabelframe" if TTKBOOTSTRAP_AVAILABLE else "",
        )
        for column in range(4):
            frame.columnconfigure(column, weight=1, uniform="engine_audit")

        fields = (
            ("COLLISIONS", self.engine_audit_collision_var),
            ("UNMAPPED", self.engine_audit_unmapped_var),
            ("MEMBER SHIFTS", self.engine_audit_member_shift_var),
            ("FLAGS", self.engine_audit_flag_var),
        )
        for column, (label_text, value_var) in enumerate(fields):
            cell = ttk.Frame(frame, padding=(10, 8))
            cell.grid(row=0, column=column, sticky="nsew", padx=4, pady=(0, 8))
            ttk.Label(cell, text=label_text, anchor="center").pack(fill="x")
            ttk.Label(
                cell,
                textvariable=value_var,
                anchor="center",
                font=("Segoe UI", 16, "bold"),
            ).pack(fill="x", pady=(4, 0))

        self.engine_audit_status_label = tk.Label(
            frame,
            textvariable=self.engine_audit_status_var,
            anchor="center",
            font=("Segoe UI", 10, "bold"),
            padx=12,
            pady=8,
        )
        self.engine_audit_status_label.grid(
            row=1,
            column=0,
            columnspan=4,
            sticky="ew",
            padx=4,
            pady=(2, 0),
        )
        return frame

    def _build_engine_profile_builder(self, parent):
        frame = ttk.LabelFrame(
            parent,
            text="Target Profile Options",
            padding=12,
            style="Tool.TLabelframe" if TTKBOOTSTRAP_AVAILABLE else "",
        )
        frame.columnconfigure(0, weight=1)

        header = ttk.Frame(frame)
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)
        ttk.Label(
            header,
            textvariable=self.engine_profile_summary_var,
            wraplength=900,
            justify="left",
        ).grid(row=0, column=0, sticky="ew", padx=(0, 12))
        self.engine_profile_toggle_button = self._button(
            header,
            "Show Options",
            self.toggle_engine_profile_options,
            "secondary-outline",
        )
        self.engine_profile_toggle_button.grid(row=0, column=1, sticky="e")

        details = ttk.Frame(frame, padding=(0, 12, 0, 0))
        details.columnconfigure(1, weight=1)
        details.columnconfigure(3, weight=1)
        self.engine_profile_details_frame = details

        ttk.Label(details, text="Target access ports").grid(
            row=0,
            column=0,
            sticky="w",
            padx=(0, 8),
            pady=4,
        )
        layout_combo = ttk.Combobox(
            details,
            textvariable=self.engine_profile_layout_var,
            values=ACCESS_LAYOUT_OPTIONS,
            state="readonly",
        )
        layout_combo.grid(row=0, column=1, sticky="ew", padx=(0, 12), pady=4)

        ttk.Label(details, text="Custom naming pattern").grid(
            row=0,
            column=2,
            sticky="w",
            padx=(0, 8),
            pady=4,
        )
        ttk.Entry(
            details,
            textvariable=self.engine_profile_custom_pattern_var,
        ).grid(row=0, column=3, sticky="ew", pady=4)

        ttk.Label(details, text="Stack members").grid(
            row=1,
            column=0,
            sticky="w",
            padx=(0, 8),
            pady=4,
        )
        ttk.Entry(
            details,
            textvariable=self.engine_profile_stack_mapping_var,
        ).grid(row=1, column=1, sticky="ew", padx=(0, 12), pady=4)

        ttk.Label(details, text="Uplink rule").grid(
            row=1,
            column=2,
            sticky="w",
            padx=(0, 8),
            pady=4,
        )
        ttk.Combobox(
            details,
            textvariable=self.engine_profile_uplink_mode_var,
            values=UPLINK_MODE_OPTIONS,
            state="readonly",
        ).grid(row=1, column=3, sticky="ew", pady=4)

        ttk.Label(details, text="Uplink ports").grid(
            row=2,
            column=0,
            sticky="nw",
            padx=(0, 8),
            pady=(8, 4),
        )
        rows_frame = ttk.Frame(details)
        rows_frame.grid(
            row=2,
            column=1,
            columnspan=3,
            sticky="ew",
            pady=(8, 4),
        )
        rows_frame.columnconfigure(1, weight=1)
        rows_frame.columnconfigure(3, weight=1)
        ttk.Label(rows_frame, text="Source").grid(
            row=0,
            column=1,
            sticky="w",
            padx=(0, 8),
        )
        ttk.Label(rows_frame, text="Target").grid(
            row=0,
            column=3,
            sticky="w",
        )
        for row_index, (source_var, target_var) in enumerate(
            self.engine_profile_uplink_rows,
            start=1,
        ):
            ttk.Label(rows_frame, text=str(row_index)).grid(
                row=row_index,
                column=0,
                sticky="e",
                padx=(0, 6),
                pady=2,
            )
            ttk.Entry(rows_frame, textvariable=source_var).grid(
                row=row_index,
                column=1,
                sticky="ew",
                padx=(0, 8),
                pady=2,
            )
            ttk.Label(rows_frame, text="->").grid(
                row=row_index,
                column=2,
                sticky="ew",
                padx=(0, 8),
                pady=2,
            )
            ttk.Entry(rows_frame, textvariable=target_var).grid(
                row=row_index,
                column=3,
                sticky="ew",
                pady=2,
            )

        ttk.Label(details, text="Advanced extra uplinks").grid(
            row=3,
            column=0,
            sticky="nw",
            padx=(0, 8),
            pady=(8, 4),
        )
        uplink_frame = ttk.Frame(details)
        uplink_frame.grid(
            row=3,
            column=1,
            columnspan=3,
            sticky="ew",
            pady=(8, 4),
        )
        uplink_frame.columnconfigure(0, weight=1)
        self.engine_profile_uplink_mapping_text = tk.Text(
            uplink_frame,
            height=3,
            wrap="none",
            font=("Consolas", 9),
            relief="flat",
            borderwidth=1,
        )
        self.engine_profile_uplink_mapping_text.grid(row=0, column=0, sticky="ew")

        self._button(
            details,
            "Save Target Profile",
            self.save_custom_engine_profile,
            "primary-outline",
        ).grid(row=4, column=2, sticky="e", padx=(0, 8), pady=(8, 0))
        self._button(
            details,
            "Apply Target Profile",
            self.export_and_apply_custom_engine_profile,
            "success",
        ).grid(row=4, column=3, sticky="e", pady=(8, 0))
        self._refresh_engine_profile_options_visibility()
        return frame

    def toggle_engine_profile_options(self):
        self.engine_profile_options_visible.set(
            not self.engine_profile_options_visible.get()
        )
        self._refresh_engine_profile_options_visibility()

    def _refresh_engine_profile_options_visibility(self):
        if self.engine_profile_details_frame is None:
            return
        if self.engine_profile_options_visible.get():
            self.engine_profile_details_frame.grid(row=1, column=0, sticky="ew")
            if self.engine_profile_toggle_button is not None:
                self.engine_profile_toggle_button.configure(text="Hide Options")
        else:
            self.engine_profile_details_frame.grid_remove()
            if self.engine_profile_toggle_button is not None:
                self.engine_profile_toggle_button.configure(text="Show Options")

    def _get_engine_profile_uplink_mapping_text(self):
        structured_text = build_structured_uplink_mapping_text(
            tuple(
                (source_var.get(), target_var.get())
                for source_var, target_var in self.engine_profile_uplink_rows
            ),
            self.engine_profile_uplink_mode_var.get(),
        )
        if self.engine_profile_uplink_mapping_text is None:
            manual_text = ""
        else:
            manual_text = self.engine_profile_uplink_mapping_text.get("1.0", "end")

        parts = [part.strip() for part in (structured_text, manual_text) if part.strip()]
        return "\n".join(parts)

    def _write_temp_engine_profile(self, profile):
        temp_dir = Path(tempfile.gettempdir()) / "switch_refresh_config_import_tool"
        temp_dir.mkdir(parents=True, exist_ok=True)
        profile_file = temp_dir / "applied_engine_profile.json"
        write_text_file(profile_file, json.dumps(profile, indent=2) + "\n")
        return profile_file

    def _set_engine_audit_summary(self, plan):
        if plan is None:
            self.engine_audit_collision_var.set("0")
            self.engine_audit_unmapped_var.set("0")
            self.engine_audit_member_shift_var.set("0")
            self.engine_audit_flag_var.set("0")
            self.engine_audit_status_var.set("PENDING - GENERATE REVIEW OUTPUT")
            self._apply_engine_audit_status_color("PENDING")
            return

        audit = plan.audit_summary
        self.engine_audit_collision_var.set(str(audit.collisions_count))
        self.engine_audit_unmapped_var.set(str(audit.unmapped_count))
        self.engine_audit_member_shift_var.set(str(audit.member_shifts_count))
        self.engine_audit_flag_var.set(str(audit.total_flags_count))
        self.engine_audit_status_var.set(self._engine_audit_status_text(audit))
        self._apply_engine_audit_status_color(self._engine_audit_status_severity(audit))

    def _engine_audit_status_text(self, audit):
        if audit.collisions_count > 0:
            return "CRITICAL: Target port collisions detected."
        if not audit.is_completely_clean:
            return "WARNING: Review required before staging deployment."
        return "CLEAN: Engine rules passed. Human validation required."

    def _engine_audit_status_severity(self, audit):
        if audit.collisions_count > 0:
            return "CRITICAL"
        if not audit.is_completely_clean:
            return "WARNING"
        return "CLEAR"

    def _apply_engine_audit_status_color(self, severity):
        if self.engine_audit_status_label is None:
            return

        palette = {
            "CRITICAL": ("#ffffff", "#b00020"),
            "WARNING": ("#1f1f1f", "#f2b705"),
            "CLEAR": ("#ffffff", "#147a3d"),
            "PENDING": ("#1f1f1f", "#d9dee3"),
        }
        foreground, background = palette.get(severity, palette["PENDING"])
        self.engine_audit_status_label.configure(fg=foreground, bg=background)


def main():
    root = tb.Window(themename="flatly") if TTKBOOTSTRAP_AVAILABLE else tk.Tk()
    SwitchRefreshConfigImportApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
