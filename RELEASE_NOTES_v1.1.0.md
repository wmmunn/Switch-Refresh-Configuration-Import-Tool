# Switch Refresh Configuration Import Tool v1.1.0

## Summary

v1.1.0 adds the Target Build Planner, a profile-driven planning workflow for
creating human-reviewable new switch build sheets from sanitized Cisco IOS
running-config input.

The original Extraction Workflow remains available. v1.1.0 does not turn the
tool into a config pusher, device connector, or automatic deployment system.
Generated output is still review material and must be validated by a human
operator before use.

## Major Change

The project now separates the refresh process into smaller, testable engine
pieces:

- `source_parser.py` parses raw running-config text into structured source
  dataclasses.
- `profile_schema.py` loads target profile JSON into typed schema dataclasses.
- `mapping_engine.py` combines source data and target profile rules into a
  `TargetRefreshPlan`.
- `plan_renderer.py` renders that plan into template placeholders for a new
  switch build sheet.
- The GUI gathers files and operator choices, displays audit counters, and
  previews rendered output.

This structure is intended to make behavior easier to test, explain, review,
and extend without hiding target-design assumptions inside UI code.

## Target Build Planner

The Target Build Planner supports:

- Access-port target naming profiles.
- Mixed target interface layouts.
- Explicit stack member mapping with a 1-to-8 member guardrail.
- Site-default uplink mapping using a `{last_stack_member}` token.
- Custom uplink source-to-target mappings.
- Review visibility for uplinks, port-channels, trunk allowed VLAN evidence,
  malformed trunk syntax, unsupported interface names, and unmapped interfaces.

The engine follows an "Expose, Don't Guess" rule. It does not silently choose
alternate ports or infer a target design when the profile is incomplete.

## Review And Safety Behavior

- Unsupported interface names are rendered as unmapped.
- Missing stack member mappings produce `WARNING_UNMAPPED`.
- Non-identity stack remaps produce `WARNING_STACK_REMAP`.
- Target interface collisions produce `CRITICAL_COLLISION`.
- Collision evidence is attached to every affected mapping with a shared
  collision group and collision partners.
- Operator notes, warnings, and rendered review text begin with `!` so they are
  Cisco comment-safe if accidentally left in a config block.

## GUI Updates

- Renamed the new engine tab to `Target Build Planner`.
- Collapsed advanced target profile controls behind `Target Profile Options`.
- Reworded profile controls to use operator-facing language instead of leading
  with JSON/schema terminology.
- Clarified that the legacy `G`/`Fi` dropdown belongs only to the original
  Extraction Workflow.
- Increased default window sizing and wrapping to reduce text clipping at
  launch.

## Validation

The public test suite now covers parser behavior, profile schema validation,
mapping decisions, collision evidence, renderer output, comment-safe review
notes, GUI wording, and sanitized example behavior.

The release remains local-only and sanitized:

- No device connections.
- No command transmission.
- No credential storage.
- No private configs, logs, screenshots, or backups in the public tree.

