# Generic Lab Notes Extractor

A local Windows GUI that extracts reusable Cisco IOS switch details from a
running-config and inserts them into an operator-reviewed lab sheet.

The public edition ships only with fictional sample data. It does not connect
to network devices, transmit commands, or require credentials.

## Features

- Extracts hostname, VTP domain, management addressing, VLANs, trunks, likely
  uplinks, access-port blocks, and RADIUS/dot1x status.
- Keeps generated output gated by operator review.
- Uses a bundled generic lab-sheet template and sample running-config.
- Processes files locally.
- Runs with standard Tkinter; `ttkbootstrap` is optional.

## Repository Layout

```text
.
|-- examples/                         # Generic input files
|-- src/generic_lab_notes_extractor/  # Application source and bundled assets
|-- tests/                            # Sanitization and extraction tests
|-- .github/workflows/tests.yml       # Public CI
|-- GenericLabNotesExtractor.spec     # Windows EXE build recipe
|-- pyproject.toml
|-- LICENSE
`-- README.md
```

## Quick Start

Python 3.10 or newer is required.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .[theme]
generic-lab-notes-extractor
```

The application starts with these generic inputs selected:

- `examples/generic_sample_running_config.txt`
- `examples/generic_baseline_lab_sheet.txt`

Choose an output path, run extraction, and review the generated text before
using any portion of it.

## Run Tests

```powershell
python -m unittest discover -s tests -v
```

## Build The Windows EXE

```powershell
python -m pip install -e .[build,theme]
pyinstaller --noconfirm --clean GenericLabNotesExtractor.spec
```

The executable is written to `dist/GenericLabNotesExtractor.exe`. Publish the
binary through a GitHub Release rather than committing it to the repository.

## Sanitized Examples

The sample config uses names prefixed with `DEMO` and IP addresses from the
RFC documentation ranges:

- `192.0.2.0/24`
- `198.51.100.0/24`
- `203.0.113.0/24`

Do not submit real customer configs, credentials, logs, screenshots, or
production addressing in issues or pull requests.

## Safety

Generated output is review material, not an approved device configuration.
Confirm interface mappings, VLAN scope, uplinks, management addressing,
authentication behavior, and every line marked for review.

Cisco and Cisco IOS are trademarks of Cisco Systems, Inc. This project is
independent and is not affiliated with or endorsed by Cisco.

## License

MIT License. See [LICENSE](LICENSE).
