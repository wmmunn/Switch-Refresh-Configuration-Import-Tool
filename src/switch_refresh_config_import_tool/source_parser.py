"""Explicit Cisco IOS source-config parser for future engine work."""

from __future__ import annotations

from .engine_models import (
    FlaggedSourceBlock,
    SourceInterface,
    SourceManagement,
    SourceSwitchConfig,
    SourceVlan,
)


RADIUS_INDICATORS = (
    "radius server",
    "radius-server host",
    "aaa group server radius",
    "aaa authentication dot1x",
    "aaa authorization network",
    "dot1x system-auth-control",
)


def parse_source_config(config_text: str) -> SourceSwitchConfig:
    """Parse targeted source data into dataclasses without target assumptions."""
    lines = config_text.splitlines()
    hostname = _find_single_value(lines, "hostname ")
    vtp_domain = _find_single_value(lines, "vtp domain ")
    default_gateway = _find_single_value(lines, "ip default-gateway ")
    interfaces, flagged_blocks = _parse_interfaces(lines)
    vlans = _parse_vlans(lines)
    management = _find_management(interfaces, default_gateway)
    radius_detected = _detect_radius(lines)

    return SourceSwitchConfig(
        hostname=hostname,
        vtp_domain=vtp_domain,
        management=management,
        vlans=tuple(vlans),
        interfaces=tuple(interfaces),
        flagged_blocks=tuple(flagged_blocks),
        radius_detected=radius_detected,
    )


def _find_single_value(lines: list[str], prefix: str) -> str | None:
    for line in lines:
        stripped = line.strip()
        if stripped.lower().startswith(prefix.lower()):
            return stripped[len(prefix):].strip()
    return None


def _parse_interfaces(lines: list[str]) -> tuple[list[SourceInterface], list[FlaggedSourceBlock]]:
    interfaces: list[SourceInterface] = []
    flagged_blocks: list[FlaggedSourceBlock] = []
    current_name: str | None = None
    current_body: list[str] = []
    flagged_first_line: str | None = None
    flagged_body: list[str] = []

    for line in lines:
        stripped = line.strip()

        if flagged_first_line is not None:
            if stripped == "!":
                flagged_blocks.append(
                    FlaggedSourceBlock(
                        first_line=flagged_first_line,
                        reason="unparseable_interface_declaration",
                        body_lines=tuple(flagged_body),
                    )
                )
                flagged_first_line = None
                flagged_body = []
            else:
                flagged_body.append(line)
            continue

        if stripped == "interface" or stripped.startswith("interface "):
            if current_name is not None:
                interfaces.append(_build_interface(current_name, current_body))

            if stripped == "interface":
                interface_name = ""
            else:
                interface_name = stripped[len("interface "):].strip()

            if not interface_name:
                current_name = None
                current_body = []
                flagged_first_line = line
                flagged_body = []
            else:
                current_name = interface_name
                current_body = []
            continue

        if stripped == "!":
            if current_name is not None:
                interfaces.append(_build_interface(current_name, current_body))
                current_name = None
                current_body = []
            continue

        if current_name is not None:
            current_body.append(line)

    if current_name is not None:
        interfaces.append(_build_interface(current_name, current_body))

    if flagged_first_line is not None:
        flagged_blocks.append(
            FlaggedSourceBlock(
                first_line=flagged_first_line,
                reason="unparseable_interface_declaration",
                body_lines=tuple(flagged_body),
            )
        )

    return interfaces, flagged_blocks


def _build_interface(name: str, body_lines: list[str]) -> SourceInterface:
    description: str | None = None
    access_vlan: str | None = None
    voice_vlan: str | None = None
    trunk_allowed_vlans: str | None = None
    trunk_allowed_vlan_lines: list[str] = []
    malformed_trunk_allowed_vlan_lines: list[str] = []
    channel_group: str | None = None
    channel_group_mode: str | None = None
    shutdown = False
    is_trunk = False
    is_access = False

    for line in body_lines:
        stripped = line.strip()
        lower = stripped.lower()

        if lower.startswith("description "):
            description = stripped[len("description "):].strip()
        elif lower.startswith("switchport access vlan "):
            access_vlan = stripped[len("switchport access vlan "):].strip()
        elif lower.startswith("switchport voice vlan "):
            voice_vlan = stripped[len("switchport voice vlan "):].strip()
        elif lower.startswith("switchport trunk allowed vlan "):
            trunk_allowed_vlans = stripped[len("switchport trunk allowed vlan "):].strip()
            trunk_allowed_vlan_lines.append(stripped)
        elif lower.startswith("switchport trunk allowed "):
            malformed_trunk_allowed_vlan_lines.append(stripped)
        elif lower == "switchport mode trunk":
            is_trunk = True
        elif lower == "switchport mode access":
            is_access = True
        elif lower == "shutdown":
            shutdown = True
        elif lower.startswith("channel-group "):
            parts = stripped.split()
            if len(parts) >= 2:
                channel_group = parts[1]
            if len(parts) >= 4 and parts[2].lower() == "mode":
                channel_group_mode = parts[3]

    return SourceInterface(
        name=name,
        body_lines=tuple(body_lines),
        description=description,
        access_vlan=access_vlan,
        voice_vlan=voice_vlan,
        trunk_allowed_vlans=trunk_allowed_vlans,
        trunk_allowed_vlan_lines=tuple(trunk_allowed_vlan_lines),
        malformed_trunk_allowed_vlan_lines=tuple(malformed_trunk_allowed_vlan_lines),
        channel_group=channel_group,
        channel_group_mode=channel_group_mode,
        shutdown=shutdown,
        is_trunk=is_trunk,
        is_access=is_access,
    )


def _parse_vlans(lines: list[str]) -> list[SourceVlan]:
    vlans: list[SourceVlan] = []
    current_vlan_id: str | None = None
    current_vlan_name: str | None = None

    for line in lines:
        stripped = line.strip()
        lower = stripped.lower()

        if lower.startswith("vlan "):
            if current_vlan_id is not None:
                vlans.append(SourceVlan(current_vlan_id, current_vlan_name))

            current_vlan_id = stripped[len("vlan "):].strip()
            current_vlan_name = None
            continue

        if current_vlan_id is not None and lower.startswith("name "):
            current_vlan_name = stripped[len("name "):].strip()
            continue

        if current_vlan_id is not None and (stripped == "!" or lower.startswith("interface ")):
            vlans.append(SourceVlan(current_vlan_id, current_vlan_name))
            current_vlan_id = None
            current_vlan_name = None

    if current_vlan_id is not None:
        vlans.append(SourceVlan(current_vlan_id, current_vlan_name))

    return vlans


def _find_management(
    interfaces: list[SourceInterface],
    default_gateway: str | None,
) -> SourceManagement:
    for interface in interfaces:
        if not interface.name.lower().startswith("vlan"):
            continue

        for line in interface.body_lines:
            stripped = line.strip()
            if stripped.lower().startswith("ip address "):
                parts = stripped.split()
                if len(parts) >= 4:
                    return SourceManagement(
                        vlan_id=interface.name[4:],
                        ip_address=parts[2],
                        subnet_mask=parts[3],
                        default_gateway=default_gateway,
                    )

    return SourceManagement(default_gateway=default_gateway)


def _detect_radius(lines: list[str]) -> bool:
    for line in lines:
        lowered = line.strip().lower()
        for indicator in RADIUS_INDICATORS:
            if lowered.startswith(indicator):
                return True
    return False
