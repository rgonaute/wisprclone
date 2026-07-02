"""Write a PyInstaller version resource (version_info.txt) from wisprclone.__version__."""
from pathlib import Path

import wisprclone

TEMPLATE = """\
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=({maj}, {min}, {pat}, 0),
    prodvers=({maj}, {min}, {pat}, 0),
    mask=0x3f, flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[
    StringFileInfo([StringTable('040904B0', [
      StringStruct('CompanyName', 'rgonaute'),
      StringStruct('FileDescription', 'WisprClone — offline dictation'),
      StringStruct('FileVersion', '{ver}'),
      StringStruct('InternalName', 'WisprClone'),
      StringStruct('OriginalFilename', 'WisprClone.exe'),
      StringStruct('ProductName', 'WisprClone'),
      StringStruct('ProductVersion', '{ver}')])]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
"""


def build(path) -> Path:
    maj, min_, pat = wisprclone.__version__.split(".")
    text = TEMPLATE.format(maj=maj, min=min_, pat=pat, ver=wisprclone.__version__)
    Path(path).write_text(text, encoding="utf-8")
    return Path(path)


if __name__ == "__main__":
    out = build(Path(__file__).with_name("version_info.txt"))
    print("wrote", out)
