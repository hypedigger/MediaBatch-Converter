"""
Soutien du projet : lien Ko-fi et invitation ponctuelle (10e lancement, puis
tous les 100), fermable d'un clic, avec opt-out définitif.
"""

from PyQt6.QtCore    import Qt, QUrl
from PyQt6.QtGui     import QFont, QDesktopServices
from PyQt6.QtWidgets import (QDialog, QWidget, QVBoxLayout, QHBoxLayout,
                             QLabel, QPushButton, QCheckBox)

from core.config import KOFI_URL
from ui.effects  import apply_acrylic


def open_kofi():
    """Ouvre la page Ko-fi dans le navigateur par défaut."""
    QDesktopServices.openUrl(QUrl(KOFI_URL))


def support_due(count: int, optout: bool) -> bool:
    """Invitation au 10e lancement, puis tous les 100 — jamais après opt-out."""
    return not optout and (count == 10 or (count >= 100 and count % 100 == 0))


class SupportDialog(QDialog):
    def __init__(self, theme: str = "dark", parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedWidth(460)
        self._dark = theme == "dark"
        self._kofi = False

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        card = QWidget()
        card.setObjectName("central_widget")
        outer.addWidget(card)

        lay = QVBoxLayout(card)
        lay.setContentsMargins(28, 24, 28, 24)
        lay.setSpacing(14)

        title = QLabel("☕  Vous aimez MediaBatch Converter ?")
        title.setFont(QFont("Segoe UI Variable", 14, QFont.Weight.Bold))
        lay.addWidget(title)

        msg = QLabel(
            "Cette application est gratuite et open source, développée sur "
            "le temps libre de son créateur.\n\n"
            "Si elle vous fait gagner du temps, un petit café sur Ko-fi "
            "l'aide à continuer — merci !"
        )
        msg.setWordWrap(True)
        lay.addWidget(msg)

        self._chk_optout = QCheckBox("Ne plus me le demander")
        lay.addWidget(self._chk_optout)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        btn_row.addStretch()

        btn_later = QPushButton("Plus tard")
        btn_later.clicked.connect(self.reject)
        btn_row.addWidget(btn_later)

        btn_kofi = QPushButton("☕  Soutenir sur Ko-fi")
        btn_kofi.setObjectName("btn_primary")
        btn_kofi.setDefault(True)
        btn_kofi.clicked.connect(self._choose_kofi)
        btn_row.addWidget(btn_kofi)

        lay.addLayout(btn_row)
        self.adjustSize()

    def _choose_kofi(self):
        self._kofi = True
        self.accept()

    def kofi_chosen(self) -> bool:
        return self._kofi

    def optout_checked(self) -> bool:
        return self._chk_optout.isChecked()

    def showEvent(self, e):
        super().showEvent(e)
        apply_acrylic(int(self.winId()), dark=self._dark)
