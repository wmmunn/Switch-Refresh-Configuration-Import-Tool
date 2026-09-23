# Changelog

All notable changes to this project are documented here.

## Unreleased

- Global `vlan internal allocation policy` lines are no longer copied into the
  VLAN section; they are not VLAN database entries (`VLAN_DENYLIST`).
- When channel-group members are present but port-channel detection is disabled
  in the profile, the plan now warns and raises a review flag instead of
  flattening the bundle silently.
- Duplicate interface stanzas and unparseable interface declarations now raise
  a review flag, so the audit panel no longer reports a completely clean plan
  while the sheet contains a duplicated or malformed interface.
- Duplicate interface stanzas in the source config are now flagged and still
  rendered twice. The plan does not silently merge them; a warning names the
  duplicated interface so the operator can decide.
- Malformed parser blocks (`flagged_blocks`) now appear in the plan warnings
  instead of being collected and discarded.
- The management VLAN id written to `{{MGMT_VLAN}}` is now extracted correctly
  regardless of how the source config capitalises the SVI name (`Vlan900`,
  `VLAN900`, `VLan900`, and `Vlan 900` all yield `900`).
- VLAN SVIs and Port-channel parent interfaces are no longer staged as uplinks
  from description text. An SVI described "Uplink to Core" is recorded as
  ignored (`svi_not_translated`) instead of becoming a refresh uplink. SVIs
  that previously disappeared from the plan with no record are now listed as
  ignored. The port map and mapping engine share one role classification, so
  the faceplate matches the generated plan.
- Added an Interactive Port Map on the Target Build Planner for click-to-pair
  source and target ports, including a dedicated uplink cage.
- Port-channel members stay visible on the map and are no longer easy to
  confuse with uplink candidates.
- The planner now flags port-channel members that land on reserved uplink
  targets (`port_channel_on_uplink_target`).
- Unmapped second uplinks, collisions, and port-channel-on-uplink landings are
  shown on the map before Apply writes the pairs into the run profile.

## 1.1.0 - 2026-06-20

- Added the Target Build Planner workflow for profile-driven refresh planning.
- Added structured source parsing, profile schema loading, mapping engine
  planning, and renderer modules.
- Added target profile controls for access-port naming, mixed access layouts,
  stack member mapping, site-default uplink rules, and explicit uplink
  mappings.
- Added audit summary counts for collisions, unmapped interfaces, member
  shifts, and review flags.
- Added review evidence for mapping decisions, including symmetric collision
  groups and operator notes.
- Added Cisco comment-safe renderer output for warnings, review notes,
  collisions, and unmapped interfaces.
- Added safeguards for unsupported interface names, missing stack member
  mappings, non-identity stack remaps, malformed trunk syntax, and empty
  interface accounting.
- Clarified GUI wording so the legacy Extraction Workflow controls are
  distinguished from the Target Build Planner controls.
- Increased default GUI sizing and wrapping to avoid default-window truncation.
- Added expanded unit coverage for parser, schema, mapping, renderer, GUI
  wording, and sanitized distribution behavior.

## 1.0.0 - 2026-06-16

- Added the public sanitized Switch Refresh Configuration Import Tool.
- Added generic refresh build template and Cisco IOS existing-switch examples.
- Added local import logic for identity, management, VLAN, trunk, uplink,
  access-port, and RADIUS/dot1x details.
- Added operator-review guidance and conservative legacy-command cleanup.
- Added tests that verify placeholder coverage and sanitized generic content.
- Added a reproducible PyInstaller Windows build.
- Added project history documentation for regression tracking.
- Added local-only recovered source snapshots archive with SHA-256 manifest.
- Added explicit archive policy to prevent unarchived deletion of project
  artifacts.
- Added GitHub repository rename and public-release sanitization guidance.
