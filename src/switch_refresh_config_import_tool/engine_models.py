"""Dataclasses shared by the target profile mapping engine."""

from __future__ import annotations

from dataclasses import dataclass, field


class InvalidSchemaElementError(ValueError):
    """Raised when a profile contains an unsupported schema element."""


ReviewSetting = bool | str


@dataclass(frozen=True)
class SourceVlan:
    vlan_id: str
    name: str | None = None


@dataclass(frozen=True)
class SourceManagement:
    vlan_id: str | None = None
    ip_address: str | None = None
    subnet_mask: str | None = None
    default_gateway: str | None = None


@dataclass(frozen=True)
class SourceInterface:
    name: str
    body_lines: tuple[str, ...]
    description: str | None = None
    access_vlan: str | None = None
    voice_vlan: str | None = None
    trunk_allowed_vlans: str | None = None
    trunk_allowed_vlan_lines: tuple[str, ...] = ()
    malformed_trunk_allowed_vlan_lines: tuple[str, ...] = ()
    channel_group: str | None = None
    channel_group_mode: str | None = None
    shutdown: bool = False
    is_trunk: bool = False
    is_access: bool = False


@dataclass(frozen=True)
class FlaggedSourceBlock:
    first_line: str
    reason: str
    body_lines: tuple[str, ...] = ()


@dataclass(frozen=True)
class SourceSwitchConfig:
    hostname: str | None
    vtp_domain: str | None
    management: SourceManagement
    vlans: tuple[SourceVlan, ...]
    interfaces: tuple[SourceInterface, ...]
    flagged_blocks: tuple[FlaggedSourceBlock, ...] = ()
    radius_detected: bool = False


@dataclass(frozen=True)
class ProfileMetadata:
    name: str
    version: int
    vendor: str
    os_family: str


@dataclass(frozen=True)
class StackTranslationRules:
    enabled: bool = False
    member_mapping: dict[int, int] = field(default_factory=dict)


@dataclass(frozen=True)
class AccessPortRangeRule:
    source_ports: str
    target_pattern: str
    target_start: int | None = None
    rule_name: str | None = None
    verification_level: str = "custom_user_defined"


@dataclass(frozen=True)
class AccessPortTranslationRules:
    mode: str = "same_member_same_port"
    source_pattern: str = "GigabitEthernet{member}/0/{port}"
    target_pattern: str = "GigabitEthernet{member}/0/{port}"
    default_target_pattern: str | None = None
    range_rules: tuple[AccessPortRangeRule, ...] = ()
    source_range: str = "1-48"
    preserve_unmapped_as_review: bool = True


@dataclass(frozen=True)
class InterfaceTranslationRules:
    normalize_names: bool = True
    access_ports: AccessPortTranslationRules = field(
        default_factory=AccessPortTranslationRules
    )
    explicit_mappings: dict[str, str] = field(default_factory=dict)
    unmapped_behavior: str = "review_required"


@dataclass(frozen=True)
class UplinkDetectionRules:
    known_source_ports: tuple[str, ...] = ()
    description_contains: tuple[str, ...] = ()
    treat_trunks_as_candidates: bool = True


@dataclass(frozen=True)
class UplinkDestinationRules:
    mode: str = "explicit"
    mappings: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class UplinkRules:
    detection: UplinkDetectionRules = field(default_factory=UplinkDetectionRules)
    destination: UplinkDestinationRules = field(default_factory=UplinkDestinationRules)
    preserve_description: ReviewSetting = True
    preserve_trunk_allowed_vlans: ReviewSetting = "review_required"


@dataclass(frozen=True)
class PortChannelRules:
    detect_channel_groups: bool = True
    destination_channel_id_mode: str = "preserve_source_id"
    member_translation: str = "use_interface_translation"
    preserve_lacp_mode: bool = True
    preserve_trunk_allowed_vlans: ReviewSetting = "review_required"
    require_review: bool = True


@dataclass(frozen=True)
class AccessPortExtractionRules:
    preserve_description: bool = True
    preserve_access_vlan: bool = True
    preserve_voice_vlan: bool = True
    preserve_shutdown_state: ReviewSetting = "review_required"
    preserve_portfast: bool = True
    preserve_unsupported_lines: bool = False


@dataclass(frozen=True)
class ExtractionRules:
    access_ports: AccessPortExtractionRules = field(
        default_factory=AccessPortExtractionRules
    )


@dataclass(frozen=True)
class ReviewGates:
    always_review: tuple[str, ...] = ()
    fail_closed_on: tuple[str, ...] = ()


@dataclass(frozen=True)
class TemplateMapping:
    fields: dict[str, str]


@dataclass(frozen=True)
class ProfileSchema:
    profile: ProfileMetadata
    stack_translation: StackTranslationRules
    interface_translation: InterfaceTranslationRules
    uplinks: UplinkRules
    port_channels: PortChannelRules
    extraction: ExtractionRules
    review_gates: ReviewGates
    template_mapping: TemplateMapping


@dataclass(frozen=True)
class MappingEvidence:
    source_interface: str
    target_interface: str | None
    applied_rule_type: str
    rule_details: str
    is_collision: bool = False
    collision_group: str | None = None
    collision_partners: tuple[str, ...] = ()
    review_urgency: str = "GREEN"
    operator_notes: str = ""


@dataclass(frozen=True)
class InterfaceMappingDecision:
    source_interface: str
    target_interface: str | None
    role: str
    review_required: bool
    reason: str
    mapping_evidence: MappingEvidence
    description: str | None = None
    trunk_allowed_vlans: str | None = None
    trunk_allowed_vlan_lines: tuple[str, ...] = ()
    malformed_trunk_allowed_vlan_lines: tuple[str, ...] = ()
    channel_group: str | None = None
    channel_group_mode: str | None = None
    is_trunk: bool = False


@dataclass(frozen=True)
class TargetAccessPort:
    source_interface: str
    target_interface: str | None
    description: str | None
    access_vlan: str | None
    voice_vlan: str | None
    shutdown: bool
    mapping_evidence: MappingEvidence
    review_flags: tuple[str, ...] = ()


@dataclass(frozen=True)
class TargetUplink:
    source_interface: str
    target_interface: str | None
    trunk_allowed_vlans: str | None
    trunk_allowed_vlan_lines: tuple[str, ...]
    malformed_trunk_allowed_vlan_lines: tuple[str, ...]
    description: str | None
    mapping_evidence: MappingEvidence
    review_flags: tuple[str, ...] = ()


@dataclass(frozen=True)
class TargetPortChannel:
    channel_group: str
    member_interfaces: tuple[InterfaceMappingDecision, ...]
    review_flags: tuple[str, ...] = ()


@dataclass(frozen=True)
class IgnoredInterface:
    source_interface: str
    reason: str


@dataclass(frozen=True)
class EngineAuditSummary:
    collisions_count: int = 0
    unmapped_count: int = 0
    member_shifts_count: int = 0
    total_flags_count: int = 0
    is_completely_clean: bool = True


@dataclass(frozen=True)
class TargetRefreshPlan:
    hostname: str | None
    vtp_domain: str | None
    management: SourceManagement
    vlans: tuple[SourceVlan, ...]
    access_ports: tuple[TargetAccessPort, ...]
    uplinks: tuple[TargetUplink, ...]
    port_channels: tuple[TargetPortChannel, ...]
    ignored_interfaces: tuple[IgnoredInterface, ...]
    review_flags: tuple[str, ...]
    warnings: tuple[str, ...]
    audit_summary: EngineAuditSummary = field(default_factory=EngineAuditSummary)
