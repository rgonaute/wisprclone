from wisprclone_mac.notice import format_notice


def test_rewrites_ctrl_v_to_cmd_v():
    assert format_notice("Copied to clipboard — press Ctrl+V to paste.") == \
        "Copied to clipboard — press Cmd+V to paste."


def test_leaves_unrelated_text_untouched():
    assert format_notice("Settings saved.") == "Settings saved."
