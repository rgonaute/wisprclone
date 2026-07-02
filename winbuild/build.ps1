# Build WisprClone-Setup.exe: clean venv -> PyInstaller -> Inno Setup.
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot   # repo root
Set-Location $root
$env:PYTHONPATH = $root   # so gen_version_info.py and the version read can import wisprclone (not pip-installed)

$venv = ".venv-build"
if (Test-Path $venv) { Remove-Item -Recurse -Force $venv }
py -3.14 -m venv $venv
$py = Join-Path $venv "Scripts\python.exe"

& $py -m pip install --upgrade pip
& $py -m pip install -r winbuild\requirements-build.txt

# Generate version resource + icon from the single-source version.
& $py winbuild\gen_version_info.py
& $py winbuild\make_icon.py

# Clean prior build output, then freeze.
if (Test-Path build) { Remove-Item -Recurse -Force build }
if (Test-Path dist)  { Remove-Item -Recurse -Force dist }
& $py -m PyInstaller --clean --noconfirm winbuild\wisprclone.spec

if (-not (Test-Path "dist\WisprClone\WisprClone.exe")) { throw "PyInstaller output missing" }

# Read version for the installer.
$ver = (& $py -c "import wisprclone; print(wisprclone.__version__)").Trim()

# Locate Inno Setup compiler (install if missing).
$iscc = Get-Command iscc -ErrorAction SilentlyContinue
if (-not $iscc) {
  $candidate = "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe"
  if (-not (Test-Path $candidate)) { winget install -e --id JRSoftware.InnoSetup --accept-source-agreements --accept-package-agreements }
  $iscc = $candidate
} else { $iscc = $iscc.Source }

& $iscc "/DVersion=$ver" winbuild\installer.iss

Write-Host "Built dist\WisprClone-Setup.exe"
