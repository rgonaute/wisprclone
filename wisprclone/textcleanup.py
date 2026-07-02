import re

_NOISE_TERMS = (
    "BLANK_AUDIO|SILENCE|music|applause|laughter|laughing|noise|inaudible|"
    "indistinct|coughing|cough|breathing|inhale|exhale|sigh|sighs|wind|static|"
    "background noise|unintelligible"
)
_NOISE_TAGS = re.compile(r"[\[\(]\s*(?:" + _NOISE_TERMS + r")\s*[\]\)]", re.IGNORECASE)
_NOSPEECH = re.compile(r"<\|nospeech\|>")
_FILLERS = re.compile(
    r"(?i)(^|[\s,.;:!?])(?:uh+|um+|umm+|uhm+|erm+|hmm+)(?=$|[\s,.;:!?])[,.;:!?]?"
)
_SPACE_BEFORE_PUNCT = re.compile(r"\s+([,.;:!?])")
_MULTISPACE = re.compile(r"\s+")


def clean_text(raw: str, remove_fillers: bool = False) -> str:
    text = _NOSPEECH.sub(" ", raw)
    text = _NOISE_TAGS.sub(" ", text)
    if remove_fillers:
        text = _FILLERS.sub(r"\1", text)
        text = _SPACE_BEFORE_PUNCT.sub(r"\1", text)
    text = _MULTISPACE.sub(" ", text)
    return text.strip()
