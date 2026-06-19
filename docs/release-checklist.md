# Public Release Checklist

Use this checklist before publishing a GitHub Release. The goal is to make the
public artifact unambiguous, repeatable, and free of local-only project
material.

## Release Inputs

- Confirm the release is built from the sanitized public source tree.
- Confirm tests pass against sanitized fixtures.
- Confirm the application launches from a clean extracted release folder.
- Confirm the generic sample files are present and selected as expected.
- Confirm no real configs, logs, screenshots, paths, credentials, or private
  archive material are included.

## Artifact Naming

Use an explicit public release filename:

```text
SwitchRefreshConfigurationImportTool-vX.Y.Z-windows-x64-PUBLIC.zip
```

Avoid uploading ambiguous working files from the parent project folder. The
release upload folder should contain only the public ZIP and its checksum file.

## Expected Windows ZIP Contents

The Windows release ZIP should contain only release-runtime material such as:

```text
SwitchRefreshConfigurationImportTool-vX.Y.Z-windows-x64/
|-- SwitchRefreshConfigurationImportTool.exe
|-- generic_existing_switch_config.txt
|-- generic_refresh_build_template.txt
|-- LICENSE.txt
|-- QUICK_START.txt
|-- RELEASE_NOTES_vX.Y.Z.md
`-- SHA256SUMS.txt
```

Do not include:

- Local notes.
- Private archive folders.
- Legacy source snapshots.
- Raw configs.
- Logs.
- Screenshots from real environments.
- Build folders unless they are intentionally part of the release runtime.
- Any file marked do not publish.

## Public Safety Scan

Before upload, inspect the ZIP file list and scan text files for local-only or
private markers. At minimum, check for:

- Local-only note filenames.
- Private archive folder names.
- Personal or work-environment paths.
- Legacy project names that should not appear in the public release.
- Credentials or credential-like strings.
- Non-documentation IP addressing.

Record the result in the release notes using precise wording, for example:

```text
Local public-release scan passed.
```

This statement means the local packaging scan passed. It is not a third-party
security certification.

## Checksum

Generate and record a SHA256 checksum for the uploaded ZIP.

The checksum in the GitHub release notes should match:

- The local checksum file.
- The checksum shown inside the release ZIP, when included.
- The GitHub asset digest, when GitHub displays one.

## GitHub Release Fields

Recommended fields:

```text
Tag: vX.Y.Z
Target: master
Release title: Switch Refresh Configuration Import Tool vX.Y.Z
Pre-release: No, unless the build is intentionally experimental
Set as latest release: Yes, for normal stable releases
```

Use hand-written release notes for initial or safety-sensitive releases. Do not
rely only on generated release notes when packaging and sanitization details
matter.

## Release Notes Safety Language

The release notes should clearly state:

- The package is built from the sanitized public version.
- The package contains generic sample input files only.
- No private configs, logs, paths, local notes, or archive material are
  included.
- The tool processes local text files only.
- The tool does not connect to devices or transmit commands.
- The SHA256 checksum of the public ZIP.

## Final Verification

After publishing:

1. Open the public release page.
2. Confirm the asset name includes `PUBLIC`.
3. Confirm the release is not marked as a pre-release unless intended.
4. Confirm the uploaded asset checksum matches the local checksum.
5. Download the public ZIP from GitHub and confirm it extracts cleanly.
6. Launch the EXE from the extracted folder.
7. Record any post-release findings in project history or a follow-up issue.

