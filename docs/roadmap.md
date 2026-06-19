# Roadmap

This roadmap is intentionally conservative. The v1.0.0 release is the sanitized
public baseline, and future work should preserve the tool's local-only,
operator-reviewed safety model.

## Current Baseline

Version 1.0.0 provides a local Windows GUI that imports selected values from an
existing Cisco IOS switch configuration into a reviewable refresh build
template. It ships with fictional examples only and does not connect to network
devices.

## Near-Term Priorities

1. Preserve v1.0.0 as the stable public baseline.
2. Track post-release validation findings using sanitized examples.
3. Keep release packaging repeatable and unambiguous.
4. Keep documentation clear for first-time users.
5. Keep new parser behavior narrow, tested, and documented with sanitized
   fixtures.
6. Avoid adding more hard-coded site assumptions before the profile design is
   settled.

## Candidate v1.1 Work

- Clearer generated import report.
- Additional review flags for high-risk values.
- Interface-name normalization helpers and tests.
- Better explanation of likely uplink and trunk detection.
- Documentation updates based on field testing.
- Initial profile-engine scaffold if the scope remains small and review-gated.

Import report clarity is not an immediate rewrite target. Revisit it if field
testing shows confusion about imported values, skipped values, or
review-required sections.

## Profile Engine Direction

A future profile engine may let users define environment-specific import rules
without hard-coding those rules into Python logic. Possible rules include:

- Site-specific uplink standards.
- Site-specific port-channel handling.
- Access-port preservation options.
- Trunk allowed VLAN import behavior.
- Shutdown-state review requirements.
- Management interface or SVI import rules.

The profile engine should suggest and stage values, not silently approve them.
Uplinks, port-channels, trunk allowed VLAN lists, management addressing,
shutdown state, and authentication-related settings should remain
operator-reviewed.

See [`profile-engine-design-notes.md`](profile-engine-design-notes.md) for the
current design notes.

## Larger v2.0 Possibility

If configurable profiles become a broad translation framework, the work should
be treated as a v2.0 effort rather than a minor parser enhancement. A v2.0
direction would likely include:

- A documented profile schema.
- Profile validation with clear warnings.
- Structured parser decisions for GUI and report rendering.
- Sanitized fixture coverage for each supported rule type.
- A clearer separation between parser logic, profile rules, GUI presentation,
  and file I/O.
