from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from wisprclone.config import Config

MAC_APP_DIR = Path.home() / "Library" / "Application Support" / "wisprclone"
MAC_CONFIG_PATH = MAC_APP_DIR / "config.json"


@dataclass
class MacConfig(Config):
    """Config with macOS-appropriate defaults. Overrides only the fields whose
    Windows defaults are wrong on Mac; everything else is inherited. The cpu/int8
    defaults are load-bearing: the transcriber fallback chain ends at
    ("base","cpu","int8"), so a cuda default would silently degrade Mac to base."""

    hotkey: str = "alt_r"          # Right Option — low-conflict push-to-talk
    model: str = "medium"          # large-v3 is too slow on CPU
    device: str = "cpu"            # no CUDA on macOS
    compute_type: str = "int8"

    @classmethod
    def load(cls, path: Path = MAC_CONFIG_PATH) -> "MacConfig":
        return super().load(path)

    def save(self, path: Path = MAC_CONFIG_PATH) -> None:
        super().save(path)
