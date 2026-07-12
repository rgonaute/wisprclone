from __future__ import annotations

from typing import Callable

# Permission name -> why WisprClone needs it (shown to the user).
_REASON = {
    "Accessibility": "paste transcribed text (synthetic Cmd+V)",
    "Input Monitoring": "detect the global push-to-talk hotkey",
}


def accessibility_ok() -> bool:
    """True if the process is trusted to post synthetic events (Accessibility)."""
    try:
        from ApplicationServices import AXIsProcessTrusted
        return bool(AXIsProcessTrusted())
    except Exception:
        return False


def input_monitoring_ok() -> bool:
    """True if the process may listen to the keyboard event tap (Input
    Monitoring). This is a DIFFERENT permission from Accessibility."""
    try:
        from Quartz import CGPreflightListenEventAccess
        return bool(CGPreflightListenEventAccess())
    except Exception:
        return False


def missing_permissions(accessibility: bool, input_monitoring: bool) -> list[str]:
    missing = []
    if not accessibility:
        missing.append("Accessibility")
    if not input_monitoring:
        missing.append("Input Monitoring")
    return missing


def permission_message(missing: list[str]) -> str:
    lines = ["WisprClone needs these macOS permissions to work:", ""]
    for name in missing:
        lines.append(f"  • {name} — to {_REASON[name]}")
    lines += [
        "",
        "Open System Settings → Privacy & Security, enable WisprClone under "
        "each item above, then relaunch WisprClone.",
    ]
    return "\n".join(lines)


def preflight(show_dialog: Callable[[str], None],
              ax_check: Callable[[], bool] = accessibility_ok,
              im_check: Callable[[], bool] = input_monitoring_ok) -> list[str]:
    """Check permissions; if any are missing, call show_dialog with an
    explanatory message. Returns the list of missing permission names."""
    missing = missing_permissions(ax_check(), im_check())
    if missing:
        show_dialog(permission_message(missing))
    return missing
