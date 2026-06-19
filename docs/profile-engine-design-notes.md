# Profile Engine Design Notes

Status: Future design candidate

## Purpose

The current public release is a sanitized local import tool. It proves the
workflow of reading an existing switch configuration, extracting selected
values, and filling a reviewable refresh build template.

The next major generalization opportunity is a configurable profile engine. The
goal is to move site-specific assumptions out of Python logic and into explicit
user-owned rules.

## Design Direction

A profile engine would let users define environment-specific rules such as:

- Site-specific uplink standards.
- Site-specific port-channel handling.
- Access-port preservation rules.
- Trunk VLAN import behavior.
- Shutdown-state review requirements.
- Management interface or SVI import rules.
- Source-to-target interface translation rules.
- Stack member mapping and target stack interface schemes.
- Values that should always require operator review.

The engine should suggest and stage values, not silently approve them. Uplinks,
port-channels, trunk allowed VLAN lists, management addressing, shutdown state,
and authentication-related settings should remain review-gated.

Stack-aware translation must remain explicit and review-gated. Users are
responsible for building the replacement stack, confirming physical member
order, identifying target member numbers, and verifying that the intended
active/master switch is in control before applying generated configuration.
The profile engine may assist with member-aware interface translation, but it
must not imply that physical stack orientation has been validated.

## Example Profile Concepts

```yaml
profile_name: Cisco IOS Refresh - Generic Access Switch

uplinks:
  known_ports:
    - TenGigabitEthernet1/1/1
    - TenGigabitEthernet1/1/2
  preserve_trunk_allowed_vlans: true
  preserve_channel_group: review_required

access_ports:
  preserve_description: true
  preserve_access_vlan: true
  preserve_voice_vlan: true
  preserve_portfast: true

interface_translation:
  access_ports:
    mode: same_member_same_port
    source_pattern: GigabitEthernet{member}/0/{port}
    target_pattern: GigabitEthernet{member}/0/{port}

  uplinks:
    mode: explicit
    mappings:
      GigabitEthernet1/0/49: TenGigabitEthernet1/1/1
      GigabitEthernet1/0/52: TenGigabitEthernet2/1/1

stack_translation:
  enabled: true
  member_mapping:
    1: 1
    2: 2

safety:
  require_review_for:
    - port_channels
    - trunk_allowed_vlans
    - shutdown_state
    - management_ip
    - stack_member_mapping
```

## Implementation Notes

- Profile loading should use safe YAML parsing.
- Empty or invalid profile files should fall back to safe defaults and emit a
  visible warning in the GUI/report.
- Interface names should be normalized before matching profile rules.
- Rule evaluation should return structured decisions instead of mixed strings
  and lists.
- Pure logic functions should be preferred so parser/rule behavior can be
  tested with sanitized fixtures.

Potential return structure:

```python
@dataclass
class InterfaceDecision:
    interface: str
    role: str
    staged_commands: list[str]
    review_flags: list[str]
    warnings: list[str]
```

## Priority Recommendation

This should not interrupt the current v1.0.0 public release path.

Recommended priority:

1. Keep v1.0.0 stable as the sanitized baseline release.
2. Collect field-test observations from the current public and private versions.
3. Identify which site-specific behaviors are truly common patterns.
4. Design the profile schema before adding new generalized extraction behavior.
5. Implement the profile engine behind tests using sanitized fixtures.

This should be treated as a v1.1 or v2.0 planning item depending on scope. If
the first version only supports a few explicit review-gated rules, v1.1 is
reasonable. If the schema becomes a broader translation framework, it should be
handled as v2.0.
