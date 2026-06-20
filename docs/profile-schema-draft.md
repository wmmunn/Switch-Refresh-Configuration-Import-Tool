# Profile Schema Draft

Status: Historical draft; v1.1.0 implements a smaller JSON target profile schema

This document describes the broader intended shape of a user-customizable
profile schema. v1.1.0 implements a smaller JSON target profile schema in
`profile_schema.py`; current behavior is documented in
[`profile-engine-design-notes.md`](profile-engine-design-notes.md).

The goal is to let users encode their own refresh assumptions without baking
site-specific rules into Python logic.

## Design Principles

- Extract targeted values only.
- Do not harvest unsupported sections from the old configuration.
- Keep the refresh build template user-owned and editable.
- Let users define source-to-target interface translation rules.
- Treat stack member mapping as explicit and review-gated.
- Stage inferred values for review instead of silently approving them.
- Keep parser logic, profile evaluation, template rendering, GUI presentation,
  and file I/O separate.
- Test behavior with sanitized fixtures before integrating it into the main
  workflow.

## Top-Level Shape

```yaml
profile:
  name: Generic Cisco IOS Access Switch Refresh
  version: 1
  vendor: cisco
  os_family: ios
  description: >
    Example profile for targeted import into a reviewable refresh template.

target_device:
  model: Generic Replacement Access Switch
  stack_enabled: true

target_stack:
  members:
    - member: 1
      model: Generic 48 Port Access Switch
      access_ports: 1-48
      uplink_ports:
        - TenGigabitEthernet1/1/1
        - TenGigabitEthernet1/1/2
    - member: 2
      model: Generic 48 Port Access Switch
      access_ports: 1-48
      uplink_ports:
        - TenGigabitEthernet2/1/1
        - TenGigabitEthernet2/1/2

source_stack:
  members:
    - member: 1
      access_ports: 1-48
    - member: 2
      access_ports: 1-48

stack_translation:
  enabled: true
  member_mapping:
    1: 1
    2: 2
```

## Interface Translation

Profiles should let users define how source interfaces move to the replacement
device scheme.

```yaml
interface_translation:
  normalize_names: true

  access_ports:
    mode: same_member_same_port
    source_pattern: GigabitEthernet{member}/0/{port}
    target_pattern: GigabitEthernet{member}/0/{port}
    source_range: 1-48
    preserve_unmapped_as_review: true

  explicit_mappings:
    GigabitEthernet1/0/49: TenGigabitEthernet1/1/1
    GigabitEthernet1/0/52: TenGigabitEthernet2/1/1

  unmapped_behavior: review_required
```

Potential access-port translation modes:

- `same_member_same_port`
- `same_port_new_prefix`
- `offset_mapping`
- `explicit_only`

Any unmapped interface should be retained as a review item rather than silently
dropped.

## Uplink Rules

Uplinks are high-risk and must remain review-visible.

```yaml
uplinks:
  detection:
    known_source_ports:
      - GigabitEthernet1/0/49
      - GigabitEthernet1/0/52
    description_contains:
      - UPLINK
    treat_trunks_as_candidates: true

  destination:
    mode: explicit
    mappings:
      GigabitEthernet1/0/49: TenGigabitEthernet1/1/1
      GigabitEthernet1/0/52: TenGigabitEthernet2/1/1

  preserve:
    description: true
    trunk_allowed_vlans: review_required
```

Potential uplink destination modes:

- `explicit`
- `ordered_list`
- `review_only`

Inferred uplinks should be flagged for review even when the profile allows
detection by description or trunk mode.

## Port-Channel Rules

Port-channel handling must preserve relationship visibility between the logical
Port-channel interface and member interfaces.

```yaml
port_channels:
  detect_channel_groups: true
  destination_channel_id_mode: preserve_source_id
  member_translation: use_interface_translation
  preserve_lacp_mode: true
  preserve_trunk_allowed_vlans: review_required
  require_review: true
```

Potential destination channel ID modes:

- `preserve_source_id`
- `explicit_mapping`
- `review_only`

Port-channel member translation should use the same source-to-target interface
translation model as other interfaces.

## Targeted Extraction Rules

Extraction rules define what the tool should pull from the source config.

```yaml
extraction:
  identity:
    hostname: true
    vtp_domain: true

  management:
    vlan: true
    ip_address: true
    subnet_mask: true
    default_gateway: true
    name_servers: false

  vlans:
    import_vlan_definitions: true

  access_ports:
    preserve_description: true
    preserve_access_vlan: true
    preserve_voice_vlan: true
    preserve_shutdown_state: review_required
    preserve_portfast: true
    preserve_unsupported_lines: false

  authentication:
    detect_radius: true
    detect_dot1x: true
    preserve_auth_commands: false
    summarize_for_review: true
```

Unsupported sections such as ACLs, SNMP, logging, NTP, QoS policies, banners,
and broad AAA policy should not be harvested by default.

## Review Gates

Review gates define which findings must be called out before an operator trusts
generated output.

```yaml
review_gates:
  always_review:
    - management_ip
    - uplinks
    - trunk_allowed_vlans
    - port_channels
    - stack_member_mapping
    - shutdown_state
    - authentication
    - unmapped_interfaces

  fail_closed_on:
    - invalid_profile
    - unsupported_vendor
    - ambiguous_stack_mapping
```

The first implementation should prefer fail-closed behavior for invalid or
ambiguous profiles.

## Template Mapping

Template mapping connects normalized extracted values to placeholders in the
plain text refresh build template.

```yaml
template_mapping:
  hostname: HOSTNAME
  vtp_domain: VTP_DOMAIN
  management_vlan: MGMT_VLAN
  management_ip: MGMT_IP
  management_mask: MGMT_MASK
  default_gateway: DEFAULT_GATEWAY
  name_servers: NAME_SERVERS
  vlan_list: VLAN_LIST
  trunk_allowed_vlans: TRUNK_ALLOWED_VLANS
  uplink_trunk_1: UPLINK_TRUNK_1
  uplink_trunk_2: UPLINK_TRUNK_2
  uplink_trunk_3: UPLINK_TRUNK_3
  uplink_trunk_4: UPLINK_TRUNK_4
  port_channel_interfaces: PORT_CHANNEL_INTERFACES
  port_channel_members: PORT_CHANNEL_MEMBERS
  access_port_configs: ACCESS_PORT_CONFIGS
  radius_status: RADIUS_STATUS
  dot1x_interface_summary: DOT1X_INTERFACE_SUMMARY
```

Templates define where staged values appear. Profiles define what is extracted,
translated, and review-gated.

## Expected Internal Model

The engine should evaluate profiles against a normalized model rather than raw
text wherever practical.

Potential structures:

```text
SwitchModel
- identity
- management
- vlans
- interfaces
- port_channels
- authentication_summary
- warnings

InterfaceModel
- source_name
- normalized_source_name
- translated_target_name
- role
- description
- access_vlan
- voice_vlan
- trunk_allowed_vlans
- channel_group
- shutdown_state
- preserved_lines
- review_flags
```

## Implementation Guardrails

- Do not mix GUI widget logic with parsing or profile evaluation.
- Keep parser functions and profile evaluation functions pure where practical.
- Accept explicit inputs and return structured data.
- Do not read profile files, write output files, update GUI widgets, or render
  templates from inside parser functions.
- Validate profiles before evaluating configs.
- Treat invalid profiles as review-blocking.
- Add sanitized fixture tests before connecting new schema behavior to the GUI.
- Follow the explainability rule in
  [`development-principles.md`](development-principles.md).

## Open Questions

- Should v1 of the profile engine support stack mode, or should stack support be
  documented first and implemented later?
- Should profile files be YAML only, or should JSON also be supported?
- Should template placeholder names remain fully user-configurable, or should a
  fixed set of canonical placeholders be required?
- How much formatting control should profiles have, versus keeping formatting in
  the renderer?
- Should inferred uplinks ever populate final output automatically, or only
  review sections?
