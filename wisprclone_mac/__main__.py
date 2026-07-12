from __future__ import annotations

import sys
import threading
from pathlib import Path

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication, QMessageBox

from wisprclone.app import AppController
from wisprclone.audio import Recorder
from wisprclone.history import HistoryStore
from wisprclone.hotkey import HotkeyListener
from wisprclone.runtime_setup import configure
from wisprclone.transcriber import Transcriber
from wisprclone.tray import Tray
from wisprclone.windows import MainWindow

from . import permissions
from .config import MAC_APP_DIR, MAC_CONFIG_PATH, MacConfig
from .notice import format_notice
from .pasteboard import MacPaster
from .single_instance import SingleInstance


class _MainThreadInvoker(QObject):
    """Marshal a callable from a background thread onto the Qt event loop, via a
    queued signal connection (see the Windows entry for the full rationale)."""

    _invoke = Signal(object)

    def __init__(self):
        super().__init__()
        self._invoke.connect(self._run)

    def _run(self, fn):
        fn()

    def post(self, fn):
        self._invoke.emit(fn)


_invoker: "_MainThreadInvoker | None" = None


def _on_main_thread(fn):
    _invoker.post(fn)


def _model_is_cached(model: str) -> bool:
    hub = Path.home() / ".cache" / "huggingface" / "hub"
    return any(hub.glob(f"models--Systran--faster-whisper-{model}"))


def main() -> int:
    configure(MAC_APP_DIR / "logs")

    instance = SingleInstance(MAC_APP_DIR / "wisprclone.lock")
    if not instance.acquire():
        return 0  # another copy is already running

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    app._wisprclone_instance = instance  # keep the flock FD alive for app lifetime

    # QMessageBox needs a QApplication, so the preflight runs after it is created.
    def show_dialog(text: str) -> None:
        QMessageBox.warning(None, "WisprClone — permissions needed", text)

    permissions.preflight(show_dialog)

    global _invoker
    _invoker = _MainThreadInvoker()

    config = MacConfig.load()
    history = HistoryStore(MAC_APP_DIR / "history.json", cap=config.history_cap)
    recorder = Recorder(device=config.input_device)
    transcriber = Transcriber(config)
    paster = MacPaster()

    window_ref = {"win": None}
    tray_ref = {"tray": None}

    def notify(msg: str) -> None:
        sys.stderr.write(f"[wisprclone] {msg}\n")
        tray = tray_ref["tray"]
        if tray is not None:
            tray.notify(format_notice(msg))

    controller = AppController(
        config, recorder, transcriber, paster, history,
        notify=lambda msg: _on_main_thread(lambda: notify(msg)),
        on_state=lambda state: _on_main_thread(lambda: tray_ref["tray"].set_state(state)),
        run_async=True,
    )

    listener_ref = {"listener": None}

    def restart_listener():
        if listener_ref["listener"]:
            listener_ref["listener"].stop()
        lis = HotkeyListener(
            config.hotkey, config.trigger_mode,
            on_start=lambda: _on_main_thread(controller.start_recording),
            on_stop=lambda: _on_main_thread(controller.stop_and_transcribe),
        )
        lis.start()
        listener_ref["listener"] = lis

    def on_save(cfg: MacConfig):
        cfg.save(MAC_CONFIG_PATH)
        recorder.device = cfg.input_device
        if transcriber.ensure_current():
            notify("Model will reload on your next dictation.")
        restart_listener()
        notify("Settings saved.")

    def open_settings():
        if window_ref["win"] is None:
            window_ref["win"] = MainWindow(config, history, on_save)
        window_ref["win"].setCurrentIndex(0)
        window_ref["win"].show()
        window_ref["win"].raise_()
        window_ref["win"].activateWindow()

    def open_history():
        open_settings()
        window_ref["win"].setCurrentIndex(1)

    def on_language_change(code: str):
        config.language = code
        config.save(MAC_CONFIG_PATH)

    tray_ref["tray"] = Tray(
        config,
        on_language_change=on_language_change,
        open_settings=open_settings,
        open_history=open_history,
        quit_fn=app.quit,
    )

    restart_listener()

    threading.Thread(target=lambda: _safe_warm(transcriber, notify),
                     daemon=True).start()

    return app.exec()


def _safe_warm(transcriber: Transcriber, notify) -> None:
    try:
        if _model_is_cached(transcriber.config.model):
            _on_main_thread(lambda: notify("Loading model…"))
        else:
            _on_main_thread(lambda: notify(
                "Downloading model (~1.5 GB, one time)…"))
        transcriber.load()
        if transcriber.used_fallback and transcriber.active_mode:
            model, device, compute_type = transcriber.active_mode
            msg = f"Using {model} on {device} ({compute_type})."
            _on_main_thread(lambda m=msg: notify(m))
    except Exception as exc:
        msg = f"Model load failed: {exc}"
        _on_main_thread(lambda m=msg: notify(m))


if __name__ == "__main__":
    sys.exit(main())
