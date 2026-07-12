# -*- mode: python ; coding: utf-8 -*-
import os

from PyInstaller.utils.hooks import collect_data_files

# PyInstaller resolves relative paths against the spec dir (SPECPATH), not cwd.
here = SPECPATH                  # …/macbuild
repo = os.path.dirname(here)     # repo root: holds wisprclone/ and wisprclone_mac/

datas = collect_data_files("faster_whisper")  # Silero VAD asset, etc.

a = Analysis(
    [os.path.join(here, "entry.py")],
    pathex=[repo],
    binaries=[],
    datas=datas,
    hiddenimports=["hf_xet"],
    excludes=["onnxruntime", "pytest", "tkinter"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [], exclude_binaries=True,
    name="WisprClone", console=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="WisprClone")
app = BUNDLE(
    coll,
    name="WisprClone.app",
    icon=None,
    bundle_identifier="com.wisprclone.mac",
    info_plist={
        "LSUIElement": True,                       # menu-bar/tray-only agent
        "NSMicrophoneUsageDescription":
            "WisprClone records your voice to transcribe it into text.",
        "LSMinimumSystemVersion": "12.0",
        "CFBundleShortVersionString": "1.0.0",
        "CFBundleVersion": "1.0.0",
    },
)
