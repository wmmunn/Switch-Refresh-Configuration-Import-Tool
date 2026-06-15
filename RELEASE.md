# Release Process

1. Update the version in `pyproject.toml`, `src/generic_lab_notes_extractor/app.py`,
   and `CHANGELOG.md`.
2. Run `python -m unittest discover -s tests -v`.
3. Build with `pyinstaller --noconfirm --clean GenericLabNotesExtractor.spec`.
4. Smoke-test the EXE using both files in `examples/`.
5. Generate a SHA-256 checksum.
6. Attach the EXE, checksum, and example inputs to a GitHub Release.

Generated binaries belong in GitHub Releases, not in source control.
