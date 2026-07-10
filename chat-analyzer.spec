# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller onefile spec for the Chat Analyzer launcher.

Build:  pyinstaller chat-analyzer.spec
Output: dist/ChatAnalyzer  (a single self-contained executable)

Entry point is ``launcher.py``. The whole pure-stdlib pipeline is bundled as
data + hidden imports so the frozen binary can import ``main``, the ``src``
package, and the two build scripts. matplotlib/numpy are excluded on purpose —
the launcher always analyses with ``skip_visualizations=True``.
"""

from PyInstaller.utils.hooks import collect_submodules, collect_data_files

block_cipher = None

# Bundle the code that the launcher imports at runtime. main.py / build_*.py sit
# at the repo root (not importable as a package by folder), so ship them as data
# AND declare them as hidden imports; PyInstaller adds _MEIPASS to sys.path.
datas = [
    ("main.py", "."),
    ("build_dashboard.py", "."),
    ("build_connected.py", "."),
    ("build_insights.py", "."),
    ("assets/echarts.min.js", "assets"),
] + collect_data_files("tzdata")  # zoneinfo files reached via importlib.resources

hiddenimports = (
    ["main", "build_dashboard", "build_connected", "build_insights", "tzdata"]
    + collect_submodules("src")
    + collect_submodules("tzdata")
)

a = Analysis(
    ["launcher.py"],
    pathex=["."],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["matplotlib", "numpy", "PIL", "pandas", "scipy", "tkinter"],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="ChatAnalyzer",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
