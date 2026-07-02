from wisprclone.history import HistoryEntry, HistoryStore


def _entry(text):
    return HistoryEntry(text=text, timestamp="2026-07-02T10:00:00",
                        duration=1.0, language="en", model="large-v3")


def test_add_prepends_newest_first(tmp_path):
    store = HistoryStore(tmp_path / "h.json")
    store.add(_entry("first"))
    store.add(_entry("second"))
    assert [e.text for e in store.entries] == ["second", "first"]


def test_cap_prunes_oldest(tmp_path):
    store = HistoryStore(tmp_path / "h.json", cap=2)
    for t in ["a", "b", "c"]:
        store.add(_entry(t))
    assert [e.text for e in store.entries] == ["c", "b"]


def test_persistence_roundtrip(tmp_path):
    p = tmp_path / "h.json"
    HistoryStore(p).add(_entry("שלום"))
    reloaded = HistoryStore(p)
    assert reloaded.entries[0].text == "שלום"


def test_clear(tmp_path):
    p = tmp_path / "h.json"
    store = HistoryStore(p)
    store.add(_entry("x"))
    store.clear()
    assert store.entries == []
    assert HistoryStore(p).entries == []


def test_corrupt_file_loads_empty(tmp_path):
    p = tmp_path / "h.json"
    p.write_text("garbage", encoding="utf-8")
    assert HistoryStore(p).entries == []
