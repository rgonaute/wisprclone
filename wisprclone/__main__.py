from __future__ import annotations

import sys

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from .app import AppController
from .audio import Recorder
from .config import CONFIG_PATH, Config
from .history import HistoryStore
from .hotkey import HotkeyListener
from .paste import Paster
from .tray import Tray
from .transcriber import Transcriber
from .windows import MainWindow


def _on_main_thread(fn):
    """Marshal a call from a background thread onto the Qt event loop."""
    QTimer.singleShot(0, fn)


def main() -> int:
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)  # tray app keeps running with no window

    from .config import APP_DIR
    config = Config.load()
    history = HistoryStore(APP_DIR / "history.json", cap=config.history_cap)
    recorder = Recorder(device=config.input_device)
    transcriber = Transcriber(config)
    paster = Paster()

    window_ref = {"win": None}
    tray_ref = {"tray": None}

    controller = AppController(
        config, recorder, transcriber, paster, history,
        notify=lambda msg: _on_main_thread(lambda: tray_ref["tray"].notify(msg)),
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

    def on_save(cfg: Config):
        cfg.save(CONFIG_PATH)
        recorder.device = cfg.input_device
        if transcriber.ensure_current():
            tray_ref["tray"].notify("Model will reload on your next dictation.")
        restart_listener()
        tray_ref["tray"].notify("Settings saved.")

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
        config.save(CONFIG_PATH)

    tray_ref["tray"] = Tray(
        config,
        on_language_change=on_language_change,
        open_settings=open_settings,
        open_history=open_history,
        quit_fn=app.quit,
    )

    restart_listener()

    # Warm the model in the background so the first transcription isn't slow.
    import threading
    threading.Thread(target=lambda: _safe_warm(transcriber, tray_ref),
                     daemon=True).start()

    return app.exec()


def _safe_warm(transcriber: Transcriber, tray_ref) -> None:
    try:
        transcriber.load()
        if transcriber.used_fallback:
            _on_main_thread(lambda: tray_ref["tray"].notify(
                "GPU unavailable — using CPU (base model)."))
    except Exception as exc:
        _on_main_thread(lambda: tray_ref["tray"].notify(f"Model load failed: {exc}"))


if __name__ == "__main__":
    sys.exit(main())
