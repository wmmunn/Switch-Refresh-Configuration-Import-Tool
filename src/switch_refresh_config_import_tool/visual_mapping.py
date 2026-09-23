"""Pure helpers for the interactive source-to-target port map.

The window draws these cells and pairs. This module does not own mapping
rules; it classifies source ports with the engine, records operator pairs,
and writes those pairs back into the existing target profile fields.
"""

from __future__ import annotations

from dataclasses import dataclass

from .engine_models import ProfileSchema, SourceSwitchConfig
from .mapping_engine import classify_interface_role, parse_source_member_port


ROLE_ACCESS = "access"
ROLE_UPLINK = "uplink"
ROLE_PORT_CHANNEL_MEMBER = "port_channel_member"
ROLE_EMPTY = "empty"
ROLE_IGNORED = "ignored"
ROLE_UNPLACEABLE = "unplaceable"

TARGET_CAGE_ACCESS = "access"
TARGET_CAGE_UPLINK = "uplink"

ACCESS_LAYOUT_GIGABIT = "48-port GigabitEthernet access"
ACCESS_LAYOUT_TENGIGABIT = "48-port TenGigabitEthernet access"
ACCESS_LAYOUT_FIVEGIGABIT = "48-port FiveGigabitEthernet access"
ACCESS_LAYOUT_MIXED_GIGABIT_FIVEGIGABIT = "Mixed Gi 1-24, Five 25-48"
ACCESS_LAYOUT_CUSTOM_PATTERN = "Custom target pattern"

ACCESS_LAYOUT_TARGET_PATTERNS = {
    ACCESS_LAYOUT_GIGABIT: "GigabitEthernet{member}/0/{port}",
    ACCESS_LAYOUT_TENGIGABIT: "TenGigabitEthernet{member}/0/{port}",
    ACCESS_LAYOUT_FIVEGIGABIT: "FiveGigabitEthernet{member}/0/{port}",
}

DEFAULT_ACCESS_PORT_COUNT = 48
DEFAULT_UPLINK_SLOT_COUNT = 8
DEFAULT_UPLINK_SLOT_PATTERN = "TenGigabitEthernet{member}/1/{port}"


@dataclass(frozen=True)
class SourcePortCell:
    name: str
    role: str
    member: int | None
    port: int | None
    description: str | None
    channel_group: str | None
    access_vlan: str | None
    is_trunk: bool
    placeable: bool


@dataclass(frozen=True)
class TargetPortCell:
    name: str
    role: str
    member: int
    port: int
    cage: str


@dataclass(frozen=True)
class TargetChassisSpec:
    access_layout: str
    custom_target_pattern: str = ""
    target_members: tuple[int, ...] = (1,)
    access_port_count: int = DEFAULT_ACCESS_PORT_COUNT
    uplink_slot_count: int = DEFAULT_UPLINK_SLOT_COUNT
    uplink_pattern: str = DEFAULT_UPLINK_SLOT_PATTERN


@dataclass(frozen=True)
class PortMappingPair:
    source_interface: str
    target_interface: str


@dataclass(frozen=True)
class VisualMappingStatus:
    mapped_count: int
    unmapped_uplink_sources: tuple[str, ...]
    unmapped_port_channel_members: tuple[str, ...]
    collision_targets: tuple[str, ...]
    port_channel_on_uplink_slots: tuple[tuple[str, str], ...]
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class VisualProfileFragments:
    explicit_mappings: dict[str, str]
    uplink_mappings: dict[str, str]
    known_source_ports: tuple[str, ...]


def classify_source_ports(
    source_config: SourceSwitchConfig,
    schema: ProfileSchema,
) -> tuple[SourcePortCell, ...]:
    """Build source cells for every parsed interface using engine roles."""
    cells: list[SourcePortCell] = []

    for source_interface in source_config.interfaces:
        role = classify_interface_role(source_interface, schema)
        parsed = parse_source_member_port(source_interface.name)
        member = int(parsed["member"]) if parsed is not None else None
        port = int(parsed["port"]) if parsed is not None else None
        placeable = role not in {ROLE_IGNORED}

        cells.append(
            SourcePortCell(
                name=source_interface.name,
                role=role,
                member=member,
                port=port,
                description=source_interface.description,
                channel_group=source_interface.channel_group,
                access_vlan=source_interface.access_vlan,
                is_trunk=source_interface.is_trunk,
                placeable=placeable,
            )
        )

    return tuple(cells)


def build_target_access_name(
    access_layout: str,
    custom_target_pattern: str,
    member: int,
    port: int,
) -> str:
    """Name one target access port from the same layouts the profile builder uses."""
    if access_layout in ACCESS_LAYOUT_TARGET_PATTERNS:
        return ACCESS_LAYOUT_TARGET_PATTERNS[access_layout].format(
            member=member,
            port=port,
        )

    if access_layout == ACCESS_LAYOUT_MIXED_GIGABIT_FIVEGIGABIT:
        if port <= 24:
            return f"GigabitEthernet{member}/0/{port}"
        return f"FiveGigabitEthernet{member}/0/{port}"

    if access_layout == ACCESS_LAYOUT_CUSTOM_PATTERN:
        pattern = custom_target_pattern.strip()
        if not pattern:
            raise ValueError("Custom target pattern is required.")
        if "{member}" not in pattern or "{port}" not in pattern:
            raise ValueError(
                "Custom target pattern must include {member} and {port}."
            )
        return pattern.format(member=member, port=port)

    raise ValueError(f"Unsupported access layout: {access_layout}")


def build_target_chassis(spec: TargetChassisSpec) -> tuple[TargetPortCell, ...]:
    """Build the operator-owned target faceplate: access ports plus uplink slots."""
    if not spec.target_members:
        raise ValueError("At least one target stack member is required.")

    cells: list[TargetPortCell] = []
    for member in spec.target_members:
        for port in range(1, spec.access_port_count + 1):
            cells.append(
                TargetPortCell(
                    name=build_target_access_name(
                        spec.access_layout,
                        spec.custom_target_pattern,
                        member,
                        port,
                    ),
                    role=ROLE_ACCESS,
                    member=member,
                    port=port,
                    cage=TARGET_CAGE_ACCESS,
                )
            )
        for slot in range(1, spec.uplink_slot_count + 1):
            cells.append(
                TargetPortCell(
                    name=spec.uplink_pattern.format(member=member, port=slot),
                    role=ROLE_UPLINK,
                    member=member,
                    port=slot,
                    cage=TARGET_CAGE_UPLINK,
                )
            )

    return tuple(cells)


def chassis_target_members(member_mapping: dict[int, int]) -> tuple[int, ...]:
    """Return distinct target member IDs in stable numeric order."""
    if not member_mapping:
        return (1,)
    return tuple(sorted(set(member_mapping.values())))


def pairs_from_profile(profile: dict) -> tuple[PortMappingPair, ...]:
    """Seed the canvas from profile uplink and explicit mappings."""
    interface_translation = profile.get("interface_translation", {})
    explicit = interface_translation.get("explicit_mappings", {})
    uplinks = (
        profile.get("uplinks", {})
        .get("destination", {})
        .get("mappings", {})
    )

    merged: dict[str, str] = {}
    if isinstance(explicit, dict):
        merged.update(
            {str(source): str(target) for source, target in explicit.items()}
        )
    if isinstance(uplinks, dict):
        merged.update(
            {str(source): str(target) for source, target in uplinks.items()}
        )

    return tuple(
        PortMappingPair(source_interface=source, target_interface=target)
        for source, target in merged.items()
        if source and target
    )


def set_mapping(
    pairs: tuple[PortMappingPair, ...],
    source_interface: str,
    target_interface: str,
) -> tuple[PortMappingPair, ...]:
    """Replace any existing pair for this source with the new target."""
    kept = tuple(
        pair for pair in pairs if pair.source_interface != source_interface
    )
    return kept + (
        PortMappingPair(
            source_interface=source_interface,
            target_interface=target_interface,
        ),
    )


def clear_mapping(
    pairs: tuple[PortMappingPair, ...],
    source_interface: str,
) -> tuple[PortMappingPair, ...]:
    """Remove the pair for one source interface."""
    return tuple(
        pair for pair in pairs if pair.source_interface != source_interface
    )


def occupancy(
    pairs: tuple[PortMappingPair, ...],
) -> dict[str, tuple[str, ...]]:
    """Group source interfaces by the target they claim."""
    claimed: dict[str, list[str]] = {}
    for pair in pairs:
        claimed.setdefault(pair.target_interface, []).append(pair.source_interface)
    return {
        target: tuple(sources)
        for target, sources in claimed.items()
    }


def source_cells_by_name(
    source_cells: tuple[SourcePortCell, ...],
) -> dict[str, SourcePortCell]:
    return {cell.name: cell for cell in source_cells}


def target_cells_by_name(
    target_cells: tuple[TargetPortCell, ...],
) -> dict[str, TargetPortCell]:
    return {cell.name: cell for cell in target_cells}


def build_visual_mapping_status(
    source_cells: tuple[SourcePortCell, ...],
    target_cells: tuple[TargetPortCell, ...],
    pairs: tuple[PortMappingPair, ...],
) -> VisualMappingStatus:
    """Summarize unmapped uplinks, PC-on-uplink landings, and collisions."""
    mapped_sources = {pair.source_interface for pair in pairs}
    target_lookup = target_cells_by_name(target_cells)
    claimed = occupancy(pairs)

    unmapped_uplinks = tuple(
        cell.name
        for cell in source_cells
        if cell.role == ROLE_UPLINK and cell.name not in mapped_sources
    )
    unmapped_members = tuple(
        cell.name
        for cell in source_cells
        if cell.role == ROLE_PORT_CHANNEL_MEMBER and cell.name not in mapped_sources
    )
    collision_targets = tuple(
        sorted(
            target
            for target, sources in claimed.items()
            if len(sources) > 1
        )
    )

    port_channel_on_uplink: list[tuple[str, str]] = []
    source_lookup = source_cells_by_name(source_cells)
    for pair in pairs:
        source_cell = source_lookup.get(pair.source_interface)
        target_cell = target_lookup.get(pair.target_interface)
        if source_cell is None or target_cell is None:
            continue
        if (
            source_cell.role == ROLE_PORT_CHANNEL_MEMBER
            and target_cell.cage == TARGET_CAGE_UPLINK
        ):
            port_channel_on_uplink.append(
                (pair.source_interface, pair.target_interface)
            )

    warnings: list[str] = []
    if unmapped_uplinks:
        warnings.append(
            "Unmapped uplink source(s): "
            + ", ".join(unmapped_uplinks)
            + ". A blank second uplink is usually a missing explicit destination."
        )
    if unmapped_members:
        warnings.append(
            "Unmapped port-channel member(s): "
            + ", ".join(unmapped_members)
            + ". The engine will otherwise translate these with access-port rules."
        )
    if collision_targets:
        warnings.append(
            "Target collision(s): "
            + ", ".join(collision_targets)
            + ". Two source ports claim the same destination."
        )
    if port_channel_on_uplink:
        rendered = ", ".join(
            f"{source} -> {target}" for source, target in port_channel_on_uplink
        )
        warnings.append(
            "Port-channel member(s) land on uplink slot(s): "
            + rendered
            + ". Confirm the bundle should occupy a new-switch uplink cage port."
        )

    return VisualMappingStatus(
        mapped_count=len(pairs),
        unmapped_uplink_sources=unmapped_uplinks,
        unmapped_port_channel_members=unmapped_members,
        collision_targets=collision_targets,
        port_channel_on_uplink_slots=tuple(port_channel_on_uplink),
        warnings=tuple(warnings),
    )


def build_profile_fragments(
    pairs: tuple[PortMappingPair, ...],
    source_cells: tuple[SourcePortCell, ...],
    target_cells: tuple[TargetPortCell, ...],
) -> VisualProfileFragments:
    """Turn canvas pairs into the profile fields the engine already consumes."""
    source_lookup = source_cells_by_name(source_cells)
    target_lookup = target_cells_by_name(target_cells)
    explicit_mappings: dict[str, str] = {}
    uplink_mappings: dict[str, str] = {}
    known_source_ports: list[str] = []

    for pair in pairs:
        explicit_mappings[pair.source_interface] = pair.target_interface
        source_cell = source_lookup.get(pair.source_interface)
        target_cell = target_lookup.get(pair.target_interface)
        source_role = source_cell.role if source_cell is not None else ROLE_UNPLACEABLE
        target_is_uplink_slot = (
            target_cell is not None and target_cell.cage == TARGET_CAGE_UPLINK
        )

        if source_role == ROLE_UPLINK or (
            source_role == ROLE_PORT_CHANNEL_MEMBER and target_is_uplink_slot
        ):
            uplink_mappings[pair.source_interface] = pair.target_interface
            known_source_ports.append(pair.source_interface)

    return VisualProfileFragments(
        explicit_mappings=explicit_mappings,
        uplink_mappings=uplink_mappings,
        known_source_ports=tuple(dict.fromkeys(known_source_ports)),
    )


def merge_visual_mappings_into_profile(
    profile: dict,
    fragments: VisualProfileFragments,
) -> dict:
    """Replace explicit and uplink mappings with the operator-drawn pairs."""
    merged = {
        **profile,
        "interface_translation": {
            **profile.get("interface_translation", {}),
            "explicit_mappings": dict(fragments.explicit_mappings),
        },
        "uplinks": {
            **profile.get("uplinks", {}),
            "detection": {
                **profile.get("uplinks", {}).get("detection", {}),
                "known_source_ports": list(fragments.known_source_ports),
            },
            "destination": {
                **profile.get("uplinks", {}).get("destination", {}),
                "mode": "explicit",
                "mappings": dict(fragments.uplink_mappings),
            },
        },
    }
    return merged


def source_cell_label(cell: SourcePortCell) -> str:
    """Short faceplate label for a source port."""
    if cell.port is not None:
        return str(cell.port)
    return cell.name


def source_cell_detail(cell: SourcePortCell) -> str:
    """Status-line description for the selected source port."""
    parts = [cell.name, cell.role.replace("_", " ")]
    if cell.description:
        parts.append(cell.description)
    if cell.channel_group:
        parts.append(f"Po{cell.channel_group}")
    if cell.access_vlan:
        parts.append(f"VLAN {cell.access_vlan}")
    if cell.is_trunk:
        parts.append("trunk")
    return " | ".join(parts)


def target_cell_detail(cell: TargetPortCell) -> str:
    """Status-line description for a target port."""
    cage_label = "uplink slot" if cell.cage == TARGET_CAGE_UPLINK else "access port"
    return f"{cell.name} | {cage_label} | member {cell.member}"
