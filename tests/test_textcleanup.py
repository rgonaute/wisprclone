from wisprclone.textcleanup import clean_text


def test_strips_bracketed_noise_tags():
    assert clean_text("hello [BLANK_AUDIO] world") == "hello world"
    assert clean_text("hi (music) there") == "hi there"


def test_strips_nospeech_token():
    assert clean_text("text <|nospeech|> more") == "text more"


def test_collapses_whitespace():
    assert clean_text("a    b\n\nc") == "a b c"


def test_fillers_removed_when_enabled():
    assert clean_text("so um this uh works", remove_fillers=True) == "so this works"


def test_fillers_kept_when_disabled():
    assert clean_text("so um this works", remove_fillers=False) == "so um this works"


def test_space_before_punctuation_fixed_when_fillers_enabled():
    assert clean_text("hello um , world", remove_fillers=True) == "hello, world"


def test_hebrew_passes_through_unchanged():
    hebrew = "שלום עולם מה שלומך"
    assert clean_text(hebrew) == hebrew


def test_trims_and_returns_empty_for_noise_only():
    assert clean_text("  [SILENCE]  ") == ""
