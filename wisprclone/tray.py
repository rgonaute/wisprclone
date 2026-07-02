from __future__ import annotations

from typing import Callable

from PySide6.QtGui import QAction, QActionGroup, QIcon, QPixmap
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

_STATE_TOOLTIP = {
    "idle": "WisprClone — ready",
    "recording": "WisprClone — recording…",
    "transcribing": "WisprClone — transcribing…",
}
_STATE_COLOR = {
    "idle": "#3e435e",
    "recording": "#fb2c36",
    "transcribing": "#fdc20e",
}


def _dot_icon(hex_color: str) -> QIcon:
    pix = QPixmap(16, 16)
    pix.fill(0)  # transparent
    from PySide6.QtGui import QColor, QPainter
    painter = QPainter(pix)
    painter.setBrush(QColor(hex_color))
    painter.setPen(QColor(hex_color))
    painter.drawEllipse(2, 2, 12, 12)
    painter.end()
    return QIcon(pix)


class Tray:
    def __init__(self, config, on_language_change: Callable[[str], None],
                 open_settings: Callable[[], None], open_history: Callable[[], None],
                 quit_fn: Callable[[], None]):
        self.config = config
        self.icon = QSystemTrayIcon(_dot_icon(_STATE_COLOR["idle"]))
        self.icon.setToolTip(_STATE_TOOLTIP["idle"])
        menu = QMenu()

        lang_menu = menu.addMenu("Language")
        group = QActionGroup(lang_menu)
        group.setExclusive(True)
        for label, code in [("Auto", "auto"), ("English", "en"), ("Hebrew", "he")]:
            act = QAction(label, lang_menu, checkable=True)
            act.setChecked(config.language == code)
            act.triggered.connect(lambda _checked, c=code: on_language_change(c))
            group.addAction(act)
            lang_menu.addAction(act)

        menu.addAction("Settings", open_settings)
        menu.addAction("History", open_history)
        menu.addSeparator()
        menu.addAction("Quit", quit_fn)
        self.icon.setContextMenu(menu)
        self.icon.show()

    def set_state(self, state: str) -> None:
        self.icon.setIcon(_dot_icon(_STATE_COLOR.get(state, _STATE_COLOR["idle"])))
        self.icon.setToolTip(_STATE_TOOLTIP.get(state, "WisprClone"))

    def notify(self, message: str) -> None:
        self.icon.showMessage("WisprClone", message, QSystemTrayIcon.Information, 4000)
