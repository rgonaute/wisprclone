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


def test_preflight_requests_each_missing_permission():
    calls = []
    preflight(lambda msg: None,
              ax_check=lambda: False, im_check=lambda: False,
              ax_request=lambda: calls.append("ax"),
              im_request=lambda: calls.append("im"))
    assert calls == ["ax", "im"]


def test_preflight_requests_only_the_missing_permission():
    calls = []
    preflight(lambda msg: None,
              ax_check=lambda: True, im_check=lambda: False,
              ax_request=lambda: calls.append("ax"),
              im_request=lambda: calls.append("im"))
    assert calls == ["im"]


def test_preflight_makes_no_requests_when_all_granted():
    calls = []
    preflight(lambda msg: None,
              ax_check=lambda: True, im_check=lambda: True,
              ax_request=lambda: calls.append("ax"),
              im_request=lambda: calls.append("im"))
    assert calls == []


def test_preflight_swallows_request_errors_and_still_shows_dialog():
    shown = []

    def boom():
        raise RuntimeError("pyobjc missing")

    missing = preflight(shown.append,
                        ax_check=lambda: False, im_check=lambda: False,
                        ax_request=boom, im_request=boom)
    assert missing == ["Accessibility", "Input Monitoring"]
    assert len(shown) == 1 and "Accessibility" in shown[0]
