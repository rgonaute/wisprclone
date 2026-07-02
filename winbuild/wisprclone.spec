# -*- mode: python ; coding: utf-8 -*-
import os

from PyInstaller.utils.hooks import collect_data_files
import nvidia  # provided by nvidia-cublas-cu12 / nvidia-cudnn-cu12

# Bundle the CUDA DLLs, preserving nvidia/<lib>/bin layout so
# cuda_paths.ensure_cuda_on_path() finds them via sys._MEIPASS at runtime.
cuda_binaries = []
for base in list(nvidia.__path__):
    for sub in ("cublas", "cudnn"):
        bindir = os.path.join(base, sub, "bin")
        if os.path.isdir(bindir):
            for fn in os.listdir(bindir):
                if fn.lower().endswith(".dll") and fn.lower() != "nvblas64_12.dll":
                    cuda_binaries.append((os.path.join(bindir, fn), f"nvidia/{sub}/bin"))

datas = collect_data_files("faster_whisper")  # Silero VAD asset, etc.

a = Analysis(
    ['winbuild/entry.py'],
    pathex=['.'],
    binaries=cuda_binaries,
    datas=datas,
    hiddenimports=['hf_xet'],
    excludes=['onnxruntime', 'pytest', 'tkinter'],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [], exclude_binaries=True,
    name='WisprClone', console=False,
    icon='winbuild/wisprclone.ico', version='winbuild/version_info.txt',
)
coll = COLLECT(exe, a.binaries, a.datas, name='WisprClone')
