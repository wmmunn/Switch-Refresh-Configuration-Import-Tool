# Release Process

## GitHub Repository Rename

Preferred public repository name:

`switch-refresh-config-import-tool`

Before pushing a public release, confirm the GitHub repository name, README,
package name, EXE name, release ZIP names, and release notes all use the
Switch Refresh Configuration Import Tool identity.

GitHub redirects old repository URLs after a rename, but release notes should
still mention the rename briefly for clarity.

## Build And Publish

1. Update the version in `pyproject.toml`,
   `src/switch_refresh_config_import_tool/app.py`, and `CHANGELOG.md`.
2. Run `python -m unittest discover -s tests -v`.
3. Build with `pyinstaller --noconfirm --clean SwitchRefreshConfigurationImportTool.spec`.
4. Smoke-test the EXE using both files in `examples/`.
5. Generate a SHA-256 checksum.
6. Attach the EXE, checksum, and example inputs to a GitHub Release.

## Sanitization Check

Before publishing:

- Scan the public tree for personal names, workstation paths, credentials,
  private network ranges, raw configs, and internal-only archive material.
- Confirm `source-snapshots` is not included in public release ZIPs.
- Confirm any local-only archive remains outside the GitHub-ready tree.

Generated binaries belong in GitHub Releases, not in source control.
