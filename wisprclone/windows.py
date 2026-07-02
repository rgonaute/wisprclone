from __future__ import annotations

from typing import Callable

import sounddevice as sd
from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QHBoxLayout, QLabel, QLineEdit, QListWidget,
    QPushButton, QTabWidget, QTextEdit, QVBoxLayout, QWidget,
)

from .config import Config
from .history import HistoryStore
from .hotkey import HotkeyCapture

_MODELS = ["large-v3", "medium", "small", "base"]   # multilingual only
_LANGUAGES = [("Auto", "auto"), ("English", "en"), ("Hebrew", "he")]


def _input_device_names() -> list[str]:
    names = []
    try:
        for dev in sd.query_devices():
            if dev.get("max_input_channels", 0) > 0:
                names.append(dev["name"])
    except Exception:
        pass
    return names


class MainWindow(QTabWidget):
    hotkey_captured = Signal(str)

    def __init__(self, config: Config, history: HistoryStore,
                 on_save: Callable[[Config], None]):
        super().__init__()
        self.hotkey_captured.connect(self._apply_captured_hotkey)
        self.config = config
        self.history = history
        self.on_save = on_save
        self._capture = None
        self._pending_hotkey = None  # staged capture; applied to config only on Save
        self.setWindowTitle("WisprClone")
        self.resize(460, 420)
        self.addTab(self._build_settings(), "Settings")
        self.addTab(self._build_history(), "History")

    def show_settings(self) -> None:
        self.setCurrentIndex(0)
        self.show()
        self.raise_()
        self.activateWindow()

    def show_history(self) -> None:
        self.setCurrentIndex(1)
        self.show()
        self.raise_()
        self.activateWindow()

    # --- Settings tab ---
    def _build_settings(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)

        row = QHBoxLayout()
        self.hotkey_label = QLabel()
        set_btn = QPushButton("Set hotkey")
        set_btn.clicked.connect(self._begin_capture)
        row.addWidget(QLabel("Hotkey:"))
        row.addWidget(self.hotkey_label, 1)
        row.addWidget(set_btn)
        layout.addLayout(row)

        self.trigger_box = QComboBox()
        self.trigger_box.addItems(["hold", "toggle"])
        layout.addWidget(QLabel("Trigger mode:"))
        layout.addWidget(self.trigger_box)

        self.mic_box = QComboBox()
        self.mic_box.addItem("System default", None)
        for name in _input_device_names():
            self.mic_box.addItem(name, name)
        layout.addWidget(QLabel("Microphone:"))
        layout.addWidget(self.mic_box)

        self.model_box = QComboBox()
        self.model_box.addItems(_MODELS)
        layout.addWidget(QLabel("Model (multilingual):"))
        layout.addWidget(self.model_box)

        self.lang_box = QComboBox()
        for label, code in _LANGUAGES:
            self.lang_box.addItem(label, code)
        layout.addWidget(QLabel("Language:"))
        layout.addWidget(self.lang_box)

        layout.addWidget(QLabel("Vocabulary hint (English terms you say in Hebrew):"))
        self.vocab_edit = QLineEdit()
        layout.addWidget(self.vocab_edit)

        self.fillers_chk = QCheckBox("Remove English filler words (um, uh)")
        layout.addWidget(self.fillers_chk)

        self.autopaste_chk = QCheckBox("Auto-paste after transcription")
        layout.addWidget(self.autopaste_chk)

        save_btn = QPushButton("Save")
        save_btn.clicked.connect(self._save)
        layout.addWidget(save_btn)
        layout.addStretch(1)

        self._sync_settings_from_config()
        return w

    def _sync_settings_from_config(self) -> None:
        """Populate the settings widgets from the live config. Called at build
        time and every time the window is shown, so out-of-band changes (e.g.
        the tray Language menu, or a fallback-adjusted model) don't get reverted
        when the user saves a stale window."""
        self._pending_hotkey = None
        self.hotkey_label.setText(self.config.hotkey)
        self.trigger_box.setCurrentText(self.config.trigger_mode)
        i = self.mic_box.findData(self.config.input_device)
        self.mic_box.setCurrentIndex(i if i >= 0 else 0)
        self.model_box.setCurrentText(self.config.model)
        li = self.lang_box.findData(self.config.language)
        self.lang_box.setCurrentIndex(li if li >= 0 else 0)
        self.vocab_edit.setText(self.config.vocab_hint)
        self.fillers_chk.setChecked(self.config.remove_fillers)
        self.autopaste_chk.setChecked(self.config.auto_paste)

    def _begin_capture(self) -> None:
        if self._capture is not None:  # don't stack listeners on repeated clicks
            self._capture.stop()
        self.hotkey_label.setText("Press keys…")
        self._capture = HotkeyCapture(on_captured=self.hotkey_captured.emit)
        self._capture.start()

    def _apply_captured_hotkey(self, hotkey: str) -> None:
        # Delivered on the GUI thread via the hotkey_captured signal. Stage it —
        # it becomes the real hotkey only when the user clicks Save, so closing
        # without saving cancels an accidental capture.
        self._capture = None
        self._pending_hotkey = hotkey
        self.hotkey_label.setText(hotkey)

    def _save(self) -> None:
        if self._pending_hotkey is not None:
            self.config.hotkey = self._pending_hotkey
            self._pending_hotkey = None
        self.config.trigger_mode = self.trigger_box.currentText()
        self.config.input_device = self.mic_box.currentData()
        self.config.model = self.model_box.currentText()
        self.config.language = self.lang_box.currentData()
        self.config.vocab_hint = self.vocab_edit.text().strip()
        self.config.remove_fillers = self.fillers_chk.isChecked()
        self.config.auto_paste = self.autopaste_chk.isChecked()
        self.on_save(self.config)

    # --- History tab ---
    def _build_history(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        self.history_list = QListWidget()
        self.preview = QTextEdit()
        self.preview.setReadOnly(True)
        self._refresh_history()
        self.history_list.currentRowChanged.connect(self._show_preview)

        btns = QHBoxLayout()
        copy_btn = QPushButton("Copy selected")
        copy_btn.clicked.connect(self._copy_selected)
        clear_btn = QPushButton("Clear all")
        clear_btn.clicked.connect(self._clear_history)
        btns.addWidget(copy_btn)
        btns.addWidget(clear_btn)

        layout.addWidget(self.history_list, 2)
        layout.addWidget(self.preview, 1)
        layout.addLayout(btns)
        return w

    def _refresh_history(self) -> None:
        self.history_list.clear()
        for e in self.history.entries:
            self.history_list.addItem(f"[{e.timestamp[:19]}] {e.text[:60]}")

    def _show_preview(self, row: int) -> None:
        if 0 <= row < len(self.history.entries):
            self.preview.setPlainText(self.history.entries[row].text)

    def _copy_selected(self) -> None:
        from PySide6.QtWidgets import QApplication
        row = self.history_list.currentRow()
        if 0 <= row < len(self.history.entries):
            QApplication.clipboard().setText(self.history.entries[row].text)

    def _clear_history(self) -> None:
        self.history.clear()
        self._refresh_history()
        self.preview.clear()

    def showEvent(self, event):  # re-sync from config each time the window is shown
        self._sync_settings_from_config()
        self._refresh_history()
        super().showEvent(event)
