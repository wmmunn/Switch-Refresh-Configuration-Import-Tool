"""Explicit source-to-target mapping engine for target profile support."""

from __future__ import annotations

from dataclasses import replace
import re

from .engine_models import (
    EngineAuditSummary,
    InterfaceMappingDecision,
    IgnoredInterface,
    InvalidSchemaElementError,
    MappingEvidence,
    ProfileSchema,
    SourceInterface,
    SourceSwitchConfig,
    TargetAccessPort,
    TargetPortChannel,
    TargetRefreshPlan,
    TargetUplink,
)


# Example: GigabitEthernet1/0/24
INTERFACE_MEMBER_PORT_PATTERN = re.compile(
    r"^(?P<prefix>[A-Za-z]+Ethernet)(?P<member>\d+)/0/(?P<port>\d+)$"
)

# Example: GigabitEthernet0/24
INTERFACE_STANDALONE_PORT_PATTERN = re.compile(
    r"^(?P<prefix>[A-Za-z]+Ethernet)0/(?P<port>\d+)$"
)


def build_target_refresh_plan(
    source_config: SourceSwitchConfig,
    schema: ProfileSchema,
) -> TargetRefreshPlan:
    """Evaluate source data against profile rules and return a target plan."""
    access_ports: list[TargetAccessPort] = []
    uplinks: list[TargetUplink] = []
    port_channels: list[TargetPortChannel] = []
    ignored_interfaces: list[IgnoredInterface] = []
    review_flags: list[str] = list(schema.review_gates.always_review)
    warnings: list[str] = []

    for source_interface in source_config.interfaces:
        if _is_port_channel_member(source_interface, schema):
            continue

        if _is_empty_interface(source_interface):
            ignored_interfaces.append(
                IgnoredInterface(
                    source_interface=source_interface.name,
                    reason="empty_interface",
                )
            )
        elif _is_uplink_candidate(source_interface, schema):
            uplinks.append(_build_uplink(source_interface, schema, review_flags, warnings))
        elif _is_access_port_candidate(source_interface):
            access_ports.append(
                _build_access_port(source_interface, schema, review_flags, warnings)
            )

    if schema.port_channels.detect_channel_groups:
        port_channels = _build_port_channels(source_config, schema, review_flags)

    _flag_target_interface_collisions(
        access_ports,
        uplinks,
        port_channels,
        review_flags,
        warnings,
    )

    deduplicated_review_flags = tuple(_deduplicate(review_flags))
    audit_summary = _build_audit_summary(
        access_ports,
        uplinks,
        port_channels,
        deduplicated_review_flags,
    )

    return TargetRefreshPlan(
        hostname=source_config.hostname,
        vtp_domain=source_config.vtp_domain,
        management=source_config.management,
        vlans=source_config.vlans,
        access_ports=tuple(access_ports),
        uplinks=tuple(uplinks),
        port_channels=tuple(port_channels),
        ignored_interfaces=tuple(ignored_interfaces),
        review_flags=deduplicated_review_flags,
        warnings=tuple(warnings),
        audit_summary=audit_summary,
    )


def _is_access_port_candidate(source_interface: SourceInterface) -> bool:
    if source_interface.name.lower().startswith("vlan"):
        return False

    if source_interface.name.lower().startswith("port-channel"):
        return False

    if source_interface.is_trunk:
        return False

    return source_interface.is_access or source_interface.access_vlan is not None


def _is_uplink_candidate(
    source_interface: SourceInterface,
    schema: ProfileSchema,
) -> bool:
    # Port-channel parents are excluded from uplink detection by default;
    # physical member interfaces carry uplink movement under port_channels.
    # A future schema flag may opt a Port-channel into logical uplink mapping.
    # That opt-in behavior is not supported yet.
    if source_interface.name.lower().startswith("port-channel"):
        return False

    detection = schema.uplinks.detection

    if source_interface.name in detection.known_source_ports:
        return True

    if detection.treat_trunks_as_candidates and source_interface.is_trunk:
        return True

    if source_interface.description:
        description = source_interface.description.lower()
        for marker in detection.description_contains:
            if marker.lower() in description:
                return True

    return False


def _is_empty_interface(source_interface: SourceInterface) -> bool:
    return not any(line.strip() for line in source_interface.body_lines)


def _is_port_channel_member(
    source_interface: SourceInterface,
    schema: ProfileSchema,
) -> bool:
    return bool(schema.port_channels.detect_channel_groups and source_interface.channel_group)


def _build_access_port(
    source_interface: SourceInterface,
    schema: ProfileSchema,
    review_flags: list[str],
    warnings: list[str],
) -> TargetAccessPort:
    decision = translate_interface(source_interface.name, "access_port", schema)

    if decision.target_interface is None:
        warnings.append(f"Access interface {source_interface.name} has no target mapping.")
        if "unmapped_interfaces" not in review_flags:
            review_flags.append("unmapped_interfaces")
    else:
        target_interface = decision.target_interface

    access_review_flags: list[str] = []

    if source_interface.shutdown:
        access_review_flags.append("shutdown_state")
        if "shutdown_state" not in review_flags:
            review_flags.append("shutdown_state")

    if decision.review_required:
        access_review_flags.append(decision.reason)
        if decision.reason not in review_flags:
            review_flags.append(decision.reason)

    return TargetAccessPort(
        source_interface=source_interface.name,
        target_interface=decision.target_interface,
        description=source_interface.description,
        access_vlan=source_interface.access_vlan,
        voice_vlan=source_interface.voice_vlan,
        shutdown=source_interface.shutdown,
        mapping_evidence=decision.mapping_evidence,
        review_flags=tuple(access_review_flags),
    )


def _build_uplink(
    source_interface: SourceInterface,
    schema: ProfileSchema,
    review_flags: list[str],
    warnings: list[str],
) -> TargetUplink:
    raw_target_interface = schema.uplinks.destination.mappings.get(source_interface.name)
    target_interface = _resolve_target_tokens(raw_target_interface, schema)

    if raw_target_interface is None:
        raw_target_interface = schema.interface_translation.explicit_mappings.get(
            source_interface.name
        )
        target_interface = _resolve_target_tokens(raw_target_interface, schema)
        applied_rule_type = "EXPLICIT_INTERFACE"
        rule_details = (
            "interface_translation.explicit_mappings"
            f"[{source_interface.name!r}]"
        )
    else:
        applied_rule_type = "EXPLICIT_UPLINK"
        rule_details = f"uplinks.destination.mappings[{source_interface.name!r}]"

    uplink_review_flags = ["uplinks"]
    review_urgency = "GREEN"
    operator_notes = "Uplink target was selected from an explicit profile mapping."

    if target_interface is None:
        uplink_review_flags.append("unmapped_interfaces")
        review_urgency = "WARNING_UNMAPPED"
        applied_rule_type = "UNMAPPED_UPLINK"
        rule_details = "No uplink destination or explicit interface mapping matched."
        operator_notes = "No target uplink was found; operator review is required."

    if schema.uplinks.preserve_trunk_allowed_vlans == "review_required":
        uplink_review_flags.append("trunk_allowed_vlans")

    if source_interface.malformed_trunk_allowed_vlan_lines:
        uplink_review_flags.append("malformed_trunk_allowed_vlans")
        warnings.append(
            "Malformed trunk allowed VLAN syntax on "
            f"{source_interface.name}: "
            f"{'; '.join(source_interface.malformed_trunk_allowed_vlan_lines)}."
        )

    for flag in uplink_review_flags:
        if flag not in review_flags:
            review_flags.append(flag)

    return TargetUplink(
        source_interface=source_interface.name,
        target_interface=target_interface,
        trunk_allowed_vlans=source_interface.trunk_allowed_vlans,
        trunk_allowed_vlan_lines=source_interface.trunk_allowed_vlan_lines,
        malformed_trunk_allowed_vlan_lines=source_interface.malformed_trunk_allowed_vlan_lines,
        description=source_interface.description,
        mapping_evidence=MappingEvidence(
            source_interface=source_interface.name,
            target_interface=target_interface,
            applied_rule_type=applied_rule_type,
            rule_details=rule_details,
            review_urgency=review_urgency,
            operator_notes=operator_notes,
        ),
        review_flags=tuple(uplink_review_flags),
    )


def _build_port_channels(
    source_config: SourceSwitchConfig,
    schema: ProfileSchema,
    review_flags: list[str],
) -> list[TargetPortChannel]:
    grouped_members: dict[str, list[InterfaceMappingDecision]] = {}

    for source_interface in source_config.interfaces:
        if not source_interface.channel_group:
            continue

        decision = _build_port_channel_member_decision(source_interface, schema)
        grouped_members.setdefault(source_interface.channel_group, []).append(decision)

    port_channels: list[TargetPortChannel] = []

    for channel_group, members in grouped_members.items():
        review_items: list[str] = []

        if schema.port_channels.require_review:
            review_items.append("port_channels")

        if schema.port_channels.preserve_trunk_allowed_vlans == "review_required":
            review_items.append("trunk_allowed_vlans")

        for member in members:
            if member.review_required and member.reason not in review_items:
                review_items.append(member.reason)

        for review_item in review_items:
            if review_item not in review_flags:
                review_flags.append(review_item)

        port_channels.append(
            TargetPortChannel(
                channel_group=channel_group,
                member_interfaces=tuple(members),
                review_flags=tuple(review_items),
            )
        )

    return port_channels


def _build_port_channel_member_decision(
    source_interface: SourceInterface,
    schema: ProfileSchema,
) -> InterfaceMappingDecision:
    decision = translate_interface(source_interface.name, "port_channel_member", schema)

    return InterfaceMappingDecision(
        source_interface=decision.source_interface,
        target_interface=decision.target_interface,
        role=decision.role,
        review_required=decision.review_required,
        reason=decision.reason,
        mapping_evidence=replace(
            decision.mapping_evidence,
            operator_notes=(
                f"Port-channel member {source_interface.name} uses "
                f"{decision.mapping_evidence.operator_notes}"
            ),
        ),
        description=source_interface.description,
        trunk_allowed_vlans=source_interface.trunk_allowed_vlans,
        trunk_allowed_vlan_lines=source_interface.trunk_allowed_vlan_lines,
        malformed_trunk_allowed_vlan_lines=source_interface.malformed_trunk_allowed_vlan_lines,
        channel_group=source_interface.channel_group,
        channel_group_mode=source_interface.channel_group_mode,
        is_trunk=source_interface.is_trunk,
    )


def translate_interface(
    source_interface_name: str,
    role: str,
    schema: ProfileSchema,
) -> InterfaceMappingDecision:
    """Translate a source interface name to a target interface name."""
    raw_explicit_target = schema.interface_translation.explicit_mappings.get(
        source_interface_name
    )
    explicit_target = _resolve_target_tokens(raw_explicit_target, schema)

    if raw_explicit_target is not None:
        return InterfaceMappingDecision(
            source_interface=source_interface_name,
            target_interface=explicit_target,
            role=role,
            review_required=False,
            reason="explicit_mapping",
            mapping_evidence=MappingEvidence(
                source_interface=source_interface_name,
                target_interface=explicit_target,
                applied_rule_type="EXPLICIT_INTERFACE",
                rule_details=(
                    "interface_translation.explicit_mappings"
                    f"[{source_interface_name!r}]={raw_explicit_target!r}"
                ),
                operator_notes="Target interface was selected from an explicit profile mapping.",
            ),
        )

    access_rules = schema.interface_translation.access_ports

    if access_rules.mode == "same_member_same_port":
        return _translate_same_member_same_port(source_interface_name, role, schema)

    if access_rules.mode == "ordered_port_ranges":
        return _translate_ordered_port_ranges(source_interface_name, role, schema)

    if access_rules.mode == "explicit_only":
        return InterfaceMappingDecision(
            source_interface=source_interface_name,
            target_interface=None,
            role=role,
            review_required=True,
            reason="explicit_mapping_required",
            mapping_evidence=MappingEvidence(
                source_interface=source_interface_name,
                target_interface=None,
                applied_rule_type="EXPLICIT_MAPPING_REQUIRED",
                rule_details="interface_translation.access_ports.mode='explicit_only'",
                review_urgency="WARNING_UNMAPPED",
                operator_notes="Profile requires an explicit mapping for this interface.",
            ),
        )

    raise InvalidSchemaElementError(
        f"Unsupported access port translation mode: {access_rules.mode!r}."
    )


def _translate_same_member_same_port(
    source_interface_name: str,
    role: str,
    schema: ProfileSchema,
) -> InterfaceMappingDecision:
    interface_parts = _match_source_member_port(source_interface_name)

    if interface_parts is None:
        return InterfaceMappingDecision(
            source_interface=source_interface_name,
            target_interface=None,
            role=role,
            review_required=True,
            reason="unsupported_interface_name",
            mapping_evidence=MappingEvidence(
                source_interface=source_interface_name,
                target_interface=None,
                applied_rule_type="UNSUPPORTED_INTERFACE_NAME",
                rule_details=(
                    "Interface did not match "
                    "GigabitEthernet{member}/0/{port} or "
                    "GigabitEthernet0/{port}-style translation."
                ),
                review_urgency="WARNING_UNMAPPED",
                operator_notes=(
                    "Interface name is unsupported by the current stack/access "
                    "translation rule; no target was assigned."
                ),
            ),
        )

    source_member = interface_parts["member"]
    source_port = str(interface_parts["port"])
    source_format = interface_parts["format"]
    member_mapping = schema.stack_translation.member_mapping

    if schema.stack_translation.enabled and source_member not in member_mapping:
        return InterfaceMappingDecision(
            source_interface=source_interface_name,
            target_interface=None,
            role=role,
            review_required=True,
            reason="missing_stack_member_mapping",
            mapping_evidence=MappingEvidence(
                source_interface=source_interface_name,
                target_interface=None,
                applied_rule_type="MISSING_STACK_MEMBER_MAPPING",
                rule_details=(
                    f"stack_translation.member_mapping has no entry for "
                    f"source member {source_member}."
                ),
                review_urgency="WARNING_UNMAPPED",
                operator_notes=(
                    "Stack translation is enabled, but this source member has "
                    "no explicit member mapping; no target was assigned."
                ),
            ),
        )

    target_member = member_mapping.get(source_member, source_member)
    target_interface = schema.interface_translation.access_ports.target_pattern.format(
        member=target_member,
        port=source_port,
    )

    review_required = False
    reason = "same_member_same_port"
    applied_rule_type = "DEFAULT_ACCESS"
    rule_details = (
        "interface_translation.access_ports.mode='same_member_same_port'; "
        f"target_pattern={schema.interface_translation.access_ports.target_pattern!r}; "
        f"source_format={source_format!r}"
    )
    operator_notes = "Source member and port were preserved by the access-port rule."
    review_urgency = "GREEN"

    if source_member != target_member:
        review_required = True
        reason = "stack_member_mapping"
        applied_rule_type = "STACK_REMAP"
        rule_details = (
            f"stack_translation.member_mapping[{source_member}]={target_member}; "
            f"target_pattern={schema.interface_translation.access_ports.target_pattern!r}"
        )
        operator_notes = (
            f"Stack member remap changed source member {source_member} "
            f"to target member {target_member}; source port {source_port} "
            "was preserved. This is an exceptional refresh condition and "
            "requires operator review."
        )
        review_urgency = "WARNING_STACK_REMAP"
    elif schema.stack_translation.enabled and source_member in member_mapping:
        applied_rule_type = "STACK_IDENTITY"
        rule_details = (
            f"stack_translation.member_mapping[{source_member}]={target_member}; "
            f"source_format={source_format!r}"
        )
        operator_notes = (
            f"Explicit stack member identity mapping kept member {source_member}; "
            f"source port {source_port} was preserved."
        )

    return InterfaceMappingDecision(
        source_interface=source_interface_name,
        target_interface=target_interface,
        role=role,
        review_required=review_required,
        reason=reason,
        mapping_evidence=MappingEvidence(
            source_interface=source_interface_name,
            target_interface=target_interface,
            applied_rule_type=applied_rule_type,
            rule_details=rule_details,
            review_urgency=review_urgency,
            operator_notes=operator_notes,
        ),
    )


def _translate_ordered_port_ranges(
    source_interface_name: str,
    role: str,
    schema: ProfileSchema,
) -> InterfaceMappingDecision:
    base_decision = _parse_member_port_for_translation(
        source_interface_name,
        role,
        unsupported_rule_name="ordered port-range translation",
    )
    if base_decision is not None:
        return base_decision

    interface_parts = _match_source_member_port(source_interface_name)
    if interface_parts is None:
        raise AssertionError("source interface was parsed before ordered range mapping")

    source_member = interface_parts["member"]
    source_port = interface_parts["port"]
    member_mapping = schema.stack_translation.member_mapping

    if schema.stack_translation.enabled and source_member not in member_mapping:
        return _missing_stack_member_decision(source_interface_name, role, source_member)

    target_member = member_mapping.get(source_member, source_member)
    access_rules = schema.interface_translation.access_ports

    for index, range_rule in enumerate(access_rules.range_rules, start=1):
        if not _port_in_range(source_port, range_rule.source_ports):
            continue

        first_source_port = _first_port_in_range(range_rule.source_ports)
        target_port = source_port
        if range_rule.target_start is not None:
            target_port = range_rule.target_start + (source_port - first_source_port)

        target_interface = range_rule.target_pattern.format(
            member=target_member,
            port=source_port,
            target_port=target_port,
        )
        rule_label = range_rule.rule_name or f"range rule {index}"
        verification_requires_review = (
            range_rule.verification_level != "operator_verified"
        )
        review_required = source_member != target_member or verification_requires_review
        reason = "ordered_port_range"
        review_urgency = "GREEN"
        if verification_requires_review:
            reason = "target_profile_verification"
            review_urgency = "WARNING_PROFILE_REVIEW"
        if source_member != target_member:
            reason = "stack_member_mapping"
            review_urgency = "WARNING_STACK_REMAP"
        applied_rule_type = (
            "STACK_REMAP_RANGE_RULE"
            if source_member != target_member
            else "ACCESS_PORT_RANGE_RULE"
        )
        operator_notes = (
            f"Target interface was selected by ordered access-port {rule_label}."
        )
        if verification_requires_review:
            operator_notes = (
                f"{operator_notes} Rule verification level is "
                f"{range_rule.verification_level}; operator confirmation is required."
            )

        if source_member != target_member:
            operator_notes = (
                f"Stack member remap changed source member {source_member} "
                f"to target member {target_member}; source port {source_port} "
                f"used ordered access-port {rule_label}. This is an exceptional "
                "refresh condition and requires operator review."
            )

        return InterfaceMappingDecision(
            source_interface=source_interface_name,
            target_interface=target_interface,
            role=role,
            review_required=review_required,
            reason=reason,
            mapping_evidence=MappingEvidence(
                source_interface=source_interface_name,
                target_interface=target_interface,
                applied_rule_type=applied_rule_type,
                rule_details=(
                    f"interface_translation.access_ports.range_rules[{index}]: "
                    f"source_ports={range_rule.source_ports!r}; "
                    f"target_pattern={range_rule.target_pattern!r}; "
                    f"target_start={range_rule.target_start!r}; "
                    f"verification_level={range_rule.verification_level!r}"
                ),
                review_urgency=review_urgency,
                operator_notes=operator_notes,
            ),
        )

    if access_rules.default_target_pattern:
        target_interface = access_rules.default_target_pattern.format(
            member=target_member,
            port=source_port,
            target_port=source_port,
        )
        review_required = source_member != target_member
        reason = "stack_member_mapping" if review_required else "default_access_pattern"
        review_urgency = "WARNING_STACK_REMAP" if review_required else "GREEN"
        applied_rule_type = (
            "STACK_REMAP_DEFAULT_PATTERN" if review_required else "DEFAULT_ACCESS_PATTERN"
        )

        return InterfaceMappingDecision(
            source_interface=source_interface_name,
            target_interface=target_interface,
            role=role,
            review_required=review_required,
            reason=reason,
            mapping_evidence=MappingEvidence(
                source_interface=source_interface_name,
                target_interface=target_interface,
                applied_rule_type=applied_rule_type,
                rule_details=(
                    "interface_translation.access_ports.default_target_pattern="
                    f"{access_rules.default_target_pattern!r}"
                ),
                review_urgency=review_urgency,
                operator_notes=(
                    "Target interface was selected by the default access-port "
                    "pattern after no ordered range rule matched."
                ),
            ),
        )

    return InterfaceMappingDecision(
        source_interface=source_interface_name,
        target_interface=None,
        role=role,
        review_required=True,
        reason="no_access_port_range_rule",
        mapping_evidence=MappingEvidence(
            source_interface=source_interface_name,
            target_interface=None,
            applied_rule_type="NO_ACCESS_PORT_RANGE_RULE",
            rule_details=(
                "interface_translation.access_ports.mode='ordered_port_ranges'; "
                f"no range rule matched source port {source_port}."
            ),
            review_urgency="WARNING_UNMAPPED",
            operator_notes=(
                "No ordered access-port range rule matched this source port; "
                "no target was assigned."
            ),
        ),
    )


def _parse_member_port_for_translation(
    source_interface_name: str,
    role: str,
    unsupported_rule_name: str,
) -> InterfaceMappingDecision | None:
    interface_parts = _match_source_member_port(source_interface_name)
    if interface_parts is not None:
        return None

    return InterfaceMappingDecision(
        source_interface=source_interface_name,
        target_interface=None,
        role=role,
        review_required=True,
        reason="unsupported_interface_name",
        mapping_evidence=MappingEvidence(
            source_interface=source_interface_name,
            target_interface=None,
            applied_rule_type="UNSUPPORTED_INTERFACE_NAME",
            rule_details=(
                "Interface did not match "
                f"GigabitEthernet{{member}}/0/{{port}} or "
                f"GigabitEthernet0/{{port}}-style {unsupported_rule_name}."
            ),
            review_urgency="WARNING_UNMAPPED",
            operator_notes=(
                "Interface name is unsupported by the current stack/access "
                "translation rule; no target was assigned."
            ),
        ),
    )


def _match_source_member_port(source_interface_name: str) -> dict[str, int | str] | None:
    member_match = INTERFACE_MEMBER_PORT_PATTERN.match(source_interface_name)
    if member_match:
        return {
            "member": int(member_match.group("member")),
            "port": int(member_match.group("port")),
            "format": "member_slot_port",
        }

    standalone_match = INTERFACE_STANDALONE_PORT_PATTERN.match(source_interface_name)
    if standalone_match:
        return {
            "member": 1,
            "port": int(standalone_match.group("port")),
            "format": "standalone_port",
        }

    return None


def _missing_stack_member_decision(
    source_interface_name: str,
    role: str,
    source_member: int,
) -> InterfaceMappingDecision:
    return InterfaceMappingDecision(
        source_interface=source_interface_name,
        target_interface=None,
        role=role,
        review_required=True,
        reason="missing_stack_member_mapping",
        mapping_evidence=MappingEvidence(
            source_interface=source_interface_name,
            target_interface=None,
            applied_rule_type="MISSING_STACK_MEMBER_MAPPING",
            rule_details=(
                f"stack_translation.member_mapping has no entry for "
                f"source member {source_member}."
            ),
            review_urgency="WARNING_UNMAPPED",
            operator_notes=(
                "Stack translation is enabled, but this source member has "
                "no explicit member mapping; no target was assigned."
            ),
        ),
    )


def _port_in_range(source_port: int, range_text: str) -> bool:
    return any(start <= source_port <= end for start, end in _parse_port_ranges(range_text))


def _first_port_in_range(range_text: str) -> int:
    return _parse_port_ranges(range_text)[0][0]


def _parse_port_ranges(range_text: str) -> tuple[tuple[int, int], ...]:
    ranges = []

    for raw_part in range_text.split(","):
        part = raw_part.strip()
        if not part:
            continue

        if "-" in part:
            raw_start, raw_end = part.split("-", 1)
            start = int(raw_start.strip())
            end = int(raw_end.strip())
        else:
            start = int(part)
            end = start

        if start > end:
            raise InvalidSchemaElementError(
                f"Invalid port range {range_text!r}: start {start} exceeds end {end}."
            )

        ranges.append((start, end))

    if not ranges:
        raise InvalidSchemaElementError("Port range cannot be empty.")

    return tuple(ranges)


def _deduplicate(values: list[str]) -> list[str]:
    deduplicated: list[str] = []

    for value in values:
        if value not in deduplicated:
            deduplicated.append(value)

    return deduplicated


def _resolve_target_tokens(
    target_interface: str | None,
    schema: ProfileSchema,
) -> str | None:
    if target_interface is None:
        return None

    if "{last_stack_member}" not in target_interface:
        return target_interface

    if schema.stack_translation.member_mapping:
        last_stack_member = max(schema.stack_translation.member_mapping.values())
    else:
        last_stack_member = 1

    return target_interface.replace("{last_stack_member}", str(last_stack_member))


def _build_audit_summary(
    access_ports: list[TargetAccessPort],
    uplinks: list[TargetUplink],
    port_channels: list[TargetPortChannel],
    review_flags: tuple[str, ...],
) -> EngineAuditSummary:
    evidence_items = []
    evidence_items.extend(access_port.mapping_evidence for access_port in access_ports)
    evidence_items.extend(uplink.mapping_evidence for uplink in uplinks)
    for port_channel in port_channels:
        evidence_items.extend(
            member.mapping_evidence for member in port_channel.member_interfaces
        )

    collision_groups = {
        evidence.collision_group
        for evidence in evidence_items
        if evidence.is_collision and evidence.collision_group is not None
    }
    unmapped_count = sum(
        1 for evidence in evidence_items if evidence.target_interface is None
    )
    member_shifts_count = sum(
        1
        for evidence in evidence_items
        if evidence.applied_rule_type.startswith("STACK_REMAP")
    )
    total_flags_count = len(review_flags)
    is_completely_clean = not (
        collision_groups
        or unmapped_count
        or member_shifts_count
        or total_flags_count
    )

    return EngineAuditSummary(
        collisions_count=len(collision_groups),
        unmapped_count=unmapped_count,
        member_shifts_count=member_shifts_count,
        total_flags_count=total_flags_count,
        is_completely_clean=is_completely_clean,
    )


def _flag_target_interface_collisions(
    access_ports: list[TargetAccessPort],
    uplinks: list[TargetUplink],
    port_channels: list[TargetPortChannel],
    review_flags: list[str],
    warnings: list[str],
) -> None:
    target_sources: dict[str, list[str]] = {}

    for access_port in access_ports:
        if access_port.target_interface is not None:
            target_sources.setdefault(access_port.target_interface, []).append(
                access_port.source_interface
            )

    for uplink in uplinks:
        if uplink.target_interface is not None:
            target_sources.setdefault(uplink.target_interface, []).append(
                uplink.source_interface
            )

    for port_channel in port_channels:
        for member in port_channel.member_interfaces:
            if member.target_interface is not None:
                target_sources.setdefault(member.target_interface, []).append(
                    member.source_interface
                )

    for target_interface, source_interfaces in target_sources.items():
        unique_sources = _deduplicate(source_interfaces)
        if len(unique_sources) < 2:
            continue

        warnings.append(
            "Target interface collision: "
            f"{target_interface} is mapped from {', '.join(unique_sources)}."
        )

        if "target_interface_collision" not in review_flags:
            review_flags.append("target_interface_collision")

        collision_group = f"GROUP_{target_interface}"
        partners_by_source = {
            source_interface: tuple(
                partner
                for partner in unique_sources
                if partner != source_interface
            )
            for source_interface in unique_sources
        }
        _mark_colliding_access_ports(
            access_ports,
            collision_group,
            partners_by_source,
        )
        _mark_colliding_uplinks(
            uplinks,
            collision_group,
            partners_by_source,
        )
        _mark_colliding_port_channel_members(
            port_channels,
            collision_group,
            partners_by_source,
        )


def _collision_evidence(
    evidence: MappingEvidence,
    collision_group: str,
    collision_partners: tuple[str, ...],
) -> MappingEvidence:
    return replace(
        evidence,
        is_collision=True,
        collision_group=collision_group,
        collision_partners=collision_partners,
        review_urgency="CRITICAL_COLLISION",
        operator_notes=(
            f"{evidence.operator_notes} Collision group {collision_group}: "
            f"target {evidence.target_interface} is also claimed by "
            f"{', '.join(collision_partners)}."
        ),
    )


def _mark_colliding_access_ports(
    access_ports: list[TargetAccessPort],
    collision_group: str,
    partners_by_source: dict[str, tuple[str, ...]],
) -> None:
    for index, access_port in enumerate(access_ports):
        partners = partners_by_source.get(access_port.source_interface)
        if partners is None:
            continue

        review_flags = list(access_port.review_flags)
        if "target_interface_collision" not in review_flags:
            review_flags.append("target_interface_collision")

        access_ports[index] = replace(
            access_port,
            mapping_evidence=_collision_evidence(
                access_port.mapping_evidence,
                collision_group,
                partners,
            ),
            review_flags=tuple(review_flags),
        )


def _mark_colliding_uplinks(
    uplinks: list[TargetUplink],
    collision_group: str,
    partners_by_source: dict[str, tuple[str, ...]],
) -> None:
    for index, uplink in enumerate(uplinks):
        partners = partners_by_source.get(uplink.source_interface)
        if partners is None:
            continue

        review_flags = list(uplink.review_flags)
        if "target_interface_collision" not in review_flags:
            review_flags.append("target_interface_collision")

        uplinks[index] = replace(
            uplink,
            mapping_evidence=_collision_evidence(
                uplink.mapping_evidence,
                collision_group,
                partners,
            ),
            review_flags=tuple(review_flags),
        )


def _mark_colliding_port_channel_members(
    port_channels: list[TargetPortChannel],
    collision_group: str,
    partners_by_source: dict[str, tuple[str, ...]],
) -> None:
    for port_channel_index, port_channel in enumerate(port_channels):
        updated_members = []
        changed = False

        for member in port_channel.member_interfaces:
            partners = partners_by_source.get(member.source_interface)
            if partners is None:
                updated_members.append(member)
                continue

            updated_members.append(
                replace(
                    member,
                    review_required=True,
                    reason="target_interface_collision",
                    mapping_evidence=_collision_evidence(
                        member.mapping_evidence,
                        collision_group,
                        partners,
                    ),
                )
            )
            changed = True

        if changed:
            port_channels[port_channel_index] = replace(
                port_channel,
                member_interfaces=tuple(updated_members),
            )
