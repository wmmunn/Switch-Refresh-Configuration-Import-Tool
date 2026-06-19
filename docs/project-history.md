# Project History

This document preserves the project-level history behind Switch Refresh
Configuration Import Tool. It is intentionally broader than `CHANGELOG.md`.
Use it when investigating regressions, tracing behavior back to an earlier
iteration, or explaining why the tool has its current safety boundaries.

No private configs, customer names, raw operational logs, screenshots, or
credential material should be added here. Use sanitized examples only.

## Current Name

**Switch Refresh Configuration Import Tool**

Tagline:

> Import selected values from an existing switch configuration into a
> reviewable refresh build template.

The name was chosen because the tool does not blindly migrate a full
configuration. It imports selected, parser-confirmed values from an existing
switch config into a prepared template that an operator must review.

## Lineage Summary

The project began as an internal Labsheet Extraction Tool that read an old
Cisco IOS switch running-config and applied parser output to a prepared build
worksheet. The public edition keeps the useful extraction behavior while
removing private examples, internal naming, and customer-specific assumptions.

The public version is now packaged as a small GitHub-style project with:

- source code under `src/`
- sanitized examples under `examples/`
- repeatable tests under `tests/`
- a PyInstaller build recipe
- release and security documentation
- a Windows release bundle

Source snapshots that still existed after recovery are preserved locally outside
the GitHub-ready public tree because exact legacy files may contain non-public
attribution or internal lineage details.

## Revision Trail

### Internal Extractor Lineage

The internal version established the core behavior:

- Read a local existing-switch running-config.
- Parse switch identity, management addressing, VLAN database entries, trunk
  allowed VLAN statements, likely uplinks, and access-port blocks.
- Convert older physical access interface names into a target-platform prefix.
- Remove or flag older interface commands that should not be blindly reused.
- Detect RADIUS/dot1x configuration before preserving dot1x access-port lines.
- Apply extracted values to placeholders in a prepared template.

Known behavior worth preserving during regression work:

- Generated output is review material, not an approved device configuration.
- Uplink candidates are ranked conservatively by source order and description.
- Legacy dot1x interface lines are stripped when no supporting RADIUS evidence
  is present.
- Unsupported or review-sensitive lines are marked instead of silently copied.

### GUI Refresh

The internal GUI was updated from a plain utility window into a clearer workflow:

- file selection for existing config, template, and output
- target access-port prefix selector
- operator-review guidance in the main window
- placeholder/reference guidance
- output-opening controls
- optional `ttkbootstrap` styling with Tkinter fallback

Regression watch points:

- The tool must remain usable without `ttkbootstrap`.
- File processing must stay local.
- Template and output selection must remain explicit.

### Sanitized Public Build

A shareable sanitized edition was created with generic assets:

- `generic_refresh_build_template.txt`
- `generic_existing_switch_config.txt`

The generic existing-switch config uses RFC documentation IP ranges only:

- `192.0.2.0/24`
- `198.51.100.0/24`
- `203.0.113.0/24`

Tests were added to verify:

- every supported placeholder exists in the bundled template
- generic examples do not include private network ranges used by real sites
- extraction fills representative identity, management, VLAN, access-port, and
  RADIUS/dot1x fields

Regression watch points:

- Do not replace sanitized examples with real configs.
- Do not add credentials, private addressing, ticket numbers, or customer names.
- Keep the example config realistic enough to exercise parser behavior.

### Public Repository Structure

The public edition was reshaped into a conventional repository layout:

- `README.md`
- `CHANGELOG.md`
- `LICENSE`
- `CONTRIBUTING.md`
- `SECURITY.md`
- `RELEASE.md`
- `.github/workflows/tests.yml`
- `pyproject.toml`
- `MANIFEST.in`
- `SwitchRefreshConfigurationImportTool.spec`
- `src/switch_refresh_config_import_tool/`
- `examples/`
- `tests/`

The Windows executable is treated as a release artifact and should not be
committed to the source repository.

### Rename From Lab Notes Extractor

The public-facing name changed from a lab-notes/extractor identity to:

**Switch Refresh Configuration Import Tool**

Reasoning:

- "Switch Refresh" describes the operational context.
- "Configuration Import" describes the action without implying full automated
  conversion.
- "Tool" keeps the name practical.
- The tagline clarifies that output lands in a reviewable refresh build
  template.

Regression watch points:

- Avoid old public names such as `GenericLabNotesExtractor`.
- Avoid internal names such as `lab_notes_extractor_sanitized`.
- Keep package/module names aligned with
  `switch_refresh_config_import_tool`.

### Recovery Audit After Cleanup

During cleanup, old root-level source files were deleted after the code was
carried into the renamed package. This was too aggressive for regression
tracking.

A recovery audit found exact legacy source copies in the workspace archive for:

- v3
- v4
- v5
- v6
- v7
- v8
- v9 radius
- v11
- v12

Those files were moved into a local-only archive with SHA-256 hashes. The
current renamed v1.0.0 package source was also copied there.

Afterward, a user-provided `earliest project file archive` folder was added to
the project root. Its v3/v5 Python sources matched the recovered copies already
archived, and its v3 spec file was added to `legacy-v3/`.

Known gap:

- An exact standalone `GenericLabNotesExtractor` source snapshot was not
  recoverable after cleanup. Its behavior survives in the current renamed
  source, but the deleted intermediate file should be treated as missing rather
  than reconstructed.

Public-release note:

- Exact legacy source snapshots are for local regression tracking only unless each file is separately sanitized and approved for publication.

Regression rule going forward:

- Archive exact source snapshots before deleting, renaming, packaging, or
  flattening project files.
- Follow `docs/archive-policy.md`: do not delete documents, code, EXE files,
  ZIP files, specs, or history notes unless an archived copy and hash/provenance
  record already exist.

## Supported Placeholders

The current public template supports:

- `{{HOSTNAME}}`
- `{{VTP_DOMAIN}}`
- `{{MGMT_VLAN}}`
- `{{MGMT_IP}}`
- `{{MGMT_MASK}}`
- `{{DEFAULT_GATEWAY}}`
- `{{VLAN_LIST}}`
- `{{TRUNK_ALLOWED_VLANS}}`
- `{{UPLINK_TRUNK_1}}`
- `{{UPLINK_TRUNK_2}}`
- `{{UPLINK_TRUNK_3}}`
- `{{UPLINK_TRUNK_4}}`
- `{{ACCESS_PORT_CONFIGS}}`
- `{{RADIUS_STATUS}}`

## Safety Boundaries

- Do not connect to devices.
- Do not transmit configuration commands.
- Do not store credentials.
- Do not include private configs or private examples.
- Do not weaken operator review.
- Do not silently copy unsupported legacy commands into build output.
- Do not preserve dot1x interface lines unless supporting RADIUS/dot1x
  infrastructure is detected.

## Regression Checklist

When changing parser or GUI behavior, verify:

- `python -m unittest discover -s tests -v` passes.
- The GUI starts with both bundled generic inputs selected.
- The EXE build embeds both generic input files.
- Old public names do not reappear in source or release artifacts.
- The release bundle includes the EXE, examples, README, quick start, license,
  and checksum.
- Generated output still requires operator review.

## Post-Release Validation

After the v1.0.0 public release, the import workflow was tested against five
additional private work-environment running-configs. The workflow completed
successfully in those tests, with no runtime failures or immediate parser
regressions observed.

This validation note is intentionally high-level. Private source configs,
environment identifiers, and operational details are not included in the public
project history.

