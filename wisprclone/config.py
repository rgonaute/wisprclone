from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path

APP_DIR = Path(os.environ.get("APPDATA", str(Path.home()))) / "wisprclone"
CONFIG_PATH = APP_DIR / "config.json"


@dataclass
class Config:
    hotkey: str = "ctrl_r"
    trigger_mode: str = "hold"          # "hold" | "toggle"
    input_device: str | None = None     # None = system default input
    model: str = "large-v3"             # multilingual only
    device: str = "cuda"                # "cuda" | "cpu"
    compute_type: str = "float16"       # "float16" | "int8"
    language: str = "auto"              # "auto" | "en" | "he"
    vocab_hint: str = ""
    remove_fillers: bool = False        # English-only filler removal
    auto_paste: bool = True
    history_cap: int = 100

    @classmethod
    def load(cls, path: Path = CONFIG_PATH) -> "Config":
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
            known = {k: data[k] for k in cls.__dataclass_fields__ if k in data}
            return cls(**known)
        except (FileNotFoundError, json.JSONDecodeError, TypeError, ValueError):
            return cls()

    def save(self, path: Path = CONFIG_PATH) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(asdict(self), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
