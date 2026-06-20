# Profile Engine Design Notes

Status: Implemented local public v1.1.0 architecture

## Purpose

The public v1.1.0 release remains a sanitized local import tool, but now has
two operator workflows:

- **Extraction Workflow**: the original v1.0.0 template-fill path.
- **Target Build Planner**: a profile-driven planning path that parses the
  source config, applies explicit target rules, exposes mapping evidence, and
  renders a reviewable new switch build sheet.

The Target Build Planner moves site-specific assumptions out of hidden Python
logic and into explicit user-owned target profiles.

## Implemented Direction

The profile engine lets users define environment-specific rules such as:

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

Standard switch refresh work is like-for-like. The normal operating assumption
is that stack members retain their identities, such as member 1 to member 1 and
member 2 to member 2, so the refreshed configuration continues to match the
physical cable plant, labels, and operator documentation.

Stack-aware translation exists as a guardrail, not as a routine workflow. A
non-identity member mapping, such as member 1 to member 3, is an exceptional and
risky schema condition. The engine may calculate it so the operator can see
exactly what the profile requested, but it should mark that decision for review
instead of presenting it as normal.

Users remain responsible for building the replacement stack, confirming
physical member order, identifying target member numbers, and verifying that
the intended active/master switch is in control before applying generated
configuration. The profile engine must not imply that physical stack
orientation has been validated.

Uplink and port-channel trunk allowed-VLAN preservation remains independently
configurable. Uplink trunks and port-channel
member trunks land in different review buckets, and keeping separate settings
lets an operator stage stricter review for one bucket without changing the
other.

Stack collision policy is "expose, don't guess." If stack translation or any
other profile rule causes multiple source interfaces to claim the same target
interface, the engine should not choose an alternate port. It should complete
the calculation, mark each competing mapping with collision evidence, group the
conflict under a shared collision identifier, and require operator review.

Multi-device stack combining is out of scope for this tool. The Switch Refresh
Configuration Import Tool handles one source switch configuration and one
like-for-like target refresh profile. Any N-to-1 stack consolidation,
cross-device VLAN reconciliation, port-channel deduplication, or intentional
stack merge belongs in the standalone Stack Combine project.

Mapping decisions should carry structured evidence for renderers instead of
requiring the renderer to infer behavior. Evidence should include the applied
rule type, rule details, collision state, collision partners, review urgency,
and plain-language operator notes.

Target interface naming must be profile-owned rather than inferred from source
configuration or hidden model guesses. Cisco access platforms can use uniform
access naming, mixed access-port speed blocks, fixed uplink blocks, modular
uplink slots, or industrial expansion-module slot layouts. The engine should
therefore support explicit mappings, ordered access-port range rules, optional
default target patterns, and target-port offsets for expansion-style layouts.

Model presets are convenience inputs, not proof. Candidate presets may be
derived from Cisco datasheets, architecture papers, and documented naming
rules, but generated output remains review material. Presets should carry a
verification level such as `operator_verified`, `cisco_derived_candidate`, or
`custom_user_defined`, and renderers should expose that status to the operator.
Custom user-defined profile rules remain the escape hatch for Cisco models,
SKUs, modules, or site standards not covered by a built-in preset.

The Target Build Planner GUI helps operators generate these user-owned profiles
without making hidden target-design decisions. Profile-builder controls may
collect access layout, custom target pattern, stack member mapping, and explicit
uplink mappings, but the saved JSON profile remains the authority consumed by
the engine. The GUI should validate the generated profile schema and then let
the normal engine review path expose unmapped interfaces, member shifts,
candidate target naming rules, and collisions.

Profile-builder controls bound stack member mappings to Cisco's
supported eight-member stack limit. Site-default uplink generation may write a
literal `{last_stack_member}` token into the JSON profile; the engine resolves
that token from the target member mapping during plan construction so the
profile remains explicit while the rendered plan receives a concrete interface.
The export/apply workflow writes a temporary local profile, reloads it through
the existing engine path, and refreshes the preview and audit panel immediately.
Structured uplink rows should be preferred for common one-to-one mappings, with
the larger text area retained as an advanced paste-in path for operators who
need more mappings than the compact row set exposes.

Rendered operator notes, review warnings, and explanatory text inserted into
lab-sheet configuration placeholders must be emitted as Cisco comment lines.
Each line should begin with `!` so that review material is skipped if an
operator accidentally leaves it in a configuration block that is later sent
through the separate console-based Cisco Config Pusher.

The renderer should remain a pure layer. It should accept a
`TargetRefreshPlan`, emit reviewable placeholder text sections, and avoid
reading files, updating GUI widgets, or re-parsing source configuration. GUI
code may choose templates and output paths, but it should not own mapping or
rendering logic.

The public test perimeter covers the core engine and renderer behaviors: clean
stack remap, stack-remap collision exposure, missing stack member handling,
ordered target port-range translation, target-port offsets for expansion-style
layouts, unsupported interface names, unmapped uplinks, port-channel member
grouping, trunk evidence preservation, malformed trunk syntax, malformed
interface declarations, comment-safe renderer notes, and accounting closure
across sanitized local bench fixtures.

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

- Target profiles are JSON files loaded through `profile_schema.py`.
- Empty or invalid profile files fail closed with visible GUI errors.
- Interface parsing is handled by `source_parser.py`; mapping decisions are
  produced by `mapping_engine.py`.
- Rule evaluation returns structured dataclasses and immutable
  `MappingEvidence` instead of mixed strings.
- Rendering is isolated in `plan_renderer.py` and emits Cisco comment-safe
  review material beginning with `!`.
- GUI/controller code gathers inputs, runs the parser/profile/engine/renderer
  path, and updates widgets. It does not own calculation behavior.

## Release Position

v1.0.0 remains the stable baseline release for the original Extraction Workflow.
v1.1.0 adds the Target Build Planner as a larger public revision with expanded
tests and documentation. Generated output remains human-review required in both
workflows.
