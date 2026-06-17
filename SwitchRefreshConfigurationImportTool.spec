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
                / "switch_refresh_config_import_tool"
                / "assets"
                / "generic_refresh_build_template.txt"
            ),
            "switch_refresh_config_import_tool/assets",
        ),
        (
            str(
                source_root
                / "switch_refresh_config_import_tool"
                / "assets"
                / "generic_existing_switch_config.txt"
            ),
            "switch_refresh_config_import_tool/assets",
        ),
    ],
    hiddenimports=["switch_refresh_config_import_tool.core"],
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
    name="SwitchRefreshConfigurationImportTool",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
)
