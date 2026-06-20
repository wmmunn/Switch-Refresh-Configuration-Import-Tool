# Roadmap

This roadmap is intentionally conservative. The v1.0.0 release remains the
sanitized public baseline for the original Extraction Workflow, and v1.1.0 adds
the Target Build Planner while preserving the local-only, operator-reviewed
safety model.

## Current Baseline

Version 1.1.0 provides a local Windows GUI with two workflows:

- Extraction Workflow: imports selected values from an existing Cisco IOS
  switch configuration into a reviewable refresh build template.
- Target Build Planner: applies a user-owned target profile to source parser
  output and renders a reviewable new switch build sheet.

It ships with fictional examples only and does not connect to network devices.

## Near-Term Priorities

1. Preserve v1.0.0 behavior as the stable Extraction Workflow baseline.
2. Track post-release validation findings using sanitized examples.
3. Keep release packaging repeatable and unambiguous.
4. Keep documentation clear for first-time users.
5. Keep new parser behavior narrow, tested, and documented with sanitized
   fixtures.
6. Avoid adding hard-coded site assumptions outside explicit target profiles.

## Delivered v1.1 Work

- Target Build Planner workflow.
- Structured source parser, profile schema, mapping engine, and renderer.
- Audit panel for collisions, unmapped interfaces, member shifts, and flags.
- Target profile controls for access naming, stack mapping, and uplinks.
- Comment-safe renderer output for operator notes and warnings.
- Expanded tests for engine, renderer, GUI wording, and sanitized behavior.

Import report clarity is not an immediate rewrite target. Revisit it if field
testing shows confusion about imported values, skipped values, or
review-required sections.

## Target Build Planner Direction

The Target Build Planner lets users define environment-specific import rules
without hard-coding those rules into Python logic. Supported or planned rule
families include:

- Site-specific uplink standards.
- Site-specific port-channel handling.
- Access-port preservation options.
- Trunk allowed VLAN import behavior.
- Shutdown-state review requirements.
- Management interface or SVI import rules.
- Port-offset-aware stack member consolidation (mapping multiple smaller old members onto port sub-ranges within one larger new member, rather than 1:1 by member ID only).

The planner should suggest and stage values, not silently approve them.
Uplinks, port-channels, trunk allowed VLAN lists, management addressing,
shutdown state, and authentication-related settings should remain
operator-reviewed.

See [`profile-engine-design-notes.md`](profile-engine-design-notes.md) for the
current design notes.

Fixture intake and promotion rules are documented in
[`fixture-strategy.md`](fixture-strategy.md).

The older working schema draft remains in
[`profile-schema-draft.md`](profile-schema-draft.md); current implementation
details are in [`profile-engine-design-notes.md`](profile-engine-design-notes.md).

## Larger v2.0 Possibility

If configurable profiles grow into a broader translation framework, future work
should be treated as a v2.0 effort rather than a minor parser enhancement. A
v2.0 direction would likely include:

- A documented profile schema.
- Profile validation with clear warnings.
- Structured parser decisions for GUI and report rendering.
- Sanitized fixture coverage for each supported rule type.
- A clearer separation between parser logic, profile rules, GUI presentation,
  and file I/O.
