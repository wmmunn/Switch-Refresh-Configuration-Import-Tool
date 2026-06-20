"""Schema validation for the target profile mapping engine."""

from __future__ import annotations

from typing import Any, Mapping

from .engine_models import (
    AccessPortExtractionRules,
    AccessPortRangeRule,
    AccessPortTranslationRules,
    ExtractionRules,
    InterfaceTranslationRules,
    InvalidSchemaElementError,
    PortChannelRules,
    ProfileMetadata,
    ProfileSchema,
    ReviewGates,
    StackTranslationRules,
    TemplateMapping,
    UplinkDestinationRules,
    UplinkDetectionRules,
    UplinkRules,
)


SUPPORTED_TOP_LEVEL_KEYS = {
    "profile",
    "stack_translation",
    "interface_translation",
    "uplinks",
    "port_channels",
    "extraction",
    "review_gates",
    "template_mapping",
}

SUPPORTED_REVIEW_GATES = {
    "management_ip",
    "uplinks",
    "trunk_allowed_vlans",
    "port_channels",
    "stack_member_mapping",
    "shutdown_state",
    "authentication",
    "unmapped_interfaces",
    "ambiguous_stack_mapping",
    "target_interface_collision",
    "malformed_trunk_allowed_vlans",
    "target_profile_verification",
}

SUPPORTED_TEMPLATE_FIELDS = {
    "hostname",
    "vtp_domain",
    "management_vlan",
    "management_ip",
    "management_mask",
    "default_gateway",
    "vlan_list",
    "trunk_allowed_vlans",
    "uplink_trunk_1",
    "uplink_trunk_2",
    "uplink_trunk_3",
    "uplink_trunk_4",
    "port_channel_interfaces",
    "port_channel_members",
    "access_port_configs",
    "radius_status",
    "dot1x_interface_summary",
}


def build_profile_schema(raw_schema: Mapping[str, Any]) -> ProfileSchema:
    _validate_keys("top-level schema", raw_schema, SUPPORTED_TOP_LEVEL_KEYS)

    profile = _build_profile_metadata(_required_mapping(raw_schema, "profile"))
    stack_translation = _build_stack_translation(
        _optional_mapping(raw_schema, "stack_translation")
    )
    interface_translation = _build_interface_translation(
        _optional_mapping(raw_schema, "interface_translation")
    )
    uplinks = _build_uplink_rules(_optional_mapping(raw_schema, "uplinks"))
    port_channels = _build_port_channel_rules(
        _optional_mapping(raw_schema, "port_channels")
    )
    extraction = _build_extraction_rules(_optional_mapping(raw_schema, "extraction"))
    review_gates = _build_review_gates(_optional_mapping(raw_schema, "review_gates"))
    template_mapping = _build_template_mapping(
        _required_mapping(raw_schema, "template_mapping")
    )

    return ProfileSchema(
        profile=profile,
        stack_translation=stack_translation,
        interface_translation=interface_translation,
        uplinks=uplinks,
        port_channels=port_channels,
        extraction=extraction,
        review_gates=review_gates,
        template_mapping=template_mapping,
    )


def _build_profile_metadata(data: Mapping[str, Any]) -> ProfileMetadata:
    _validate_keys("profile", data, {"name", "version", "vendor", "os_family"})
    return ProfileMetadata(
        name=str(data.get("name", "")),
        version=int(data.get("version", 1)),
        vendor=str(data.get("vendor", "")),
        os_family=str(data.get("os_family", "")),
    )


def _build_stack_translation(data: Mapping[str, Any]) -> StackTranslationRules:
    _validate_keys("stack_translation", data, {"enabled", "member_mapping"})
    member_mapping = data.get("member_mapping", {})

    if not isinstance(member_mapping, Mapping):
        raise InvalidSchemaElementError("stack_translation.member_mapping must be a mapping.")

    return StackTranslationRules(
        enabled=bool(data.get("enabled", False)),
        member_mapping={
            int(source_member): int(target_member)
            for source_member, target_member in member_mapping.items()
        },
    )


def _build_interface_translation(data: Mapping[str, Any]) -> InterfaceTranslationRules:
    _validate_keys(
        "interface_translation",
        data,
        {"normalize_names", "access_ports", "explicit_mappings", "unmapped_behavior"},
    )
    access_ports = _build_access_port_translation(
        _optional_mapping(data, "access_ports")
    )
    explicit_mappings = data.get("explicit_mappings", {})

    if not isinstance(explicit_mappings, Mapping):
        raise InvalidSchemaElementError(
            "interface_translation.explicit_mappings must be a mapping."
        )

    return InterfaceTranslationRules(
        normalize_names=bool(data.get("normalize_names", True)),
        access_ports=access_ports,
        explicit_mappings={
            str(source): str(target)
            for source, target in explicit_mappings.items()
        },
        unmapped_behavior=str(data.get("unmapped_behavior", "review_required")),
    )


def _build_access_port_translation(
    data: Mapping[str, Any],
) -> AccessPortTranslationRules:
    _validate_keys(
        "interface_translation.access_ports",
        data,
        {
            "mode",
            "source_pattern",
            "target_pattern",
            "default_target_pattern",
            "range_rules",
            "source_range",
            "preserve_unmapped_as_review",
        },
    )
    return AccessPortTranslationRules(
        mode=str(data.get("mode", "same_member_same_port")),
        source_pattern=str(data.get("source_pattern", "GigabitEthernet{member}/0/{port}")),
        target_pattern=str(data.get("target_pattern", "GigabitEthernet{member}/0/{port}")),
        default_target_pattern=(
            str(data["default_target_pattern"])
            if "default_target_pattern" in data
            else None
        ),
        range_rules=_build_access_port_range_rules(data.get("range_rules", ())),
        source_range=str(data.get("source_range", "1-48")),
        preserve_unmapped_as_review=bool(data.get("preserve_unmapped_as_review", True)),
    )


def _build_access_port_range_rules(raw_rules: Any) -> tuple[AccessPortRangeRule, ...]:
    if raw_rules in (None, ()):
        return ()

    if not isinstance(raw_rules, list | tuple):
        raise InvalidSchemaElementError(
            "interface_translation.access_ports.range_rules must be a list."
        )

    rules: list[AccessPortRangeRule] = []

    for index, raw_rule in enumerate(raw_rules, start=1):
        if not isinstance(raw_rule, Mapping):
            raise InvalidSchemaElementError(
                "interface_translation.access_ports.range_rules "
                f"entry {index} must be a mapping."
            )

        _validate_keys(
            f"interface_translation.access_ports.range_rules[{index}]",
            raw_rule,
            {
                "source_ports",
                "target_pattern",
                "target_start",
                "rule_name",
                "verification_level",
            },
        )

        if "source_ports" not in raw_rule:
            raise InvalidSchemaElementError(
                "interface_translation.access_ports.range_rules "
                f"entry {index} requires 'source_ports'."
            )

        if "target_pattern" not in raw_rule:
            raise InvalidSchemaElementError(
                "interface_translation.access_ports.range_rules "
                f"entry {index} requires 'target_pattern'."
            )

        target_start = raw_rule.get("target_start")
        rules.append(
            AccessPortRangeRule(
                source_ports=str(raw_rule["source_ports"]),
                target_pattern=str(raw_rule["target_pattern"]),
                target_start=int(target_start) if target_start is not None else None,
                rule_name=(
                    str(raw_rule["rule_name"])
                    if "rule_name" in raw_rule
                    else None
                ),
                verification_level=str(
                    raw_rule.get("verification_level", "custom_user_defined")
                ),
            )
        )

    return tuple(rules)


def _build_uplink_rules(data: Mapping[str, Any]) -> UplinkRules:
    _validate_keys("uplinks", data, {"detection", "destination", "preserve"})
    detection = _build_uplink_detection(_optional_mapping(data, "detection"))
    destination = _build_uplink_destination(_optional_mapping(data, "destination"))
    preserve = _optional_mapping(data, "preserve")
    _validate_keys("uplinks.preserve", preserve, {"description", "trunk_allowed_vlans"})

    return UplinkRules(
        detection=detection,
        destination=destination,
        preserve_description=preserve.get("description", True),
        preserve_trunk_allowed_vlans=preserve.get(
            "trunk_allowed_vlans",
            "review_required",
        ),
    )


def _build_uplink_detection(data: Mapping[str, Any]) -> UplinkDetectionRules:
    _validate_keys(
        "uplinks.detection",
        data,
        {"known_source_ports", "description_contains", "treat_trunks_as_candidates"},
    )
    return UplinkDetectionRules(
        known_source_ports=tuple(str(item) for item in data.get("known_source_ports", ())),
        description_contains=tuple(str(item) for item in data.get("description_contains", ())),
        treat_trunks_as_candidates=bool(data.get("treat_trunks_as_candidates", True)),
    )


def _build_uplink_destination(data: Mapping[str, Any]) -> UplinkDestinationRules:
    _validate_keys("uplinks.destination", data, {"mode", "mappings"})
    mappings = data.get("mappings", {})

    if not isinstance(mappings, Mapping):
        raise InvalidSchemaElementError("uplinks.destination.mappings must be a mapping.")

    return UplinkDestinationRules(
        mode=str(data.get("mode", "explicit")),
        mappings={str(source): str(target) for source, target in mappings.items()},
    )


def _build_port_channel_rules(data: Mapping[str, Any]) -> PortChannelRules:
    _validate_keys(
        "port_channels",
        data,
        {
            "detect_channel_groups",
            "destination_channel_id_mode",
            "member_translation",
            "preserve_lacp_mode",
            "preserve_trunk_allowed_vlans",
            "require_review",
        },
    )
    return PortChannelRules(
        detect_channel_groups=bool(data.get("detect_channel_groups", True)),
        destination_channel_id_mode=str(
            data.get("destination_channel_id_mode", "preserve_source_id")
        ),
        member_translation=str(data.get("member_translation", "use_interface_translation")),
        preserve_lacp_mode=bool(data.get("preserve_lacp_mode", True)),
        preserve_trunk_allowed_vlans=data.get(
            "preserve_trunk_allowed_vlans",
            "review_required",
        ),
        require_review=bool(data.get("require_review", True)),
    )


def _build_extraction_rules(data: Mapping[str, Any]) -> ExtractionRules:
    _validate_keys("extraction", data, {"access_ports"})
    access_ports = _optional_mapping(data, "access_ports")
    _validate_keys(
        "extraction.access_ports",
        access_ports,
        {
            "preserve_description",
            "preserve_access_vlan",
            "preserve_voice_vlan",
            "preserve_shutdown_state",
            "preserve_portfast",
            "preserve_unsupported_lines",
        },
    )
    return ExtractionRules(
        access_ports=AccessPortExtractionRules(
            preserve_description=bool(access_ports.get("preserve_description", True)),
            preserve_access_vlan=bool(access_ports.get("preserve_access_vlan", True)),
            preserve_voice_vlan=bool(access_ports.get("preserve_voice_vlan", True)),
            preserve_shutdown_state=access_ports.get(
                "preserve_shutdown_state",
                "review_required",
            ),
            preserve_portfast=bool(access_ports.get("preserve_portfast", True)),
            preserve_unsupported_lines=bool(
                access_ports.get("preserve_unsupported_lines", False)
            ),
        )
    )


def _build_review_gates(data: Mapping[str, Any]) -> ReviewGates:
    _validate_keys("review_gates", data, {"always_review", "fail_closed_on"})
    always_review = tuple(str(item) for item in data.get("always_review", ()))
    fail_closed_on = tuple(str(item) for item in data.get("fail_closed_on", ()))

    for gate in always_review + fail_closed_on:
        if gate not in SUPPORTED_REVIEW_GATES:
            raise InvalidSchemaElementError(
                f"Unsupported review gate: {gate!r}. "
                f"Supported values are: {', '.join(sorted(SUPPORTED_REVIEW_GATES))}."
            )

    return ReviewGates(always_review=always_review, fail_closed_on=fail_closed_on)


def _build_template_mapping(data: Mapping[str, Any]) -> TemplateMapping:
    _validate_keys("template_mapping", data, SUPPORTED_TEMPLATE_FIELDS)
    return TemplateMapping(fields={str(key): str(value) for key, value in data.items()})


def _required_mapping(parent: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = parent.get(key)
    if not isinstance(value, Mapping):
        raise InvalidSchemaElementError(f"Profile schema requires a {key!r} mapping.")
    return value


def _optional_mapping(parent: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = parent.get(key, {})
    if not isinstance(value, Mapping):
        raise InvalidSchemaElementError(f"Schema element {key!r} must be a mapping.")
    return value


def _validate_keys(
    mapping_name: str,
    mapping_value: Mapping[str, Any],
    supported_keys: set[str],
) -> None:
    for key in mapping_value:
        if key not in supported_keys:
            raise InvalidSchemaElementError(
                f"Unsupported {mapping_name} element: {key!r}. "
                f"Supported values are: {', '.join(sorted(supported_keys))}."
            )
