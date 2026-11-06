import time
from typing import Callable, Optional

from PyQt6.QtCore    import Qt, QTimer, QPropertyAnimation, QEasingCurve, QEvent, QSize
from ui.icons import icon, PALETTE
from PyQt6.QtWidgets import (QFrame, QHBoxLayout, QVBoxLayout, QLabel, QPushButton,
                              QGraphicsOpacityEffect, QProgressBar, QWidget)


class Toast(QFrame):
    """
    Suggestion discrète, posée dans un coin de *parent* : n'impose aucun choix,
    ne bloque rien et disparaît seule au bout de *timeout_ms* (le décompte est
    suspendu tant que la souris est dessus).
    """

    def __init__(self, parent: QWidget, timeout_ms: int = 9000):
        super().__init__(parent)
        self.setObjectName("toast")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._timeout   = timeout_ms
        self._remaining = timeout_ms
        self._action: Optional[Callable[[], None]] = None

        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 12, 10, 8)
        lay.setSpacing(8)

        row = QHBoxLayout()
        row.setSpacing(12)
        self._lbl = QLabel()
        self._lbl.setObjectName("toast_label")
        self._lbl.setWordWrap(True)
        row.addWidget(self._lbl, 1)

        self._btn = QPushButton()
        self._btn.setObjectName("btn_accent")
        self._btn.clicked.connect(self._on_action)
        row.addWidget(self._btn)

        btn_close = QPushButton()
        btn_close.setObjectName("btn_icon")
        btn_close.setIcon(icon("close", PALETTE["dark"]["muted"], 15))
        btn_close.setIconSize(QSize(15, 15))
        btn_close.setFixedSize(28, 28)
        btn_close.setToolTip("Ignorer")
        btn_close.clicked.connect(self.dismiss)
        row.addWidget(btn_close, 0, Qt.AlignmentFlag.AlignTop)
        lay.addLayout(row)

        # Fine barre qui se vide : temps restant avant disparition
        self._bar = QProgressBar()
        self._bar.setObjectName("toast_bar")
        self._bar.setTextVisible(False)
        self._bar.setFixedHeight(3)
        self._bar.setRange(0, timeout_ms)
        lay.addWidget(self._bar)

        self._fx = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self._fx)
        self._anim = QPropertyAnimation(self._fx, b"opacity", self)
        self._anim.setDuration(220)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        self._tick = QTimer(self)
        self._tick.setInterval(50)
        self._tick.timeout.connect(self._on_tick)

        parent.installEventFilter(self)     # suivre les redimensionnements
        self.hide()

    # ── API ───────────────────────────────────────────────────────────────────

    def show_message(self, text: str, action_text: str, action: Callable[[], None],
                     action_icon: Optional[str] = None):
        self._lbl.setText(text)
        self._btn.setText(action_text)
        if action_icon:
            self._btn.setIcon(icon(action_icon, PALETTE["dark"]["on_accent"], 17))
            self._btn.setIconSize(QSize(17, 17))
        self._action = action
        self._remaining = self._timeout
        self._bar.setValue(self._timeout)
        self.setFixedWidth(min(560, max(380, self.parentWidget().width() // 3)))
        self.adjustSize()
        self._place()
        self.show()
        self.raise_()
        self._fade(1.0)
        self._last = time.monotonic()
        self._tick.start()

    def dismiss(self):
        self._tick.stop()
        if self.isVisible():
            self._fade(0.0, then_hide=True)

    # ── Interne ───────────────────────────────────────────────────────────────

    def _on_action(self):
        action = self._action
        self.dismiss()
        if action:
            action()

    def _on_tick(self):
        # Temps réellement écoulé : les minuteries Windows dérivent (~60 ms au lieu de 50)
        now = time.monotonic()
        elapsed, self._last = (now - self._last) * 1000, now
        if self.underMouse():
            return                      # lecture en cours : on ne presse pas
        self._remaining -= elapsed
        self._bar.setValue(max(0, int(self._remaining)))
        if self._remaining <= 0:
            self.dismiss()

    def _fade(self, target: float, then_hide: bool = False):
        self._anim.stop()
        try:
            self._anim.finished.disconnect()
        except TypeError:
            pass
        self._anim.setStartValue(self._fx.opacity() if self.isVisible() else 0.0)
        self._anim.setEndValue(target)
        if then_hide:
            self._anim.finished.connect(self.hide)
        self._anim.start()

    def _place(self):
        p = self.parentWidget()
        margin = 18
        # Au-dessus du panneau du bas pour ne masquer aucun bouton
        self.move(p.width() - self.width() - margin,
                  p.height() - self.height() - getattr(p, "toast_bottom_offset", 150))

    def eventFilter(self, obj, event):
        if obj is self.parentWidget() and event.type() == QEvent.Type.Resize and self.isVisible():
            self._place()
        return False
