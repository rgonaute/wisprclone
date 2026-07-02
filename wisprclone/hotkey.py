from __future__ import annotations

from typing import Callable, Iterable

from pynput import keyboard


def key_token(key) -> str:
    name = getattr(key, "name", None)
    if name:
        return str(name).lower()
    char = getattr(key, "char", None)
    if char:
        return str(char).lower()
    return str(key).lower()


def parse_hotkey(s: str) -> frozenset[str]:
    return frozenset(t.strip().lower() for t in s.split("+") if t.strip())


def format_hotkey(tokens: Iterable[str]) -> str:
    return "+".join(sorted(tokens))


class HotkeyListener:
    def __init__(self, hotkey_str: str, trigger_mode: str,
                 on_start: Callable[[], None], on_stop: Callable[[], None]):
        self.target = parse_hotkey(hotkey_str)
        self.trigger_mode = trigger_mode
        self.on_start = on_start
        self.on_stop = on_stop
        self._held: set[str] = set()
        self._active = False
        self._was_covered = False
        self._listener = None

    def _covered(self) -> bool:
        return bool(self.target) and self.target <= self._held

    def press(self, key) -> None:
        self._held.add(key_token(key))
        if self._covered() and not self._was_covered:
            self._was_covered = True
            if self.trigger_mode == "hold":
                self._active = True
                self.on_start()
            else:  # toggle
                self._active = not self._active
                (self.on_start if self._active else self.on_stop)()

    def release(self, key) -> None:
        self._held.discard(key_token(key))
        if not self._covered() and self._was_covered:
            self._was_covered = False
            if self.trigger_mode == "hold" and self._active:
                self._active = False
                self.on_stop()

    def start(self) -> None:
        self._listener = keyboard.Listener(on_press=self.press, on_release=self.release)
        self._listener.start()

    def stop(self) -> None:
        if self._listener:
            self._listener.stop()
            self._listener = None


class HotkeyCapture:
    def __init__(self, on_captured: Callable[[str], None]):
        self.on_captured = on_captured
        self._held: set[str] = set()
        self._max: set[str] = set()
        self._listener = None

    def press(self, key) -> None:
        self._held.add(key_token(key))
        if len(self._held) > len(self._max):
            self._max = set(self._held)

    def release(self, key) -> None:
        self._held.discard(key_token(key))
        if not self._held and self._max:
            captured = format_hotkey(self._max)
            self._max = set()
            self.on_captured(captured)
            self.stop()

    def start(self) -> None:
        self._listener = keyboard.Listener(on_press=self.press, on_release=self.release)
        self._listener.start()

    def stop(self) -> None:
        if self._listener:
            self._listener.stop()
            self._listener = None
