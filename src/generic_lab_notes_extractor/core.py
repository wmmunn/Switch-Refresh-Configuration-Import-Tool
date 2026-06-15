import os
import re
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from pathlib import Path

try:
    import ttkbootstrap as tb

    TTKBOOTSTRAP_AVAILABLE = True
except Exception:
    tb = None
    TTKBOOTSTRAP_AVAILABLE = False


APP_NAME = "Generic Lab Notes Extractor"
APP_VERSION = "1.0.0"


PLACEHOLDERS = [
    "{{HOSTNAME}}",
    "{{VTP_DOMAIN}}",
    "{{MGMT_VLAN}}",
    "{{MGMT_IP}}",
    "{{MGMT_MASK}}",
    "{{DEFAULT_GATEWAY}}",
    "{{VLAN_LIST}}",
    "{{TRUNK_ALLOWED_VLANS}}",
    "{{UPLINK_TRUNK_1}}",
    "{{UPLINK_TRUNK_2}}",
    "{{UPLINK_TRUNK_3}}",
    "{{UPLINK_TRUNK_4}}",
    "{{ACCESS_PORT_CONFIGS}}",
    "{{RADIUS_STATUS}}",
]


# 2960XR-specific or legacy interface lines to remove from extracted access-port configs.
REMOVE_COMPLETELY = [
    "srr-queue bandwidth share",
    "priority-queue out",
]

# Lines to keep out of the pasted build section, but still show as review comments.
UNSUPPORTED_OR_REVIEW = [
    "mls qos",
    "auto qos",
    "macro auto",
]


# If no RADIUS configuration is detected in the existing running-config,
# these legacy 802.1X / authentication lines are stripped from transferred
# interface configurations.
DOT1X_REMOVE_IF_NO_RADIUS = [
    "authentication host-mode multi-domain",
    "authentication open",
    "authentication port-control auto",
    "authentication periodic",
    "authentication timer reauthenticate server",
    "authentication violation replace",
    "no snmp trap link-status",
    "dot1x pae authenticator",
    "dot1x timeout tx-period 5",
    "dot1x timeout supp-timeout 5",
]

# Conservative indicators that RADIUS / dot1x infrastructure is actually configured.
# If any of these are present, dot1x interface commands are preserved.
RADIUS_INDICATORS = [
    "radius server",
    "radius-server host",
    "aaa group server radius",
    "aaa authentication dot1x",
    "aaa authorization network",
    "dot1x system-auth-control",
]


def detect_radius_config(config_text):
    """
    Return True if the old running-config appears to contain active
    RADIUS / dot1x infrastructure configuration.

    This is intentionally conservative: if RADIUS-related infrastructure
    exists, dot1x interface commands are preserved.
    """
    normalized_lines = [line.strip().lower() for line in config_text.splitlines()]

    for line in normalized_lines:
        for indicator in RADIUS_INDICATORS:
            if line.startswith(indicator.lower()):
                return True

    return False


def clean_interface_line_for_lab_notes(line, radius_present=True):
    """
    Clean older 2960XR-specific interface lines during access-port extraction.

    Returns:
    - None to remove the line completely
    - A review-comment line for lines that should not be blindly pasted
    - The original/modified line for lines that should remain
    """
    stripped = line.strip()

    if not radius_present and stripped in DOT1X_REMOVE_IF_NO_RADIUS:
        return None

    if any(stripped.startswith(cmd) for cmd in REMOVE_COMPLETELY):
        return None

    if "spanning-tree portfast edge" in stripped:
        line = line.replace("spanning-tree portfast edge", "spanning-tree portfast")

    if any(stripped.startswith(cmd) for cmd in UNSUPPORTED_OR_REVIEW):
        return f" ! REVIEW REMOVED: {stripped}"

    return line


def read_text_file(path):
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        return f.read()


def write_text_file(path, text):
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(text)


def extract_interface_blocks(config_text):
    pattern = r"^interface\s+(.+?)\n(.*?)(?=^!|\Z)"
    return re.findall(pattern, config_text, flags=re.M | re.S)


def extract_hostname(config_text):
    match = re.search(r"^hostname\s+(.+)$", config_text, flags=re.M)
    return match.group(1).strip() if match else "NOT FOUND"


def extract_vtp_domain(config_text):
    match = re.search(r"^vtp\s+domain\s+(.+)$", config_text, flags=re.M)
    return match.group(1).strip() if match else "NOT FOUND"


def extract_default_gateway(config_text):
    match = re.search(r"^ip\s+default-gateway\s+(.+)$", config_text, flags=re.M)
    return match.group(1).strip() if match else "NOT FOUND"


def extract_management_vlan_ip(config_text):
    for interface_name, body in extract_interface_blocks(config_text):
        interface_name = interface_name.strip()

        if not interface_name.lower().startswith("vlan"):
            continue

        ip_match = re.search(
            r"^\s*ip\s+address\s+(\S+)\s+(\S+)",
            body,
            flags=re.M
        )

        if ip_match:
            vlan_id = interface_name.replace("Vlan", "").replace("vlan", "").strip()
            return vlan_id, ip_match.group(1), ip_match.group(2)

    return "NOT FOUND", "NOT FOUND", "NOT FOUND"


def extract_vlans(config_text):
    """
    Extract VLAN database entries and output Cisco IOS-ready commands.

    Example output:
    vlan 10
     name DATA
    vlan 20
     name VOICE
    """
    vlan_blocks = []
    lines = config_text.splitlines()
    i = 0

    while i < len(lines):
        line = lines[i].strip()
        vlan_match = re.match(r"^vlan\s+(.+)$", line, flags=re.I)

        if vlan_match:
            vlan_id = vlan_match.group(1).strip()
            vlan_name = ""

            j = i + 1
            while j < len(lines):
                next_line = lines[j].strip()

                if next_line == "!":
                    break

                if re.match(r"^(vlan|interface|hostname|ip\s|router\s|line\s|end)\b", next_line, flags=re.I):
                    break

                name_match = re.match(r"^name\s+(.+)$", next_line, flags=re.I)
                if name_match:
                    vlan_name = name_match.group(1).strip()

                j += 1

            block_lines = [f"vlan {vlan_id}"]

            if vlan_name:
                block_lines.append(f" name {vlan_name}")

            vlan_blocks.append("\n".join(block_lines))

            i = j
            continue

        i += 1

    return "\n".join(vlan_blocks) if vlan_blocks else "NOT FOUND"

def normalize_vlan_items(vlan_string):
    """
    Split a Cisco VLAN list into ordered items.

    Supports comma-separated VLANs and ranges. This intentionally preserves
    ranges as strings instead of expanding them.

    Example:
    4,41,42,75,145,400,500,520
    """
    vlan_string = vlan_string.strip()

    if vlan_string.lower().startswith("add "):
        vlan_string = vlan_string[4:].strip()

    return [item.strip() for item in vlan_string.split(",") if item.strip()]


def split_vlan_list_for_trunk_commands(vlan_items, chunk_size=8):
    """
    Convert VLAN items into Cisco-ready trunk commands.

    Example:
    ["4","41","42","75","145","400","500","520","521","530"]

    Becomes:
    switchport trunk allowed vlan 4,41,42,75,145,400,500,520
    switchport trunk allowed vlan add 521,530
    """
    if isinstance(vlan_items, str):
        vlans = normalize_vlan_items(vlan_items)
    else:
        vlans = [str(v).strip() for v in vlan_items if str(v).strip()]

    if not vlans:
        return []

    commands = []

    first_chunk = vlans[:chunk_size]
    commands.append(
        "switchport trunk allowed vlan " + ",".join(first_chunk)
    )

    remaining = vlans[chunk_size:]

    while remaining:
        chunk = remaining[:chunk_size]
        commands.append(
            "switchport trunk allowed vlan add " + ",".join(chunk)
        )
        remaining = remaining[chunk_size:]

    return commands


def extract_trunk_vlan_items_from_body(body):
    """
    Extract and combine trunk allowed VLAN lines from one interface block.

    Handles both:
      switchport trunk allowed vlan 4,41,42
      switchport trunk allowed vlan add 75,145

    The returned list is de-duplicated while preserving order.
    """
    vlan_items = []
    seen = set()

    for line in body.splitlines():
        stripped = line.strip()

        match = re.match(
            r"^switchport\s+trunk\s+allowed\s+vlan\s+(.+)$",
            stripped,
            flags=re.I
        )

        if not match:
            continue

        value = match.group(1).strip()

        # Ignore non-list forms for now rather than inventing behavior.
        if value.lower() in {"all", "none"}:
            continue

        for item in normalize_vlan_items(value):
            key = item.lower()
            if key not in seen:
                vlan_items.append(item)
                seen.add(key)

    return vlan_items


def extract_trunk_allowed_vlans(config_text):
    """
    General trunk output. This includes the old interface name so you can see
    where each trunk VLAN list came from.
    """
    results = []

    for interface_name, body in extract_interface_blocks(config_text):
        interface_name = interface_name.strip()
        vlan_items = extract_trunk_vlan_items_from_body(body)

        if not vlan_items:
            continue

        commands = split_vlan_list_for_trunk_commands(vlan_items, chunk_size=8)

        if commands:
            interface_output = (
                f"{interface_name}\n"
                + "\n".join(commands)
            )
            results.append(interface_output)

    return "\n\n".join(results) if results else "NOT FOUND"


def extract_interface_description(body):
    match = re.search(
        r"^\s*description\s+(.+)$",
        body,
        flags=re.M
    )

    if match:
        return "description " + match.group(1).strip()

    return ""


# Uplink placeholders use source-config order.
# The old switch interface type does not determine the new 9300 uplink interface.
# The lab sheet controls destination interfaces such as Te1/1/1 and TeX/1/8.


def uplink_candidate_score(interface_name, body, vlan_items, original_order):
    """
    Score trunk candidates for UPLINK_TRUNK placeholders.

    The goal is to avoid accidentally using ordinary trunk ports as uplinks.

    Priority:
    0 = description strongly suggests uplink/router/gateway/core/distribution
    1 = has any description
    2 = no description

    Within the same priority, keep source config order.
    """
    description = extract_interface_description(body).lower()

    uplink_keywords = [
        "uplink",
        "up-link",
        "gateway",
        "gw",
        "router",
        "core",
        "distribution",
        "dist",
        "vpc",
        "wan",
        "lan-uplink",
    ]

    if description and any(keyword in description for keyword in uplink_keywords):
        return (0, original_order)

    if description:
        return (1, original_order)

    return (2, original_order)


def extract_uplink_trunks(config_text, max_uplinks=4):
    """
    Dedicated uplink output for lab-note placeholders.

    The old switch interface type does NOT determine the new 9300 uplink
    interface. The lab sheet controls destination interfaces.

    This function now ranks trunk candidates so obvious uplink/router/gateway
    descriptions are preferred over ordinary trunk ports.
    """
    candidates = []

    for original_order, (interface_name, body) in enumerate(extract_interface_blocks(config_text)):
        interface_name = interface_name.strip()
        vlan_items = extract_trunk_vlan_items_from_body(body)

        if not vlan_items:
            continue

        description = extract_interface_description(body)
        score = uplink_candidate_score(interface_name, body, vlan_items, original_order)

        candidates.append({
            "interface_name": interface_name,
            "body": body,
            "vlan_items": vlan_items,
            "description": description,
            "score": score,
            "order": original_order,
        })

    candidates.sort(key=lambda item: item["score"])

    uplinks = []

    for candidate in candidates[:max_uplinks]:
        output_lines = []

        if candidate["description"]:
            output_lines.append(candidate["description"])

        commands = split_vlan_list_for_trunk_commands(candidate["vlan_items"], chunk_size=8)
        output_lines.extend(commands)

        if output_lines:
            uplinks.append("\n".join(output_lines))

    return uplinks



def is_physical_access_candidate(interface_name, body):
    """
    Return True for physical Ethernet-style interfaces that are not trunk uplinks.
    This intentionally keeps shutdown / unused ports if they are present in the config.
    """
    interface_name = interface_name.strip()

    excluded_prefixes = (
        "vlan",
        "loopback",
        "port-channel",
        "po",
        "tunnel",
        "null",
    )

    if interface_name.lower().startswith(excluded_prefixes):
        return False

    physical_patterns = (
        r"^GigabitEthernet",
        r"^FastEthernet",
        r"^Gi",
        r"^Fa",
    )

    if not any(re.match(pattern, interface_name, flags=re.I) for pattern in physical_patterns):
        return False

    if re.search(r"^\s*switchport\s+mode\s+trunk\b", body, flags=re.M | re.I):
        return False

    if re.search(r"^\s*switchport\s+trunk\s+allowed\s+vlan\b", body, flags=re.M | re.I):
        return False

    return True


def convert_access_interface_name(interface_name, new_prefix):
    """
    Convert old access interface names to abbreviated lab-build format.

    Examples:
    GigabitEthernet0/5   -> G1/0/5
    FastEthernet0/5      -> Fi1/0/5
    GigabitEthernet1/0/5 -> G1/0/5
    GigabitEthernet2/0/5 -> G2/0/5
    """
    interface_name = interface_name.strip()

    stacked = re.search(
        r"(?:GigabitEthernet|FastEthernet|Gi|Fa)(\d+)/(\d+)/(\d+)$",
        interface_name,
        flags=re.I
    )

    if stacked:
        switch_num = stacked.group(1)
        module_num = stacked.group(2)
        port_num = stacked.group(3)
        return f"{new_prefix}{switch_num}/{module_num}/{port_num}"

    standalone = re.search(
        r"(?:GigabitEthernet|FastEthernet|Gi|Fa)(\d+)/(\d+)$",
        interface_name,
        flags=re.I
    )

    if standalone:
        port_num = standalone.group(2)
        return f"{new_prefix}1/0/{port_num}"

    return interface_name


def extract_access_port_configs(config_text, new_prefix="G", radius_present=True):
    """
    Extract non-trunk physical access-port interface blocks.

    The interface line is rewritten to abbreviated format:
    interface G1/0/5
    or
    interface Fi1/0/5

    The rest of each interface block is preserved as-is.
    """
    results = []

    for interface_name, body in extract_interface_blocks(config_text):
        interface_name = interface_name.strip()

        if not is_physical_access_candidate(interface_name, body):
            continue

        new_interface = convert_access_interface_name(interface_name, new_prefix)
        output_lines = [f"interface {new_interface}"]

        for line in body.splitlines():
            if line.strip() == "":
                continue

            cleaned_line = clean_interface_line_for_lab_notes(line, radius_present=radius_present)

            if cleaned_line is None:
                continue

            output_lines.append(cleaned_line.rstrip())

        output_lines.append("!")
        results.append("\n".join(output_lines))

    return "\n".join(results) if results else "NOT FOUND"

def extract_config_values(config_text, access_port_prefix="G"):
    mgmt_vlan, mgmt_ip, mgmt_mask = extract_management_vlan_ip(config_text)
    radius_present = detect_radius_config(config_text)
    uplinks = extract_uplink_trunks(config_text, max_uplinks=4)
    access_port_configs = extract_access_port_configs(
        config_text,
        new_prefix=access_port_prefix,
        radius_present=radius_present
    )

    values = {
        "{{HOSTNAME}}": extract_hostname(config_text),
        "{{VTP_DOMAIN}}": extract_vtp_domain(config_text),
        "{{MGMT_VLAN}}": mgmt_vlan,
        "{{MGMT_IP}}": mgmt_ip,
        "{{MGMT_MASK}}": mgmt_mask,
        "{{DEFAULT_GATEWAY}}": extract_default_gateway(config_text),
        "{{VLAN_LIST}}": extract_vlans(config_text),
        "{{TRUNK_ALLOWED_VLANS}}": extract_trunk_allowed_vlans(config_text),
        "{{ACCESS_PORT_CONFIGS}}": access_port_configs,
        "{{RADIUS_STATUS}}": "RADIUS detected: YES - dot1x interface commands preserved" if radius_present else "RADIUS detected: NO - dot1x interface commands stripped",
    }

    for index in range(4):
        placeholder = "{{UPLINK_TRUNK_" + str(index + 1) + "}}"
        values[placeholder] = uplinks[index] if index < len(uplinks) else "NOT FOUND"

    return values


def apply_template(template_text, values):
    output = template_text

    for placeholder, value in values.items():
        output = output.replace(placeholder, value)

    return output


def create_default_template():
    return """Lab Build Notes
===============

Switch Hostname:
{{HOSTNAME}}

VTP Domain:
{{VTP_DOMAIN}}

Management VLAN:
{{MGMT_VLAN}}

Management IP Address:
{{MGMT_IP}}

Management Subnet Mask:
{{MGMT_MASK}}

Default Gateway:
{{DEFAULT_GATEWAY}}

VLAN Creation Commands:
{{VLAN_LIST}}

Trunk Allowed VLANs:
{{TRUNK_ALLOWED_VLANS}}

Uplink Trunk 1:
{{UPLINK_TRUNK_1}}

Uplink Trunk 2:
{{UPLINK_TRUNK_2}}

Uplink Trunk 3:
{{UPLINK_TRUNK_3}}

Uplink Trunk 4:
{{UPLINK_TRUNK_4}}

RADIUS / Dot1x Status:
{{RADIUS_STATUS}}

Access Port Interface Configurations:
{{ACCESS_PORT_CONFIGS}}
"""


class LabNotesExtractorApp:
    app_name = APP_NAME
    app_version = APP_VERSION
    template_button_text = "Create Blank Template"
    credit_text = "Open-source sanitized distribution"

    def __init__(self, root):
        self.root = root
        self.root.title(f"{self.app_name} v{self.app_version}")
        self.root.geometry("1040x720")
        self.root.minsize(860, 620)

        self.config_file_var = tk.StringVar()
        self.template_file_var = tk.StringVar()
        self.output_file_var = tk.StringVar()
        self.access_port_type_var = tk.StringVar(value="G")
        self.status_var = tk.StringVar(value="Ready. Select a running-config, template, and output file.")

        self.build_gui()

    def _button(self, parent, text, command, bootstyle=""):
        if TTKBOOTSTRAP_AVAILABLE:
            return tb.Button(
                parent,
                text=text,
                command=command,
                bootstyle=bootstyle or "secondary",
            )
        return ttk.Button(parent, text=text, command=command)

    def build_gui(self):
        if TTKBOOTSTRAP_AVAILABLE:
            self.root.style.configure(
                "Tool.TLabelframe.Label",
                font=("Segoe UI", 10, "bold"),
            )

        top = ttk.Frame(self.root, padding=14)
        top.pack(fill="x")

        header = ttk.Frame(top)
        header.grid(row=0, column=0, sticky="we", pady=(0, 12))
        ttk.Label(
            header,
            text=self.app_name,
            font=("Segoe UI", 17, "bold"),
        ).pack(side="left")
        ttk.Label(
            header,
            text=f"v{self.app_version}",
            font=("Segoe UI", 10),
            foreground="#5c6b73",
        ).pack(side="left", padx=(8, 0), pady=(6, 0))
        ttk.Label(
            header,
            text="Local file processing only; review generated configuration before use.",
            foreground="#5c6b73",
        ).pack(side="right", pady=(6, 0))
        top.columnconfigure(0, weight=1)

        notebook = ttk.Notebook(self.root)
        notebook.pack(fill="both", expand=True, padx=14, pady=(0, 10))

        workflow_tab = ttk.Frame(notebook, padding=12)
        reference_tab = ttk.Frame(notebook, padding=12)
        notebook.add(workflow_tab, text="Extraction Workflow")
        notebook.add(reference_tab, text="Template Reference")

        content = ttk.LabelFrame(
            workflow_tab,
            text="Files and Target Platform",
            padding=12,
            style="Tool.TLabelframe" if TTKBOOTSTRAP_AVAILABLE else "",
        )
        content.pack(fill="x")

        self.add_file_row(
            content,
            0,
            "Old switch running-config",
            self.config_file_var,
            self.browse_config_file
        )

        self.add_file_row(
            content,
            1,
            "Lab notes template",
            self.template_file_var,
            self.browse_template_file
        )

        self.add_file_row(
            content,
            2,
            "Completed lab notes output",
            self.output_file_var,
            self.browse_output_file
        )

        access_label = ttk.Label(
            content,
            text="New access port prefix",
            anchor="w",
        )
        access_label.grid(row=3, column=0, sticky="w", pady=6)

        access_dropdown = ttk.Combobox(
            content,
            textvariable=self.access_port_type_var,
            values=["G", "Fi"],
            state="readonly",
            width=10
        )
        access_dropdown.grid(row=3, column=1, sticky="w", padx=8, pady=6)

        ttk.Label(
            content,
            text="G produces G1/0/5; Fi produces Fi1/0/5.",
            foreground="#5c6b73",
        ).grid(row=3, column=1, columnspan=2, sticky="w", padx=(105, 8), pady=6)

        template_button = self._button(
            content,
            self.template_button_text,
            self.save_blank_template,
            "primary-outline",
        )
        template_button.grid(row=4, column=1, sticky="w", padx=8, pady=(8, 2))
        self.add_distribution_buttons(content)

        content.columnconfigure(1, weight=1)

        actions = ttk.Frame(workflow_tab, padding=(0, 12, 0, 10))
        actions.pack(fill="x")
        self.run_button = self._button(
            actions,
            "Run Extraction",
            self.run_extraction,
            "success",
        )
        self.run_button.pack(side="left", padx=(0, 6))
        self._button(
            actions,
            "Open Output",
            self.open_output_file,
            "primary-outline",
        ).pack(side="left", padx=6)
        self._button(
            actions,
            "Open Output Folder",
            self.open_output_folder,
            "primary-outline",
        ).pack(side="left", padx=6)
        self._button(
            actions,
            "Clear",
            self.clear,
            "secondary-outline",
        ).pack(side="left", padx=6)
        self._button(
            actions,
            "Exit",
            self.root.destroy,
            "secondary-outline",
        ).pack(side="right")

        ttk.Label(
            workflow_tab,
            textvariable=self.status_var,
            font=("Segoe UI", 11, "bold"),
        ).pack(fill="x", pady=(0, 10))

        review_frame = ttk.LabelFrame(
            workflow_tab,
            text="Operator Review",
            padding=12,
            style="Tool.TLabelframe" if TTKBOOTSTRAP_AVAILABLE else "",
        )
        review_frame.pack(fill="both", expand=True)
        review_text = tk.Text(
            review_frame,
            height=12,
            wrap="word",
            font=("Segoe UI", 10),
            relief="flat",
            borderwidth=1,
        )
        review_text.pack(fill="both", expand=True)
        review_text.insert(
            "1.0",
            "The generated file is review material, not an approved device configuration.\n\n"
            "Extraction behavior:\n"
            "- Reads local running-config and template files only.\n"
            "- Extracts management, VLAN, trunk, uplink, and access-port details.\n"
            "- Converts selected legacy interface syntax for the target platform.\n"
            "- Preserves RADIUS/dot1x interface commands only when supporting "
            "RADIUS configuration is detected.\n"
            "- Marks unsupported or review-sensitive legacy commands in the output.\n\n"
            "Before use, confirm uplink selection, VLAN scope, management addressing, "
            "authentication requirements, and all lines marked REVIEW REMOVED.",
        )
        review_text.configure(state="disabled")

        reference_tab.columnconfigure(0, weight=1)
        reference_tab.columnconfigure(1, weight=1)
        reference_tab.rowconfigure(0, weight=1)

        placeholder_frame = ttk.LabelFrame(
            reference_tab,
            text="Supported Placeholders",
            padding=10,
        )
        placeholder_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        placeholder_text = tk.Text(
            placeholder_frame,
            wrap="none",
            font=("Consolas", 10),
            relief="flat",
            borderwidth=1,
        )
        placeholder_text.pack(fill="both", expand=True)
        placeholder_text.insert("1.0", "\n".join(PLACEHOLDERS))
        placeholder_text.configure(state="disabled")

        extracted_frame = ttk.LabelFrame(
            reference_tab,
            text="Extracted Content",
            padding=10,
        )
        extracted_frame.grid(row=0, column=1, sticky="nsew", padx=(6, 0))
        extracted_text = tk.Text(
            extracted_frame,
            wrap="word",
            font=("Segoe UI", 10),
            relief="flat",
            borderwidth=1,
        )
        extracted_text.pack(fill="both", expand=True)
        extracted_text.insert(
            "1.0",
            "- Switch hostname\n"
            "- VTP domain\n"
            "- Management VLAN, IP address, and subnet mask\n"
            "- Default gateway\n"
            "- VLAN creation and name commands\n"
            "- Trunk allowed VLAN statements by interface\n"
            "- Up to four likely uplink blocks\n"
            "- Access-port interface configurations\n"
            "- RADIUS/dot1x detection status\n\n"
            "Uplink candidates with descriptions containing uplink, router, gateway, "
            "core, or distribution terms are preferred. Source order breaks ties.",
        )
        extracted_text.configure(state="disabled")

        ttk.Label(
            self.root,
            text=self.credit_text,
            foreground="#5c6b73",
            font=("Segoe UI", 8, "italic"),
            padding=(14, 0, 14, 8),
        ).pack(fill="x")

    def add_file_row(self, parent, row, label_text, variable, command):
        label = ttk.Label(parent, text=label_text, anchor="w")
        label.grid(row=row, column=0, sticky="w", pady=6)

        entry = ttk.Entry(parent, textvariable=variable, width=70)
        entry.grid(row=row, column=1, sticky="ew", padx=8, pady=6)

        button = self._button(parent, "Browse", command, "primary-outline")
        button.grid(row=row, column=2, pady=6)

    def add_distribution_buttons(self, parent):
        """Allow packaged editions to add fixture-export actions."""

    def browse_config_file(self):
        filename = filedialog.askopenfilename(
            title="Select Old Switch Running-Config",
            filetypes=[
                ("Text / Config Files", "*.txt *.cfg *.conf"),
                ("All Files", "*.*")
            ]
        )
        if filename:
            self.config_file_var.set(filename)

    def browse_template_file(self):
        filename = filedialog.askopenfilename(
            title="Select Lab Notes Template",
            filetypes=[
                ("Text / Markdown Files", "*.txt *.md"),
                ("All Files", "*.*")
            ]
        )
        if filename:
            self.template_file_var.set(filename)

    def browse_output_file(self):
        filename = filedialog.asksaveasfilename(
            title="Save Completed Lab Notes As",
            defaultextension=".txt",
            filetypes=[
                ("Text Files", "*.txt"),
                ("Markdown Files", "*.md"),
                ("All Files", "*.*")
            ]
        )
        if filename:
            self.output_file_var.set(filename)

    def save_blank_template(self):
        filename = filedialog.asksaveasfilename(
            title="Save Blank Lab Notes Template",
            defaultextension=".txt",
            filetypes=[
                ("Text Files", "*.txt"),
                ("Markdown Files", "*.md"),
                ("All Files", "*.*")
            ]
        )

        if not filename:
            return

        try:
            write_text_file(filename, create_default_template())
            self.template_file_var.set(filename)
            self.status_var.set(f"Blank template created: {filename}")
            messagebox.showinfo("Template Created", f"Blank template saved to:\n{filename}")
        except Exception as e:
            messagebox.showerror("Template Error", str(e))

    def clear(self):
        self.config_file_var.set("")
        self.template_file_var.set("")
        self.output_file_var.set("")
        self.access_port_type_var.set("G")
        self.status_var.set("Ready. Select a running-config, template, and output file.")

    def open_output_file(self):
        output_file = Path(self.output_file_var.get().strip())
        if not output_file.is_file():
            messagebox.showwarning(
                "Output Not Found",
                "Run extraction or select an existing output file first.",
            )
            return
        os.startfile(output_file)

    def open_output_folder(self):
        output_value = self.output_file_var.get().strip()
        folder = Path(output_value).parent if output_value else Path.cwd()
        if not folder.exists():
            messagebox.showwarning(
                "Folder Not Found",
                f"Output folder not found:\n{folder}",
            )
            return
        os.startfile(folder)

    def validate_inputs(self):
        config_file = self.config_file_var.get().strip()
        template_file = self.template_file_var.get().strip()
        output_file = self.output_file_var.get().strip()

        if not config_file:
            messagebox.showerror("Missing File", "Please select the old switch running-config file.")
            return None

        if not template_file:
            messagebox.showerror("Missing File", "Please select the lab notes template file.")
            return None

        if not output_file:
            messagebox.showerror("Missing File", "Please choose the completed lab notes output file.")
            return None

        if not Path(config_file).exists():
            messagebox.showerror("File Not Found", f"Running-config file not found:\n{config_file}")
            return None

        if not Path(template_file).exists():
            messagebox.showerror("File Not Found", f"Template file not found:\n{template_file}")
            return None

        return config_file, template_file, output_file

    def run_extraction(self):
        validated = self.validate_inputs()

        if not validated:
            return

        config_file, template_file, output_file = validated

        try:
            config_text = read_text_file(config_file)
            template_text = read_text_file(template_file)

            values = extract_config_values(config_text, access_port_prefix=self.access_port_type_var.get())
            completed_notes = apply_template(template_text, values)

            write_text_file(output_file, completed_notes)

            found_count = sum(1 for value in values.values() if value != "NOT FOUND")
            self.status_var.set(f"Complete. Extracted {found_count} of {len(values)} fields. Saved: {output_file}")

            messagebox.showinfo(
                "Extraction Complete",
                f"Lab notes created successfully.\n\n"
                f"Fields extracted: {found_count} of {len(values)}\n\n"
                f"Saved to:\n{output_file}"
            )

        except Exception as e:
            messagebox.showerror("Extraction Failed", str(e))
            self.status_var.set("Extraction failed. See error message.")


if __name__ == "__main__":
    root = tb.Window(themename="flatly") if TTKBOOTSTRAP_AVAILABLE else tk.Tk()
    app = LabNotesExtractorApp(root)
    root.mainloop()
