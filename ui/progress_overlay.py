"""
Panneau affiché par-dessus la liste pendant une conversion : la sélection est
voilée (et verrouillée), une carte montre l'avancement, le dossier en cours,
le temps écoulé / restant et le gain obtenu jusqu'ici.
"""

import os
import time
from typing import Dict, Iterable, Optional, Set, Tuple

from PyQt6.QtCore import (Qt, QEasingCurve, QEvent, QPointF, QPropertyAnimation, QRectF,
                          QTimer, pyqtSignal)
from PyQt6.QtGui import (QColor, QConicalGradient, QFont, QFontMetrics, QLinearGradient,
                         QPainter, QPainterPath, QPen)
from PyQt6.QtWidgets import (QGraphicsOpacityEffect, QHBoxLayout, QLabel, QPushButton,
                             QVBoxLayout, QWidget, QGridLayout)

from ui.icons import icon
from ui.image_tree import fmt_bytes

_GRAD = ("#7c3aed", "#06b6d4", "#ec4899")      # dégradé de l'écran d'accueil

_THEMES = {
    "dark": dict(scrim=QColor(10, 10, 16, 205), card0="#15151f", card1="#1f1f2e",
                 border=QColor(255, 255, 255, 20), track=QColor(255, 255, 255, 20),
                 fg="#ffffff", fg2="#b4bccb", fg3="#7d8496", comet=QColor(255, 255, 255, 150)),
    "light": dict(scrim=QColor(240, 241, 247, 215), card0="#ffffff", card1="#f4f5fb",
                  border=QColor(0, 0, 0, 22), track=QColor(0, 0, 0, 16),
                  fg="#1d2130", fg2="#4b5263", fg3="#868c9c", comet=QColor(124, 58, 237, 140)),
}


def _dur(sec: float) -> str:
    sec = int(sec)
    if sec < 60:
        return f"{sec} s"
    m, s = divmod(sec, 60)
    if m < 60:
        return f"{m} min {s:02d} s"
    h, m = divmod(m, 60)
    return f"{h} h {m:02d} min"


def _eta(sec: float) -> str:
    """Temps restant arrondi (une précision à la seconde serait trompeuse)."""
    if sec < 10:
        return "quelques s"
    if sec < 60:
        return f"≈ {int(round(sec / 5) * 5)} s"
    if sec < 3600:
        sec = round(sec / 10) * 10
        m, s = divmod(int(sec), 60)
        return f"≈ {m} min {s:02d} s" if m < 10 else f"≈ {m} min"
    h, m = divmod(int(sec // 60), 60)
    return f"≈ {h} h {m:02d} min"


# ── Anneau de progression ────────────────────────────────────────────────────

class _Ring(QWidget):
    def __init__(self, size: int = 172, parent=None):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self._shown = 0.0           # valeur affichée (rattrape la cible en douceur)
        self.target = 0.0
        self._comet = 0.0           # point lumineux qui tourne : « ça travaille »
        self.running = False
        self.sub = ""
        self.t = _THEMES["dark"]

    def tick(self) -> bool:
        changed = False
        if abs(self.target - self._shown) > 0.0005:
            self._shown += (self.target - self._shown) * 0.18
            changed = True
        if self.running:
            self._comet = (self._comet + 2.4) % 360
            changed = True
        if changed:
            self.update()
        return changed

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        stroke = 12
        r = QRectF(self.rect()).adjusted(stroke / 2 + 2, stroke / 2 + 2,
                                         -stroke / 2 - 2, -stroke / 2 - 2)
        # Piste
        pen = QPen(self.t["track"], stroke)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        p.drawEllipse(r)
        # Arc : dégradé du violet (départ, en haut) vers le cyan puis le rose
        v = max(0.0, min(1.0, self._shown))
        if v > 0.002:
            g = QConicalGradient(r.center(), 97)     # jointure juste avant le départ
            g.setColorAt(0.0, QColor(_GRAD[2]))
            g.setColorAt(0.5, QColor(_GRAD[1]))
            g.setColorAt(1.0, QColor(_GRAD[0]))
            pen = QPen(g, stroke)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            p.setPen(pen)
            p.drawArc(r, 90 * 16, -int(v * 360 * 16))
        # Comète sur la piste
        if self.running:
            import math
            a = math.radians(90 - self._comet)
            c = r.center()
            pt = QPointF(c.x() + r.width() / 2 * math.cos(a), c.y() - r.height() / 2 * math.sin(a))
            col = QColor(self.t["comet"])
            for rad, alpha in ((7, 40), (4.5, 90), (2.6, 255)):
                col.setAlpha(int(self.t["comet"].alpha() * alpha / 255))
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(col)
                p.drawEllipse(pt, rad, rad)
        # Pourcentage au centre
        p.setPen(QColor(self.t["fg"]))
        f = QFont("Bahnschrift", 30, QFont.Weight.Bold)
        p.setFont(f)
        pct = f"{int(v * 100)}"
        fm = QFontMetrics(f)
        small = QFont("Bahnschrift", 15, QFont.Weight.DemiBold)
        fms = QFontMetrics(small)
        w = fm.horizontalAdvance(pct) + 4 + fms.horizontalAdvance("%")
        x = (self.width() - w) / 2
        base = self.height() / 2 + fm.capHeight() / 2 - 6
        p.drawText(QPointF(x, base), pct)
        p.setFont(small)
        p.setPen(QColor(self.t["fg2"]))
        p.drawText(QPointF(x + fm.horizontalAdvance(pct) + 4, base), "%")
        if self.sub:
            sf = QFont("Segoe UI Variable", 9)
            p.setFont(sf)
            p.setPen(QColor(self.t["fg3"]))
            sw = QFontMetrics(sf).horizontalAdvance(self.sub)
            p.drawText(QPointF((self.width() - sw) / 2, base + 24), self.sub)


# ── Carte ────────────────────────────────────────────────────────────────────

class _Card(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.t = _THEMES["dark"]
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        path = QPainterPath()
        path.addRoundedRect(r, 18, 18)
        g = QLinearGradient(r.topLeft(), r.bottomRight())
        g.setColorAt(0, QColor(self.t["card0"]))
        g.setColorAt(1, QColor(self.t["card1"]))
        p.fillPath(path, g)
        p.setPen(QPen(self.t["border"], 1))
        p.drawPath(path)
        # Liseré dégradé en haut
        strip = QLinearGradient(r.left(), 0, r.right(), 0)
        for i, c in enumerate(_GRAD):
            strip.setColorAt(i / (len(_GRAD) - 1), QColor(c))
        p.save()
        p.setClipPath(path)
        p.fillRect(QRectF(r.left(), r.top(), r.width(), 3), strip)
        p.restore()


class _Stat(QWidget):
    def __init__(self, caption: str, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(2)
        self.cap = QLabel(caption.upper())
        self.cap.setFixedHeight(16)
        self.cap.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBottom)
        self.val = QLabel("—")
        lay.addWidget(self.cap)
        lay.addWidget(self.val)

    def style(self, t, accent: Optional[str] = None):
        self.cap.setStyleSheet(f"color: {t['fg3']}; font-size: 10px; font-weight: 700; "
                               "letter-spacing: 1.2px; background: transparent;")
        self.val.setStyleSheet(f"color: {accent or t['fg']}; font-family: Bahnschrift, 'Segoe UI'; "
                               "font-size: 19px; font-weight: 600; background: transparent;")


# ── Panneau ──────────────────────────────────────────────────────────────────

class ConversionOverlay(QWidget):
    cancel_requested = pyqtSignal()

    def __init__(self, cover: QWidget, theme: str = "dark"):
        """*cover* : le widget à recouvrir (le panneau de la liste)."""
        super().__init__(cover.parentWidget())
        self._cover = cover
        cover.installEventFilter(self)
        self.hide()

        self._t0 = 0.0
        self._sizes: Dict[str, int] = {}
        self._total_bytes = 1
        self._done_bytes = 0
        self._n_total = self._n_done = self._n_failed = 0
        self._saved = 0
        self._inflight: Dict[str, None] = {}      # ordonné : plus ancien en premier
        self._root = ""
        self._phase: Optional[str] = None

        self._card = _Card(self)
        self._card.setFixedWidth(640)
        outer = QVBoxLayout(self)
        outer.addStretch(1)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(self._card)
        row.addStretch(1)
        outer.addLayout(row)
        outer.addStretch(1)

        lay = QVBoxLayout(self._card)
        lay.setContentsMargins(30, 26, 30, 22)
        lay.setSpacing(18)

        head = QVBoxLayout()
        head.setSpacing(3)
        self._title = QLabel("Conversion en cours")
        self._settings = QLabel()
        self._settings.setWordWrap(True)
        head.addWidget(self._title)
        head.addWidget(self._settings)
        lay.addLayout(head)

        body = QHBoxLayout()
        body.setSpacing(28)
        self._ring = _Ring()
        body.addWidget(self._ring, 0, Qt.AlignmentFlag.AlignVCenter)

        right = QVBoxLayout()
        right.setSpacing(4)
        self._cap_dir = QLabel("DOSSIER EN COURS")
        right.addWidget(self._cap_dir)
        dir_row = QHBoxLayout()
        dir_row.setSpacing(8)
        self._ico_dir = QLabel()
        dir_row.addWidget(self._ico_dir, 0, Qt.AlignmentFlag.AlignVCenter)
        self._lbl_dir = QLabel("—")
        self._lbl_dir.setMinimumWidth(10)
        dir_row.addWidget(self._lbl_dir, 1)
        right.addLayout(dir_row)
        self._lbl_file = QLabel("")
        self._lbl_file.setMinimumWidth(10)
        right.addWidget(self._lbl_file)
        right.addSpacing(16)

        stats = QGridLayout()
        stats.setHorizontalSpacing(26)
        self._st_elapsed = _Stat("Écoulé")
        self._st_left = _Stat("Restant")
        self._st_gain = _Stat("Gain")
        for i, st in enumerate((self._st_elapsed, self._st_left, self._st_gain)):
            stats.addWidget(st, 0, i)
        stats.setColumnStretch(3, 1)
        right.addLayout(stats)
        right.addStretch(1)
        body.addLayout(right, 1)
        lay.addLayout(body)

        foot = QHBoxLayout()
        self._lbl_errors = QLabel("")
        foot.addWidget(self._lbl_errors, 1)
        self._btn_cancel = QPushButton(" Annuler")
        self._btn_cancel.setFixedHeight(34)
        self._btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_cancel.clicked.connect(self._on_cancel)
        foot.addWidget(self._btn_cancel)
        lay.addLayout(foot)

        self._fx = QGraphicsOpacityEffect(self)
        self._fx.setOpacity(0.0)
        self.setGraphicsEffect(self._fx)
        self._anim = QPropertyAnimation(self._fx, b"opacity", self)
        self._anim.setDuration(220)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.finished.connect(self._on_anim_done)

        self._timer = QTimer(self)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self._on_tick)
        self._ticks = 0

        self.set_theme(theme)

    # ── Thème ─────────────────────────────────────────────────────────────────

    def set_theme(self, theme: str):
        t = self.t = _THEMES.get(theme, _THEMES["dark"])
        self._card.t = self._ring.t = t
        self._title.setStyleSheet(f"color: {t['fg']}; font-family: Bahnschrift, 'Segoe UI'; "
                                  "font-size: 21px; font-weight: 700; background: transparent;")
        self._settings.setStyleSheet(f"color: {t['fg3']}; font-size: 12px; background: transparent;")
        self._cap_dir.setStyleSheet(f"color: {t['fg3']}; font-size: 10px; font-weight: 700; "
                                    "letter-spacing: 1.2px; background: transparent;")
        self._lbl_dir.setStyleSheet(f"color: {t['fg']}; font-size: 16px; font-weight: 600; "
                                    "background: transparent;")
        self._lbl_file.setStyleSheet(f"color: {t['fg3']}; font-size: 12px; background: transparent;")
        self._lbl_errors.setStyleSheet("color: #f87171; font-size: 12px; font-weight: 600; "
                                       "background: transparent;")
        self._ico_dir.setPixmap(icon("folder", _GRAD[0] if theme == "light" else "#a78bfa", 18)
                                .pixmap(18, 18))
        self._btn_cancel.setIcon(icon("stop", t["fg2"], 14))
        for st in (self._st_elapsed, self._st_left):
            st.style(t)
        self._st_gain.style(t, "#4ade80" if theme != "light" else "#16a34a")
        self._card.update()
        self.update()

    # ── API ───────────────────────────────────────────────────────────────────

    def start(self, files: Iterable[Tuple[str, int]], root: str, settings_label: str):
        self._sizes = dict(files)
        self._n_total = len(self._sizes)
        self._total_bytes = max(1, sum(self._sizes.values()))
        self._done_bytes = self._n_done = self._n_failed = self._saved = 0
        self._inflight = {}
        self._root = os.path.normpath(root) if root else ""
        self._phase = None
        self._t0 = time.monotonic()
        self._title.setText("Conversion en cours")
        self._settings.setText(settings_label)
        self._lbl_dir.setText("Démarrage…")
        self._lbl_file.setText("")
        self._lbl_errors.setText("")
        self._btn_cancel.setEnabled(True)
        self._btn_cancel.setText(" Annuler")
        self._ring.target = 0.0
        self._ring._shown = 0.0
        self._ring.running = True
        self._update_stats()
        self._sync_geometry()
        self.raise_()
        self.show()
        self._anim.stop()
        self._anim.setStartValue(self._fx.opacity())
        self._anim.setEndValue(1.0)
        self._anim.start()
        self._timer.start()

    def file_started(self, path: str):
        self._inflight[path] = None
        self._update_current()

    def file_done(self, path: str, success: bool, saved: int = 0):
        self._inflight.pop(path, None)
        self._n_done += 1
        self._done_bytes += self._sizes.get(path, 0)
        if success:
            self._saved += saved
        else:
            self._n_failed += 1
            self._lbl_errors.setText(f"{self._n_failed} erreur{'s' if self._n_failed > 1 else ''}"
                                     " — détails dans le récapitulatif")
        self._ring.target = self._done_bytes / self._total_bytes
        self._update_current()

    def set_phase(self, text: str):
        """Étape finale (ex. envoi à la corbeille) : l'anneau est plein."""
        self._phase = text
        self._title.setText(text)
        self._ring.target = 1.0
        self._lbl_dir.setText("—")
        self._lbl_file.setText("")
        self._btn_cancel.setEnabled(False)

    def set_cancelling(self):
        self._btn_cancel.setEnabled(False)
        self._btn_cancel.setText(" Annulation…")
        self._title.setText("Annulation en cours…")

    def finish(self):
        self._ring.running = False
        self._timer.stop()
        self._anim.stop()
        self._anim.setStartValue(self._fx.opacity())
        self._anim.setEndValue(0.0)
        self._anim.start()

    # ── Interne ───────────────────────────────────────────────────────────────

    def _on_cancel(self):
        self.set_cancelling()
        self.cancel_requested.emit()

    def _on_anim_done(self):
        if self._fx.opacity() <= 0.01:
            self.hide()

    def _on_tick(self):
        self._ring.tick()
        self._ticks += 1
        if self._ticks % 15 == 0:           # ~4 fois par seconde
            self._update_stats()

    def _rel(self, directory: str) -> str:
        d = os.path.normpath(directory)
        if self._root:
            try:
                rel = os.path.relpath(d, self._root)
            except ValueError:
                return d
            if rel == ".":
                return os.path.basename(self._root) or self._root
            if not rel.startswith(".."):
                return rel
        return d

    def _update_current(self):
        if self._phase:
            return
        if not self._inflight:
            if self._n_done >= self._n_total:
                self._lbl_dir.setText("Finalisation…")
                self._lbl_file.setText("")
            return
        # Les fichiers d'un dossier se suivent : le plus ancien en cours donne le dossier
        paths = list(self._inflight)
        dirs = []
        for p in paths:
            d = os.path.dirname(p)
            if d not in dirs:
                dirs.append(d)
        name = self._rel(dirs[0])
        more = f"  (+{len(dirs) - 1})" if len(dirs) > 1 else ""
        fm = QFontMetrics(self._lbl_dir.font())
        avail = max(60, self._lbl_dir.width() - fm.horizontalAdvance(more) - 4)
        self._lbl_dir.setText(fm.elidedText(name, Qt.TextElideMode.ElideMiddle, avail) + more)
        self._lbl_dir.setToolTip(dirs[0])
        names = ", ".join(os.path.basename(p) for p in paths[:3])
        if len(paths) > 3:
            names += f"  +{len(paths) - 3}"
        ff = QFontMetrics(self._lbl_file.font())
        self._lbl_file.setText(ff.elidedText(names, Qt.TextElideMode.ElideRight,
                                             max(60, self._lbl_file.width())))

    def _update_stats(self):
        el = time.monotonic() - self._t0
        self._st_elapsed.val.setText(_dur(el))
        frac = self._done_bytes / self._total_bytes
        if self._phase:
            self._st_left.val.setText("—")
        elif self._n_done >= 2 and el >= 3 and frac > 0:
            self._st_left.val.setText(_eta(el / frac - el))
        else:
            self._st_left.val.setText("calcul…")
        self._st_gain.val.setText(("−" + fmt_bytes(self._saved)) if self._saved >= 0
                                  else ("+" + fmt_bytes(-self._saved)))
        self._ring.sub = f"{self._n_done} / {self._n_total} fichiers"
        self._ring.update()

    def _sync_geometry(self):
        self.setGeometry(self._cover.geometry())

    def eventFilter(self, obj, event):
        if obj is self._cover and event.type() in (QEvent.Type.Resize, QEvent.Type.Move):
            self._sync_geometry()
        return False

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(QRectF(self.rect()), 14, 14)
        p.fillPath(path, self.t["scrim"])

    # Le voile capte la souris : rien ne passe à la liste dessous
    def mousePressEvent(self, e):
        e.accept()

    def wheelEvent(self, e):
        e.accept()


# ── Chargement d'un dossier ──────────────────────────────────────────────────

class _Spin(QWidget):
    """Arc dégradé qui tourne (chargement à durée inconnue)."""

    def __init__(self, size: int = 64, parent=None):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self._a = 0.0
        self.t = _THEMES["dark"]

    def step(self):
        self._a = (self._a + 6) % 360
        self.update()

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        stroke = 6
        r = QRectF(self.rect()).adjusted(stroke, stroke, -stroke, -stroke)
        p.setPen(QPen(self.t["track"], stroke))
        p.drawEllipse(r)
        g = QConicalGradient(r.center(), -self._a)
        g.setColorAt(0.0, QColor(_GRAD[1]))
        g.setColorAt(0.35, QColor(_GRAD[0]))
        c = QColor(_GRAD[0]); c.setAlpha(0)
        g.setColorAt(0.36, c)
        g.setColorAt(1.0, c)
        pen = QPen(g, stroke)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        p.drawArc(r, int(-self._a * 16), int(0.34 * 360 * 16))


class ScanOverlay(QWidget):
    """Posé sur la liste pendant la lecture d'un dossier (l'ancien contenu est déjà vidé)."""

    def __init__(self, cover: QWidget, theme: str = "dark"):
        super().__init__(cover.parentWidget())
        self._cover = cover
        cover.installEventFilter(self)
        self.hide()
        self._root = ""

        lay = QVBoxLayout(self)
        lay.addStretch(1)
        self._spin = _Spin()
        lay.addWidget(self._spin, 0, Qt.AlignmentFlag.AlignHCenter)
        lay.addSpacing(14)
        self._title = QLabel()
        self._title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self._title)
        self._sub = QLabel()
        self._sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self._sub)
        lay.addStretch(1)

        self._fx = QGraphicsOpacityEffect(self)
        self._fx.setOpacity(0.0)
        self.setGraphicsEffect(self._fx)
        self._anim = QPropertyAnimation(self._fx, b"opacity", self)
        self._anim.setDuration(160)
        self._anim.finished.connect(lambda: self._fx.opacity() <= 0.01 and self.hide())

        self._timer = QTimer(self)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self._spin.step)
        # Un dossier qui se lit en un éclair ne doit pas faire clignoter l'animation
        self._delay = QTimer(self)
        self._delay.setSingleShot(True)
        self._delay.setInterval(140)
        self._delay.timeout.connect(self._appear)
        self.set_theme(theme)

    def set_theme(self, theme: str):
        t = self.t = _THEMES.get(theme, _THEMES["dark"])
        self._spin.t = t
        self._title.setStyleSheet(f"color: {t['fg']}; font-family: Bahnschrift, 'Segoe UI'; "
                                  "font-size: 18px; font-weight: 600; background: transparent;")
        self._sub.setStyleSheet(f"color: {t['fg3']}; font-size: 12px; background: transparent;")

    def start(self, root: str, what: str = "fichiers trouvés"):
        self._root = os.path.normpath(root)
        self._what = what
        name = os.path.basename(self._root) or self._root
        self._title.setText(f"Chargement de « {name} »…")
        self._sub.setText("Lecture du dossier")
        self._delay.start()

    def set_progress(self, n: int, directory: str):
        try:
            rel = os.path.relpath(directory, self._root) if self._root else directory
        except ValueError:
            rel = directory
        where = "" if rel == "." else f"   ·   {rel}"
        fm = QFontMetrics(self._sub.font())
        text = f"{n:,}".replace(",", "\u202f") + f" {self._what}{where}"
        self._sub.setText(fm.elidedText(text, Qt.TextElideMode.ElideMiddle,
                                        max(200, self.width() - 80)))

    def stop(self):
        self._delay.stop()
        if not self.isVisible():
            return
        self._timer.stop()
        self._anim.stop()
        self._anim.setStartValue(self._fx.opacity())
        self._anim.setEndValue(0.0)
        self._anim.start()

    def _appear(self):
        self.setGeometry(self._cover.geometry())
        self.raise_()
        self.show()
        self._timer.start()
        self._anim.stop()
        self._anim.setStartValue(self._fx.opacity())
        self._anim.setEndValue(1.0)
        self._anim.start()

    def eventFilter(self, obj, event):
        if obj is self._cover and event.type() in (QEvent.Type.Resize, QEvent.Type.Move):
            self.setGeometry(self._cover.geometry())
        return False

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(QRectF(self.rect()), 14, 14)
        c = QColor(self.t["scrim"])
        c.setAlpha(120)
        p.fillPath(path, c)

    def mousePressEvent(self, e):
        e.accept()
