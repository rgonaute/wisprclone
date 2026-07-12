from wisprclone_mac.permissions import (
    missing_permissions, permission_message, preflight,
)


def test_no_missing_when_all_granted():
    assert missing_permissions(True, True) == []


def test_lists_both_when_neither_granted():
    assert missing_permissions(False, False) == ["Accessibility", "Input Monitoring"]


def test_lists_only_input_monitoring():
    assert missing_permissions(True, False) == ["Input Monitoring"]


def test_message_names_missing_and_says_relaunch():
    msg = permission_message(["Accessibility"])
    assert "Accessibility" in msg
    assert "relaunch" in msg.lower()


def test_preflight_shows_dialog_and_returns_missing():
    shown = []
    missing = preflight(shown.append, ax_check=lambda: False, im_check=lambda: True)
    assert missing == ["Accessibility"]
    assert len(shown) == 1 and "Accessibility" in shown[0]


def test_preflight_is_silent_when_all_ok():
    shown = []
    missing = preflight(shown.append, ax_check=lambda: True, im_check=lambda: True)
    assert missing == []
    assert shown == []
