#!/usr/bin/env bash
# Build WisprClone.app + WisprClone.dmg on Apple Silicon macOS.
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo="$(dirname "$here")"
cd "$repo"

venv=".venv-build-mac"
rm -rf "$venv"
python3 -m venv "$venv"
py="$venv/bin/python"

"$py" -m pip install --upgrade pip
"$py" -m pip install -r macbuild/requirements-build-mac.txt

rm -rf build dist
"$py" -m PyInstaller --clean --noconfirm macbuild/wisprclone-mac.spec

test -d "dist/WisprClone.app" || { echo "PyInstaller output missing"; exit 1; }

# Stable self-signed identity so TCC (Accessibility/Input Monitoring/Mic) grants
# survive rebuilds. Create it once in Keychain Access (login keychain) as a
# code-signing certificate named exactly "WisprClone Self-Signed", or override
# via WISPRCLONE_CODESIGN_ID. Falls back to ad-hoc "-" (permissions re-prompt
# every build) so the build still succeeds without a cert.
identity="${WISPRCLONE_CODESIGN_ID:-WisprClone Self-Signed}"
if security find-identity -v -p codesigning | grep -q "$identity"; then
  sign="$identity"
else
  echo "WARNING: signing identity '$identity' not found; using ad-hoc (-)." >&2
  echo "         TCC permissions will re-prompt on every rebuild." >&2
  sign="-"
fi
# No --options runtime: Hardened Runtime denies audio input without a
# com.apple.security.device.audio-input entitlement and can reject the bundled
# Python dylibs under library validation; it only matters for notarization,
# which a self-signed app cannot get anyway.
codesign --force --deep --sign "$sign" "dist/WisprClone.app"

# Build the .dmg with hdiutil (no create-dmg/Homebrew dependency).
rm -f dist/WisprClone.dmg
staging="$(mktemp -d)"
cp -R "dist/WisprClone.app" "$staging/"
ln -s /Applications "$staging/Applications"
hdiutil create -volname "WisprClone" -srcfolder "$staging" -ov \
  -format UDZO "dist/WisprClone.dmg"
rm -rf "$staging"

echo "Built dist/WisprClone.dmg"
echo "Unsigned/self-signed: first launch, open via System Settings ->"
echo "Privacy & Security -> Open Anyway, then grant Accessibility, Input"
echo "Monitoring, and Microphone, and relaunch."
