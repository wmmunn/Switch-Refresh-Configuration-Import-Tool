# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path


project_root = Path.cwd().resolve()
source_root = project_root / "src"

a = Analysis(
    [str(project_root / "run_app.py")],
    pathex=[str(source_root)],
    binaries=[],
    datas=[
        (
            str(
                source_root
                / "generic_lab_notes_extractor"
                / "assets"
                / "generic_baseline_lab_sheet.txt"
            ),
            "generic_lab_notes_extractor/assets",
        ),
        (
            str(
                source_root
                / "generic_lab_notes_extractor"
                / "assets"
                / "generic_sample_running_config.txt"
            ),
            "generic_lab_notes_extractor/assets",
        ),
    ],
    hiddenimports=["generic_lab_notes_extractor.core"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="GenericLabNotesExtractor",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
)
