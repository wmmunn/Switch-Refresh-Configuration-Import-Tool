# Changelog

All notable changes to this project are documented here.

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
