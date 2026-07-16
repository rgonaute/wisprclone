# WisprClone macOS Manual Smoke Checklist

Run on an Apple Silicon Mac. CI cannot cover TCC/mic/paste — this is that gate.

## From source (do this first)
1. `python3 -m venv .venv && source .venv/bin/activate`
2. `pip install -r requirements-mac.txt`
3. `python -m wisprclone_mac`
4. On first launch a permissions dialog lists Accessibility + Input Monitoring.
   For from-source runs the TCC entry to enable is your TERMINAL app (Terminal,
   iTerm, or python) — not "WisprClone"; only the packaged .app build appears
   as WisprClone. Grant both in System Settings -> Privacy & Security (and
   Microphone when prompted), then relaunch.
5. Tray dot icon appears. From source a Dock icon is normal; only the .app
   build (step 14) hides it.
6. Copy some text first — the clipboard-restore check below is deterministic
   only for text (restore is skipped by design when the previous clipboard
   content is non-text, e.g. an image or file). Hold Right Option, speak
   English -> text pastes into the focused app; the previous clipboard is
   restored afterward.
7. Repeat in Hebrew (tray Language -> Hebrew or Auto) -> Hebrew pastes correctly
   (verifies NSPasteboard Unicode).
8. Turn OFF Accessibility (from source: toggle your terminal app's entry, per
   step 4), dictate -> you get a "Copied to clipboard — press Cmd+V to paste."
   notice and the text is on the clipboard (NOT lost). Re-grant.
   Caveat: tray toasts (QSystemTrayIcon.showMessage) may not render at all for
   unsigned/from-source apps on macOS — the text still lands on the clipboard,
   so do not read a missing toast alone as a failure.
9. Launch a second `python -m wisprclone_mac` -> it exits immediately (single
   instance); no double paste.
10. Settings: change model/mic/hotkey, Save -> persists across restart
    (`~/Library/Application Support/wisprclone/config.json`).

## Packaged .app / .dmg

One-time setup before building: create a code-signing certificate named exactly
`WisprClone Self-Signed` in Keychain Access (login keychain, Certificate
Assistant -> Create a Certificate -> type "Code Signing"), or export
`WISPRCLONE_CODESIGN_ID=<your identity>`. Without it build.sh falls back to
ad-hoc signing, so TCC permissions re-prompt on every rebuild and step 15
fails by design.

11. `bash macbuild/build.sh` -> produces `dist/WisprClone.dmg`.
12. Open the .dmg, drag WisprClone to Applications. First launch: right-click ->
    Open, or System Settings -> Privacy & Security -> Open Anyway (unsigned).
13. Grant Accessibility + Input Monitoring + Microphone; relaunch.
14. Repeat steps 6-10 against the installed .app. Confirm NO Dock icon
    (LSUIElement) and the mic prompt shows the usage string.
15. Rebuild with `build.sh` and relaunch -> permissions are NOT re-prompted
    (confirms the stable self-signed identity + fixed bundle id).
