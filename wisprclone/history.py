from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass
class HistoryEntry:
    text: str
    timestamp: str      # ISO 8601
    duration: float
    language: str
    model: str


class HistoryStore:
    def __init__(self, path: Path, cap: int = 100):
        self.path = Path(path)
        self.cap = cap
        self.entries: list[HistoryEntry] = self._load()

    def _load(self) -> list[HistoryEntry]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return [HistoryEntry(**e) for e in data]
        except (FileNotFoundError, json.JSONDecodeError, TypeError, ValueError):
            return []

    def add(self, entry: HistoryEntry) -> None:
        self.entries.insert(0, entry)
        del self.entries[self.cap:]
        self._save()

    def clear(self) -> None:
        self.entries = []
        self._save()

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps([asdict(e) for e in self.entries], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
