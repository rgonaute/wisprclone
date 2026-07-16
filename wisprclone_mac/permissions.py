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


def request_accessibility() -> None:
    """Ask macOS for Accessibility trust with the system prompt enabled. This
    registers the app in the Accessibility TCC pane (so the user can toggle it
    instead of hunting for the '+' button) and may show Apple's own dialog."""
    try:
        from ApplicationServices import (
            AXIsProcessTrustedWithOptions, kAXTrustedCheckOptionPrompt,
        )
        AXIsProcessTrustedWithOptions({kAXTrustedCheckOptionPrompt: True})
    except Exception:
        pass


def request_input_monitoring() -> None:
    """Ask macOS for Input Monitoring access. Registers the app in the Input
    Monitoring TCC pane and may show the system prompt."""
    try:
        from Quartz import CGRequestListenEventAccess
        CGRequestListenEventAccess()
    except Exception:
        pass


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
              im_check: Callable[[], bool] = input_monitoring_ok,
              ax_request: Callable[[], None] = request_accessibility,
              im_request: Callable[[], None] = request_input_monitoring,
              ) -> list[str]:
    """Check permissions; for each missing one, ask macOS to request it (which
    registers the app in the TCC panes and may show the system prompt), then
    call show_dialog with an explanatory message. Returns the list of missing
    permission names."""
    missing = missing_permissions(ax_check(), im_check())
    requests = {"Accessibility": ax_request, "Input Monitoring": im_request}
    for name in missing:
        try:
            requests[name]()
        except Exception:
            pass  # the request is best-effort; the dialog below still guides
    if missing:
        show_dialog(permission_message(missing))
    return missing
