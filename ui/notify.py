"""
Fin de tâche (estimation, conversion) : son si l'app est au premier plan,
notification Windows sinon (avec le son de notification du système).
"""

from PyQt6.QtCore import QObject, QEvent
from PyQt6.QtWidgets import QSystemTrayIcon, QWidget

try:
    import winsound
except ImportError:                     # hors Windows
    winsound = None


def _play_sound():
    if winsound is None:
        return
    try:
        winsound.PlaySound("SystemAsterisk", winsound.SND_ALIAS | winsound.SND_ASYNC)
    except RuntimeError:
        pass


class Notifier(QObject):
    def __init__(self, window: QWidget):
        super().__init__(window)
        self._win = window
        self._tray = None
        window.installEventFilter(self)

    def _in_foreground(self) -> bool:
        return self._win.isActiveWindow() and not self._win.isMinimized()

    def notify(self, title: str, text: str):
        if self._in_foreground():
            _play_sound()
            return
        if not QSystemTrayIcon.isSystemTrayAvailable():
            _play_sound()
            return
        if self._tray is None:
            self._tray = QSystemTrayIcon(self._win.windowIcon(), self)
            self._tray.setToolTip(self._win.windowTitle())
            self._tray.messageClicked.connect(self._bring_to_front)
            self._tray.activated.connect(lambda *_: self._bring_to_front())
        # L'icône reste dans la zone de notification tant que l'app n'est pas
        # revenue au premier plan, pour que la notification reste cliquable
        self._tray.show()
        self._tray.showMessage(title, text, self._win.windowIcon(), 10000)

    def _bring_to_front(self):
        w = self._win
        if w.isMinimized():
            w.showNormal()
        w.raise_()
        w.activateWindow()

    def eventFilter(self, obj, event):
        if (obj is self._win and event.type() == QEvent.Type.WindowActivate
                and self._tray is not None and self._tray.isVisible()):
            self._tray.hide()
        return False
