# Archive Policy

This project preserves working history for regression tracking. Do not delete
or overwrite project artifacts without first archiving them.

## Applies To

Archive before removing, renaming, replacing, or flattening:

- source code
- tests
- documentation
- templates
- examples
- spec/build files
- release folders
- EXE files
- ZIP files
- notes that explain behavior, assumptions, or revision history

## Required Before Cleanup

Before deleting or replacing project artifacts:

1. Copy the current artifact into an appropriate archive folder.
2. Preserve the original filename when it has historical value.
3. Record the source/provenance of the archived artifact.
4. Update or create a SHA-256 manifest.
5. Update `docs/project-history.md` when the change affects project lineage.
6. Only then remove or rename the working copy.

## Archive Locations

Source snapshots:

- local-only archives outside the GitHub-ready source tree

Historical notes and supporting records:

- `docs/archive/`

Exact legacy source snapshots are not automatically public-release material.
Before including any historical source snapshot in a GitHub-ready tree or
release, scan it for personal names, workstation paths, private network data,
credentials, raw configs, and internal-only context.

User-provided recovery material may also exist outside the public repository.
Do not modify or delete those folders unless the user explicitly asks for that
exact action.

## Non-Negotiable Rule

Do not "clean up" by deleting documents, code, EXE files, ZIP files, specs, or
history notes unless an archived copy already exists and the archive record has
been updated.

When in doubt, archive first.
