"""
Écran d'accueil (inspiré de HD My Pictures) : on choisit d'abord un dossier,
parmi les dossiers récents ou avec Parcourir — la liste des fichiers ne
s'affiche qu'ensuite, quand on en a besoin.
"""

import os
from typing import List

from PyQt6.QtCore    import Qt, QRectF, QSize, pyqtSignal
from PyQt6.QtGui     import (QColor, QFont, QFontMetrics, QLinearGradient, QPainter,
                             QPainterPath, QPen, QBrush)
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
                             QSizePolicy, QFrame)

from ui.icons import icon

# Palette « Nuit » de HD My Pictures (fond, verre, dégradé violet → cyan → rose)
_DARK = {
    "bgA": "#0a0a0f", "bgB": "#1e1e2a", "fg": "#ffffff", "fg2": "#a0aec0", "fg3": "#6b7280",
    "glass": QColor(255, 255, 255, 14), "glass_border": QColor(255, 255, 255, 34),
    "hi": "#a78bfa", "danger": "#f87171",
    "grad": ("#7c3aed", "#06b6d4", "#ec4899"),
}
_LIGHT = {
    "bgA": "#f6f4ff", "bgB": "#e6e9f7", "fg": "#17142b", "fg2": "#4b5168", "fg3": "#6b7088",
    "glass": QColor(255, 255, 255, 190), "glass_border": QColor(60, 40, 140, 40),
    "hi": "#6d28d9", "danger": "#c2410c",
    "grad": ("#6d28d9", "#0891b2", "#db2777"),
}

_TITLES = {
    "audio": ("Ta musique,", "au bon format."),
    "image": ("Tes images,", "plus légères."),
}
_PITCH = {
    "audio": "Choisis un dossier : chaque morceau est converti en parallèle, "
             "tags et pochettes compris.",
    "image": "Choisis un dossier : tu vois combien de place tu peux gagner "
             "avant de convertir quoi que ce soit.",
}


class _GradientTitle(QWidget):
    """Deux lignes de titre ; la seconde en dégradé (comme HD My Pictures)."""

    def __init__(self):
        super().__init__()
        self._l1, self._l2 = "", ""
        self._pal = _DARK
        self._font = QFont("Bahnschrift", 46, QFont.Weight.Bold)
        if not QFontMetrics(self._font).horizontalAdvance("A"):
            self._font = QFont("Segoe UI", 44, QFont.Weight.Bold)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def set_text(self, l1: str, l2: str, pal: dict):
        self._l1, self._l2, self._pal = l1, l2, pal
        self.setFixedHeight(int(QFontMetrics(self._font).height() * 2.15))
        self.update()

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        fm = QFontMetrics(self._font)
        p.setFont(self._font)
        p.setPen(QColor(self._pal["fg"]))
        y1 = fm.ascent()
        p.drawText(0, y1, self._l1)
        y2 = y1 + int(fm.height() * 1.05)
        w = fm.horizontalAdvance(self._l2)
        grad = QLinearGradient(0, 0, max(w, 1), 0)
        for pos, col in zip((0.0, 0.5, 1.0), (self._pal["hi"],) + self._pal["grad"][1:]):
            grad.setColorAt(pos, QColor(col))
        path = QPainterPath()
        path.addText(0, y2, self._font, self._l2)
        p.fillPath(path, QBrush(grad))
        p.end()


class _Glass(QFrame):
    """Panneau « verre » : fond translucide, bord fin, coins arrondis."""

    def __init__(self, radius: int = 16):
        super().__init__()
        self._radius = radius
        self._pal = _DARK
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)

    def set_palette(self, pal: dict):
        self._pal = pal
        self.update()

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        p.setPen(QPen(self._pal["glass_border"], 1))
        p.setBrush(self._pal["glass"])
        p.drawRoundedRect(r, self._radius, self._radius)
        p.end()


class HomeScreen(QWidget):
    browse_requested = pyqtSignal()
    open_requested   = pyqtSignal(str)       # dossier récent choisi
    clear_requested  = pyqtSignal()          # effacer l'historique

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pal = _DARK
        self._mode = "audio"
        self._recents: List[str] = []
        self._current = ""
        self._rows: list = []                    # (bouton, nom, emplacement, suffixe)
        self._col = None
        self._build()

    # ── Construction ──────────────────────────────────────────────────────────

    def _build(self):
        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        col = QWidget()
        col.setMaximumWidth(640)
        self._col = col
        lay = QVBoxLayout(col)
        lay.setContentsMargins(72, 64, 24, 24)
        lay.setSpacing(0)

        self._title = _GradientTitle()
        lay.addWidget(self._title)
        lay.addSpacing(10)

        self._pitch = QLabel()
        self._pitch.setWordWrap(True)
        lay.addWidget(self._pitch)
        lay.addSpacing(26)

        # Champ dossier (verre) + Parcourir
        self._field = _Glass(18)
        self._field.setFixedHeight(60)
        fl = QHBoxLayout(self._field)
        fl.setContentsMargins(18, 0, 10, 0)
        fl.setSpacing(12)
        self._field_icon = QLabel()
        fl.addWidget(self._field_icon)
        self._field_text = QLabel()
        self._field_text.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        fl.addWidget(self._field_text, 1)
        self._btn_browse = QPushButton("Parcourir")
        self._btn_browse.setObjectName("home_browse")
        self._btn_browse.setFixedHeight(40)
        self._btn_browse.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_browse.clicked.connect(self.browse_requested.emit)
        fl.addWidget(self._btn_browse)
        lay.addWidget(self._field)
        lay.addSpacing(22)

        # Dossiers récents (verre)
        self._recent_panel = _Glass(16)
        rl = QVBoxLayout(self._recent_panel)
        rl.setContentsMargins(16, 12, 12, 12)
        rl.setSpacing(2)
        head = QHBoxLayout()
        self._lbl_recent = QLabel("DOSSIERS RÉCENTS")
        head.addWidget(self._lbl_recent)
        head.addStretch()
        self._btn_clear = QPushButton("Effacer")
        self._btn_clear.setObjectName("home_link_danger")
        self._btn_clear.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_clear.setToolTip("Vider la liste des dossiers récents")
        self._btn_clear.clicked.connect(self.clear_requested.emit)
        head.addWidget(self._btn_clear)
        rl.addLayout(head)
        rl.addSpacing(6)
        self._rows_box = QVBoxLayout()
        self._rows_box.setSpacing(2)
        rl.addLayout(self._rows_box)
        lay.addWidget(self._recent_panel)

        lay.addStretch(1)
        outer.addWidget(col, 1)
        outer.addStretch(0)

        # Grande barre d'action en dégradé (bas, toute la largeur)
        self._bar = QPushButton()
        self._bar.setObjectName("home_bar")
        self._bar.setCursor(Qt.CursorShape.PointingHandCursor)
        self._bar.setFixedHeight(84)
        self._bar.clicked.connect(self._on_bar)
        self._bar.setParent(self)

    def _on_bar(self):
        cur = self._current if self._current and os.path.isdir(self._current) else ""
        if cur:
            self.open_requested.emit(cur)
        else:
            self.browse_requested.emit()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._bar.setGeometry(0, self.height() - self._bar.height(), self.width(), self._bar.height())
        self._bar.raise_()
        self._elide_rows()

    def _elide_rows(self):
        """Nom du dossier en entier, emplacement raccourci au milieu selon la place."""
        avail = max(120, self._recent_panel.width() - 80)
        for b, name, parent, suffix in self._rows:
            fm = QFontMetrics(b.font())
            head = f"{name}{suffix}"
            rest = avail - fm.horizontalAdvance(head + "     ")
            loc = fm.elidedText(parent, Qt.TextElideMode.ElideMiddle, rest) if rest > 40 else ""
            b.setText(f"  {head}     {loc}" if loc else f"  {head}")

    def _drop_rect(self) -> QRectF:
        """Zone « Glisse un dossier ici » à droite de la colonne (si la place le permet)."""
        if self._col is None:
            return QRectF()
        x0 = self._col.geometry().right() + 56
        x1 = self.width() - 72
        y0, y1 = 80, self.height() - self._bar.height() - 56
        if x1 - x0 < 320 or y1 - y0 < 220:
            return QRectF()
        return QRectF(x0, y0, x1 - x0, y1 - y0)

    # ── Données ───────────────────────────────────────────────────────────────

    def set_mode(self, mode: str):
        self._mode = mode
        self._refresh()

    def set_theme(self, theme: str):
        self._pal = _LIGHT if theme == "light" else _DARK
        self._refresh()

    def set_recents(self, paths: List[str], current: str = ""):
        self._recents = list(paths)
        self._current = current
        self._refresh()

    def _refresh(self):
        pal = self._pal
        self._title.set_text(*_TITLES.get(self._mode, _TITLES["audio"]), pal)
        self._pitch.setText(_PITCH.get(self._mode, ""))
        self._pitch.setStyleSheet(f"color: {pal['fg2']}; font-size: 15px; background: transparent;")
        for g in (self._field, self._recent_panel):
            g.set_palette(pal)
        self._field_icon.setPixmap(icon("folder", pal["hi"], 20).pixmap(QSize(20, 20)))
        cur = self._current if self._current and os.path.isdir(self._current) else ""
        self._field_text.setText(cur or "Aucun dossier sélectionné")
        self._field_text.setStyleSheet(
            f"color: {pal['fg2'] if cur else pal['fg3']}; font-size: 14px; background: transparent;")
        self._lbl_recent.setStyleSheet(
            f"color: {pal['hi']}; font-size: 11px; font-weight: 700; letter-spacing: 1px; background: transparent;")

        g0, g1, g2 = pal["grad"]
        self.setStyleSheet(f"""
            QPushButton#home_browse {{
                background: rgba(255,255,255,26); color: {pal['fg']};
                border: 1px solid rgba(255,255,255,42); border-radius: 12px;
                padding: 0 18px; font-size: 13px; font-weight: 600;
            }}
            QPushButton#home_browse:hover {{ background: rgba(255,255,255,46); }}
            QPushButton#home_link_danger {{
                background: transparent; border: none; color: {pal['danger']};
                font-size: 12px; padding: 2px 6px;
            }}
            QPushButton#home_link_danger:hover {{ text-decoration: underline; }}
            QPushButton#home_row {{
                background: transparent; border: none; border-radius: 16px;
                color: {pal['fg2']}; font-size: 13px; text-align: left; padding: 0 12px;
            }}
            QPushButton#home_row:hover {{ background: rgba(139,92,246,70); color: {pal['fg']}; }}
            QPushButton#home_row:disabled {{ color: {pal['fg3']}; }}
            QPushButton#home_bar {{
                border: none; border-top: 1px solid rgba(255,255,255,70);
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 {g0}, stop:0.5 {g1}, stop:1 {g2});
                color: white; font-family: Bahnschrift, 'Segoe UI'; font-size: 22px; font-weight: 700;
            }}
            QPushButton#home_bar:hover {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 {g1}, stop:0.5 {g2}, stop:1 {g0});
            }}
        """)
        # Un dossier est déjà sélectionné : la barre l'ouvre ; sinon elle en fait choisir un
        self._bar.setIconSize(QSize(24, 24))
        if cur:
            name = os.path.basename(os.path.normpath(cur)) or cur
            self._bar.setIcon(icon("play", "#ffffff", 22))
            self._bar.setText(f"  Ouvrir  {QFontMetrics(self._bar.font()).elidedText(name, Qt.TextElideMode.ElideMiddle, 520)}")
            self._bar.setToolTip(f"Afficher les fichiers de :\n{cur}")
        else:
            self._bar.setIcon(icon("folder", "#ffffff", 24))
            self._bar.setText("  Choisir un dossier")
            self._bar.setToolTip("Choisir le dossier à convertir")

        # Lignes « dossiers récents »
        while self._rows_box.count():
            w = self._rows_box.takeAt(0).widget()
            if w:
                # Masquer et détacher tout de suite : deleteLater() n'agit qu'au
                # prochain tour de boucle, l'ancienne ligne resterait visible
                w.hide()
                w.setParent(None)
                w.deleteLater()
        self._btn_clear.setVisible(bool(self._recents))
        if not self._recents:
            empty = QLabel("Aucun dossier récent — choisis un dossier avec Parcourir")
            empty.setStyleSheet(f"color: {pal['fg3']}; font-size: 13px; background: transparent; padding: 4px 12px;")
            self._rows_box.addWidget(empty)
        self._rows = []
        for path in self._recents:
            exists = os.path.isdir(path)
            is_cur = bool(cur) and os.path.normcase(path) == os.path.normcase(cur)
            b = QPushButton()
            b.setObjectName("home_row")
            b.setFixedHeight(34)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setEnabled(exists)
            b.setIcon(icon("folder", pal["hi"] if is_cur else pal["fg3"], 15))
            b.setIconSize(QSize(15, 15))
            norm = os.path.normpath(path)
            name = os.path.basename(norm) or norm
            parent = os.path.dirname(norm) if os.path.basename(norm) else ""
            self._rows.append((b, name, parent, "" if exists else "  (introuvable)"))
            b.setToolTip(("Ouvrir ce dossier :\n" if exists else "Dossier introuvable :\n") + path)
            b.clicked.connect(lambda _c, p=path: self.open_requested.emit(p))
            self._rows_box.addWidget(b)
        self._elide_rows()
        self.update()

    # ── Fond ──────────────────────────────────────────────────────────────────

    def paintEvent(self, _e):
        p = QPainter(self)
        grad = QLinearGradient(0, 0, self.width() * 0.4, self.height())
        grad.setColorAt(0, QColor(self._pal["bgA"]))
        grad.setColorAt(1, QColor(self._pal["bgB"]))
        p.fillRect(self.rect(), grad)
        # Halo coloré discret à droite (rappel du dégradé de la barre)
        halo = QLinearGradient(self.width(), 0, self.width() * 0.55, self.height() * 0.7)
        c = QColor(self._pal["grad"][0]); c.setAlpha(55)
        halo.setColorAt(0, c)
        c2 = QColor(self._pal["grad"][1]); c2.setAlpha(0)
        halo.setColorAt(1, c2)
        p.fillRect(self.rect(), halo)

        # Zone de dépôt
        r = self._drop_rect()
        if not r.isEmpty():
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            pen = QPen(self._pal["glass_border"], 2, Qt.PenStyle.DashLine)
            pen.setDashPattern([6, 6])
            p.setPen(pen)
            p.setBrush(QColor(255, 255, 255, 6) if self._pal is _DARK else QColor(255, 255, 255, 120))
            p.drawRoundedRect(r, 24, 24)
            ic = icon("folder", self._pal["hi"], 56).pixmap(QSize(56, 56))
            c = r.center()
            p.drawPixmap(int(c.x() - 28), int(c.y() - 70), ic)
            f = QFont("Segoe UI", 15, QFont.Weight.DemiBold)
            p.setFont(f)
            p.setPen(QColor(self._pal["fg"]))
            p.drawText(QRectF(r.x(), c.y() + 2, r.width(), 30), Qt.AlignmentFlag.AlignHCenter,
                       "Glisse un dossier ici")
            p.setFont(QFont("Segoe UI", 11))
            p.setPen(QColor(self._pal["fg3"]))
            p.drawText(QRectF(r.x(), c.y() + 36, r.width(), 24), Qt.AlignmentFlag.AlignHCenter,
                       "ou des fichiers, depuis l'Explorateur")
        p.end()
