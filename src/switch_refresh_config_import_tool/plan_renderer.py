"""Render target refresh plans into reviewable lab-sheet sections."""

from __future__ import annotations

from .engine_models import (
    InterfaceMappingDecision,
    MappingEvidence,
    TargetAccessPort,
    TargetPortChannel,
    TargetRefreshPlan,
    TargetUplink,
)


ENGINE_REVIEW_SUMMARY = "{{ENGINE_REVIEW_SUMMARY}}"
ENGINE_ACCESS_PORTS = "{{ENGINE_ACCESS_PORTS}}"
ENGINE_UPLINKS = "{{ENGINE_UPLINKS}}"
ENGINE_PORT_CHANNELS = "{{ENGINE_PORT_CHANNELS}}"
ENGINE_WARNINGS = "{{ENGINE_WARNINGS}}"
ENGINE_COLLISIONS = "{{ENGINE_COLLISIONS}}"
ENGINE_UNMAPPED_INTERFACES = "{{ENGINE_UNMAPPED_INTERFACES}}"

ENGINE_PLACEHOLDERS = (
    ENGINE_REVIEW_SUMMARY,
    ENGINE_ACCESS_PORTS,
    ENGINE_UPLINKS,
    ENGINE_PORT_CHANNELS,
    ENGINE_WARNINGS,
    ENGINE_COLLISIONS,
    ENGINE_UNMAPPED_INTERFACES,
)


def render_plan_placeholders(plan: TargetRefreshPlan) -> dict[str, str]:
    """Return template placeholder values for a target refresh plan."""
    return {
        ENGINE_REVIEW_SUMMARY: render_review_summary(plan),
        ENGINE_ACCESS_PORTS: render_access_ports(plan),
        ENGINE_UPLINKS: render_uplinks(plan),
        ENGINE_PORT_CHANNELS: render_port_channels(plan),
        ENGINE_WARNINGS: render_warnings(plan),
        ENGINE_COLLISIONS: render_collisions(plan),
        ENGINE_UNMAPPED_INTERFACES: render_unmapped_interfaces(plan),
    }


def render_plan_template(template_text: str, plan: TargetRefreshPlan) -> str:
    """Apply rendered engine sections to a lab-sheet template."""
    output = template_text

    for placeholder, value in render_plan_placeholders(plan).items():
        output = output.replace(placeholder, value)

    return output


def render_review_summary(plan: TargetRefreshPlan) -> str:
    """Render a compact review summary as Cisco-safe comment lines."""
    collision_count = len(_colliding_evidence(plan))
    unmapped_count = len(_unmapped_labels(plan))
    warning_count = len(plan.warnings)

    lines = [
        _comment("REVIEW", "Generated output is review material, not approved configuration."),
        _comment("REVIEW", f"Source hostname: {plan.hostname or 'UNKNOWN'}."),
        _comment("REVIEW", f"Source VTP domain: {plan.vtp_domain or 'UNKNOWN'}."),
        _comment("REVIEW", f"Access ports staged: {len(plan.access_ports)}."),
        _comment("REVIEW", f"Uplinks staged: {len(plan.uplinks)}."),
        _comment("REVIEW", f"Port-channels staged: {len(plan.port_channels)}."),
        _comment("REVIEW", f"Warnings: {warning_count}."),
        _comment("REVIEW", f"Unmapped interfaces: {unmapped_count}."),
        _comment("REVIEW", f"Collision evidence items: {collision_count}."),
    ]

    if plan.review_flags:
        lines.append(_comment("REVIEW", f"Review flags: {', '.join(plan.review_flags)}."))
    else:
        lines.append(_comment("REVIEW", "Review flags: none."))

    return "\n".join(lines)


def render_access_ports(plan: TargetRefreshPlan) -> str:
    """Render mapped and unmapped access ports."""
    if not plan.access_ports:
        return _comment("INFO", "No access ports were staged by the engine.")

    rendered_blocks = []

    for access_port in plan.access_ports:
        if access_port.target_interface is None:
            rendered_blocks.append(_render_unmapped_access_port(access_port))
            continue

        lines = [f"interface {access_port.target_interface}"]
        if access_port.description:
            lines.append(f" description {access_port.description}")
        if access_port.access_vlan:
            lines.append(f" switchport access vlan {access_port.access_vlan}")
        if access_port.voice_vlan:
            lines.append(f" switchport voice vlan {access_port.voice_vlan}")
        if access_port.shutdown:
            lines.append(" shutdown")

        lines.extend(_render_evidence_comments(access_port.mapping_evidence, access_port.review_flags))
        lines.append("!")
        rendered_blocks.append("\n".join(lines))

    return "\n".join(rendered_blocks)


def render_uplinks(plan: TargetRefreshPlan) -> str:
    """Render uplink sections with review-visible evidence."""
    if not plan.uplinks:
        return _comment("INFO", "No uplinks were staged by the engine.")

    rendered_blocks = []

    for uplink in plan.uplinks:
        if uplink.target_interface is None:
            rendered_blocks.append(_render_unmapped_uplink(uplink))
            continue

        lines = [f"interface {uplink.target_interface}"]
        if uplink.description:
            lines.append(f" description {uplink.description}")
        lines.extend(f" {line}" for line in uplink.trunk_allowed_vlan_lines)
        for malformed_line in uplink.malformed_trunk_allowed_vlan_lines:
            lines.append(_comment("REVIEW", f"Malformed trunk allowed VLAN source line: {malformed_line}"))

        lines.extend(_render_evidence_comments(uplink.mapping_evidence, uplink.review_flags))
        lines.append("!")
        rendered_blocks.append("\n".join(lines))

    return "\n".join(rendered_blocks)


def render_port_channels(plan: TargetRefreshPlan) -> str:
    """Render port-channel parents and member mapping evidence."""
    if not plan.port_channels:
        return _comment("INFO", "No port-channels were staged by the engine.")

    rendered_blocks = []

    for port_channel in plan.port_channels:
        lines = [
            _comment("REVIEW", f"Port-channel {port_channel.channel_group} requires operator review."),
            _comment("REVIEW", f"Review flags: {_format_flags(port_channel.review_flags)}."),
            f"interface Port-channel{port_channel.channel_group}",
            _comment("REVIEW", "Parent interface is shown as a review anchor; member interfaces follow."),
            "!",
        ]
        for member in port_channel.member_interfaces:
            lines.append(_render_port_channel_member(member))

        rendered_blocks.append("\n".join(lines))

    return "\n".join(rendered_blocks)


def render_warnings(plan: TargetRefreshPlan) -> str:
    """Render plan warnings as Cisco-safe comment lines."""
    if not plan.warnings:
        return _comment("INFO", "No engine warnings were produced.")

    return "\n".join(_comment("WARNING", warning) for warning in plan.warnings)


def render_collisions(plan: TargetRefreshPlan) -> str:
    """Render collision evidence as Cisco-safe comment lines."""
    colliding = _colliding_evidence(plan)
    if not colliding:
        return _comment("INFO", "No target interface collisions were detected.")

    lines = []
    for evidence in colliding:
        lines.append(
            _comment(
                "CRITICAL",
                (
                    f"{evidence.source_interface} -> {evidence.target_interface} "
                    f"in {evidence.collision_group}; partners: "
                    f"{', '.join(evidence.collision_partners)}."
                ),
            )
        )
    return "\n".join(lines)


def render_unmapped_interfaces(plan: TargetRefreshPlan) -> str:
    """Render unmapped interfaces as Cisco-safe comment lines."""
    unmapped = _unmapped_labels(plan)
    if not unmapped:
        return _comment("INFO", "No unmapped interfaces were staged by the engine.")

    return "\n".join(_comment("REVIEW", label) for label in unmapped)


def _render_unmapped_access_port(access_port: TargetAccessPort) -> str:
    evidence = access_port.mapping_evidence
    lines = [
        _comment("REVIEW", f"{access_port.source_interface} -> UNMAPPED."),
        _comment("REVIEW", f"Applied rule: {evidence.applied_rule_type}."),
        _comment("REVIEW", f"Review urgency: {evidence.review_urgency}."),
        _comment("REVIEW", f"Review flags: {_format_flags(access_port.review_flags)}."),
    ]
    if evidence.operator_notes:
        lines.append(_comment("REVIEW", evidence.operator_notes))
    return "\n".join(lines)


def _render_unmapped_uplink(uplink: TargetUplink) -> str:
    evidence = uplink.mapping_evidence
    lines = [
        _comment("REVIEW", f"{uplink.source_interface} -> UNMAPPED uplink."),
        _comment("REVIEW", f"Applied rule: {evidence.applied_rule_type}."),
        _comment("REVIEW", f"Review urgency: {evidence.review_urgency}."),
        _comment("REVIEW", f"Review flags: {_format_flags(uplink.review_flags)}."),
    ]
    if evidence.operator_notes:
        lines.append(_comment("REVIEW", evidence.operator_notes))
    for malformed_line in uplink.malformed_trunk_allowed_vlan_lines:
        lines.append(_comment("REVIEW", f"Malformed trunk allowed VLAN source line: {malformed_line}"))
    return "\n".join(lines)


def _render_port_channel_member(member: InterfaceMappingDecision) -> str:
    if member.target_interface is None:
        lines = [
            _comment("REVIEW", f"Port-channel member {member.source_interface} -> UNMAPPED."),
            _comment("REVIEW", f"Applied rule: {member.mapping_evidence.applied_rule_type}."),
            _comment("REVIEW", f"Review urgency: {member.mapping_evidence.review_urgency}."),
        ]
        if member.mapping_evidence.operator_notes:
            lines.append(_comment("REVIEW", member.mapping_evidence.operator_notes))
        return "\n".join(lines)

    lines = [f"interface {member.target_interface}"]
    if member.description:
        lines.append(f" description {member.description}")
    lines.extend(f" {line}" for line in member.trunk_allowed_vlan_lines)
    if member.channel_group:
        channel_mode = member.channel_group_mode or "on"
        lines.append(f" channel-group {member.channel_group} mode {channel_mode}")
    for malformed_line in member.malformed_trunk_allowed_vlan_lines:
        lines.append(_comment("REVIEW", f"Malformed trunk allowed VLAN source line: {malformed_line}"))
    lines.extend(_render_evidence_comments(member.mapping_evidence, (member.reason,) if member.review_required else ()))
    lines.append("!")
    return "\n".join(lines)


def _render_evidence_comments(
    evidence: MappingEvidence,
    review_flags: tuple[str, ...],
) -> list[str]:
    if evidence.review_urgency == "GREEN" and not review_flags:
        return []

    lines = [
        _comment("REVIEW", f"Source interface: {evidence.source_interface}."),
        _comment("REVIEW", f"Applied rule: {evidence.applied_rule_type}."),
        _comment("REVIEW", f"Review urgency: {evidence.review_urgency}."),
        _comment("REVIEW", f"Review flags: {_format_flags(review_flags)}."),
    ]
    if evidence.operator_notes:
        lines.append(_comment("REVIEW", evidence.operator_notes))
    if evidence.is_collision:
        lines.append(_comment("CRITICAL", f"Collision group: {evidence.collision_group}."))
        lines.append(
            _comment(
                "CRITICAL",
                f"Collision partners: {', '.join(evidence.collision_partners)}.",
            )
        )
    return lines


def _comment(label: str, text: str) -> str:
    normalized = " ".join(str(text).split())
    return f"! {label}: {normalized}"


def _format_flags(flags: tuple[str, ...]) -> str:
    return ", ".join(flags) if flags else "none"


def _colliding_evidence(plan: TargetRefreshPlan) -> tuple[MappingEvidence, ...]:
    evidence: list[MappingEvidence] = []

    for access_port in plan.access_ports:
        if access_port.mapping_evidence.is_collision:
            evidence.append(access_port.mapping_evidence)
    for uplink in plan.uplinks:
        if uplink.mapping_evidence.is_collision:
            evidence.append(uplink.mapping_evidence)
    for port_channel in plan.port_channels:
        for member in port_channel.member_interfaces:
            if member.mapping_evidence.is_collision:
                evidence.append(member.mapping_evidence)

    return tuple(evidence)


def _unmapped_labels(plan: TargetRefreshPlan) -> tuple[str, ...]:
    labels = []

    for access_port in plan.access_ports:
        if access_port.target_interface is None:
            labels.append(f"Access interface {access_port.source_interface} is UNMAPPED.")
    for uplink in plan.uplinks:
        if uplink.target_interface is None:
            labels.append(f"Uplink {uplink.source_interface} is UNMAPPED.")
    for port_channel in plan.port_channels:
        for member in port_channel.member_interfaces:
            if member.target_interface is None:
                labels.append(
                    f"Port-channel member {member.source_interface} is UNMAPPED."
                )

    return tuple(labels)
