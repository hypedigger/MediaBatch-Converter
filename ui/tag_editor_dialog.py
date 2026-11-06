"""
Éditeur de tags intégré — dialogue frameless dans le style de l'app.
Édite titre/artiste/album/… et la pochette via core.tags (mutagen).
"""
import os
from typing import Optional

from PyQt6.QtCore    import Qt, QSize
from PyQt6.QtGui     import QFont, QPixmap
from PyQt6.QtWidgets import (
    QDialog, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QLineEdit, QPushButton, QFrame, QFileDialog, QMessageBox,
)

from core.tags   import TAG_FIELDS, read_tags, write_tags, read_cover, write_cover
from ui.effects  import apply_acrylic
from ui.icons    import icon, PALETTE


_COVER_SIZE = 190


class TagEditorDialog(QDialog):
    """Édite les tags d'un seul fichier. exec() → Accepted si enregistré."""

    def __init__(self, file_path: str, dark: bool = True, parent=None):
        super().__init__(parent)
        self._path  = file_path
        self._dark  = dark
        self._new_cover:      Optional[bytes] = None   # pochette choisie par l'utilisateur
        self._new_cover_mime: str = ""
        self.saved = False

        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedWidth(640)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        card = QWidget()
        card.setObjectName("central_widget")
        outer.addWidget(card)

        lay = QVBoxLayout(card)
        lay.setContentsMargins(28, 24, 28, 24)
        lay.setSpacing(14)

        # ── Titre ────────────────────────────────────────────────────────────
        title = QLabel("Éditeur de tags")
        title.setFont(QFont("Segoe UI Variable", 14, QFont.Weight.Bold))
        title.setStyleSheet("color: #c0a0ff;")
        lay.addWidget(title)

        fname = QLabel(os.path.basename(file_path))
        fname.setStyleSheet("color: rgba(255,255,255,140); font-size:12px;")
        fname.setWordWrap(True)
        lay.addWidget(fname)

        sep = QFrame(); sep.setFrameShape(QFrame.Shape.HLine)
        lay.addWidget(sep)

        # ── Corps : pochette à gauche, champs à droite ───────────────────────
        body = QHBoxLayout()
        body.setSpacing(22)

        cover_col = QVBoxLayout()
        cover_col.setSpacing(8)

        self._cover_lbl = QLabel()
        self._cover_lbl.setFixedSize(_COVER_SIZE, _COVER_SIZE)
        self._cover_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._cover_lbl.setStyleSheet(
            "background: rgba(255,255,255,6);"
            "border: 1px solid rgba(255,255,255,14);"
            "border-radius: 10px;"
            "color: rgba(255,255,255,80); font-size: 12px;"
        )
        cover_col.addWidget(self._cover_lbl)

        btn_cover = QPushButton(" Changer la pochette…")
        btn_cover.setIcon(icon("image", PALETTE["dark"]["text"], 16))
        btn_cover.setIconSize(QSize(16, 16))
        btn_cover.clicked.connect(self._pick_cover)
        cover_col.addWidget(btn_cover)
        cover_col.addStretch()
        body.addLayout(cover_col)

        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(10)

        self._edits = {}
        for row, (key, label) in enumerate(TAG_FIELDS):
            lbl = QLabel(label)
            lbl.setStyleSheet("color: rgba(200,200,220,150); font-size:12px;")
            grid.addWidget(lbl, row, 0)
            edit = QLineEdit()
            self._edits[key] = edit
            grid.addWidget(edit, row, 1)

        body.addLayout(grid, 1)
        lay.addLayout(body)

        # ── Boutons ──────────────────────────────────────────────────────────
        btn_row = QHBoxLayout()
        btn_row.addStretch()

        btn_cancel = QPushButton("Annuler")
        btn_cancel.clicked.connect(self.reject)
        btn_row.addWidget(btn_cancel)

        btn_save = QPushButton("  💾  Enregistrer  ")
        btn_save.setObjectName("btn_primary")
        btn_save.clicked.connect(self._save)
        btn_row.addWidget(btn_save)
        lay.addLayout(btn_row)

        self._load()
        self.adjustSize()

    # ── Chargement ────────────────────────────────────────────────────────────

    def _load(self):
        try:
            tags = read_tags(self._path)
        except Exception as e:
            QMessageBox.warning(self, "Erreur",
                                f"Impossible de lire les tags :\n{e}")
            tags = {}
        for key, edit in self._edits.items():
            edit.setText(tags.get(key, ""))

        try:
            data = read_cover(self._path)
        except Exception:
            data = None
        self._show_cover(data)

    def _show_cover(self, data: Optional[bytes]):
        if data:
            pix = QPixmap()
            if pix.loadFromData(data):
                self._cover_lbl.setPixmap(pix.scaled(
                    _COVER_SIZE, _COVER_SIZE,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                ))
                return
        self._cover_lbl.setText("Aucune\npochette")

    # ── Actions ───────────────────────────────────────────────────────────────

    def _pick_cover(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Choisir une pochette",
            os.path.dirname(self._path),
            "Images (*.jpg *.jpeg *.png)",
        )
        if not path:
            return
        try:
            with open(path, "rb") as f:
                data = f.read()
        except OSError as e:
            QMessageBox.warning(self, "Erreur", f"Impossible de lire l'image :\n{e}")
            return

        self._new_cover = data
        self._new_cover_mime = (
            "image/png" if path.lower().endswith(".png") else "image/jpeg"
        )
        self._show_cover(data)

    def _save(self):
        tags = {key: edit.text() for key, edit in self._edits.items()}
        try:
            write_tags(self._path, tags)
            if self._new_cover:
                write_cover(self._path, self._new_cover, self._new_cover_mime)
        except Exception as e:
            QMessageBox.critical(self, "Erreur",
                                 f"Impossible d'enregistrer les tags :\n{e}")
            return
        self.saved = True
        self.accept()

    # ── Acrylic ───────────────────────────────────────────────────────────────

    def showEvent(self, e):
        super().showEvent(e)
        apply_acrylic(int(self.winId()), dark=self._dark)
