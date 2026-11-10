"""
Récapitulatif de fin de conversion : badge d'état, gain d'espace en grand
(dégradé de l'accueil), barres avant / après, compteurs et erreurs éventuelles.
"""

import os
import subprocess

from PyQt6.QtCore    import Qt, QRectF, QPointF, QSize
from PyQt6.QtGui     import (QColor, QFont, QFontMetrics, QLinearGradient, QPainter,
                             QPainterPath, QPen, QBrush)
from PyQt6.QtWidgets import (QDialog, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
                             QLabel, QPushButton, QScrollArea, QFrame, QSizePolicy)

from ui.icons      import icon
from ui.image_tree import fmt_bytes, gain_color

_GRAD = ("#7c3aed", "#06b6d4", "#ec4899")      # dégradé de l'écran d'accueil
_FG, _FG2, _FG3 = "#ffffff", "#b4bccb", "#7d8496"


def _duration(sec: float) -> str:
    sec = int(round(sec))
    if sec < 60:
        return f"{sec} s"
    return f"{sec // 60} min {sec % 60:02d} s"


class _Badge(QWidget):
    """Pastille ronde en dégradé : coche (succès), ! (erreurs) ou carré (arrêt)."""

    def __init__(self, kind: str):
        super().__init__()
        self._kind = kind
        self.setFixedSize(60, 60)

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(2, 2, 56, 56)
        if self._kind == "ok":
            g = QLinearGradient(r.topLeft(), r.bottomRight())
            g.setColorAt(0, QColor("#22c55e")); g.setColorAt(1, QColor("#06b6d4"))
        elif self._kind == "warn":
            g = QLinearGradient(r.topLeft(), r.bottomRight())
            g.setColorAt(0, QColor("#f59e0b")); g.setColorAt(1, QColor("#ec4899"))
        else:
            g = QLinearGradient(r.topLeft(), r.bottomRight())
            g.setColorAt(0, QColor("#64748b")); g.setColorAt(1, QColor("#7c3aed"))
        # Halo
        halo = QColor(g.stops()[0][1]); halo.setAlpha(60)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(halo)
        p.drawEllipse(QRectF(0, 0, 60, 60))
        p.setBrush(QBrush(g))
        p.drawEllipse(r.adjusted(3, 3, -3, -3))
        pen = QPen(QColor("white"), 4.2, cap=Qt.PenCapStyle.RoundCap, join=Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)
        c = r.center()
        if self._kind == "ok":
            p.drawPolyline([c + QPointF(-11, 1), c + QPointF(-3, 9), c + QPointF(12, -8)])
        elif self._kind == "warn":
            p.drawLine(c + QPointF(0, -11), c + QPointF(0, 3))
            p.drawPoint(c + QPointF(0, 11))
        else:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor("white"))
            p.drawRoundedRect(QRectF(c.x() - 8, c.y() - 8, 16, 16), 3, 3)
        p.end()


class _GradientNumber(QWidget):
    """Grand chiffre en dégradé (comme le titre de l'accueil)."""

    def __init__(self, text: str, colors=_GRAD):
        super().__init__()
        self._text, self._colors = text, colors
        self._font = QFont("Bahnschrift", 40, QFont.Weight.Bold)
        fm = QFontMetrics(self._font)
        self.setFixedHeight(fm.height() + 4)
        self.setMinimumWidth(fm.horizontalAdvance(text) + 8)

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        fm = QFontMetrics(self._font)
        w = fm.horizontalAdvance(self._text)
        g = QLinearGradient(0, 0, max(w, 1), 0)
        for pos, col in zip((0.0, 0.55, 1.0), self._colors):
            g.setColorAt(pos, QColor(col))
        path = QPainterPath()
        path.addText(0, fm.ascent(), self._font, self._text)
        p.fillPath(path, QBrush(g))
        p.end()


class _CompareBars(QWidget):
    """Deux barres proportionnelles : avant / après."""

    def __init__(self, before: int, after: int):
        super().__init__()
        self._b, self._a = before, after
        self.setFixedHeight(64)

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        label_w, value_w = 56, 92
        bar_x = label_w
        bar_w = self.width() - label_w - value_w
        top = max(self._b, self._a, 1)
        rows = (("Avant", self._b, None), ("Après", self._a, _GRAD))
        f = QFont("Segoe UI", 10)
        fb = QFont("Segoe UI", 10, QFont.Weight.DemiBold)
        for i, (lbl, val, grad) in enumerate(rows):
            y = 6 + i * 30
            p.setFont(f)
            p.setPen(QColor(_FG3))
            p.drawText(QRectF(0, y, label_w, 20), Qt.AlignmentFlag.AlignVCenter, lbl)
            track = QRectF(bar_x, y + 5, bar_w, 10)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(255, 255, 255, 18))
            p.drawRoundedRect(track, 5, 5)
            fill = QRectF(bar_x, y + 5, max(8.0, bar_w * val / top), 10)
            if grad:
                g = QLinearGradient(fill.topLeft(), fill.topRight())
                g.setColorAt(0, QColor(grad[0])); g.setColorAt(1, QColor(grad[1]))
                p.setBrush(QBrush(g))
            else:
                p.setBrush(QColor(255, 255, 255, 70))
            p.drawRoundedRect(fill, 5, 5)
            p.setFont(fb)
            p.setPen(QColor(_FG))
            p.drawText(QRectF(self.width() - value_w, y, value_w, 20),
                       Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, fmt_bytes(val))
        p.end()


class SummaryDialog(QDialog):
    """
    *s* : total, success, skipped, failed [(nom, message)], src_size, out_size,
    recycled, recycle_error, cancelled, duration, fmt_label, folder.
    """

    def __init__(self, s: dict, dark: bool = True, parent=None):
        super().__init__(parent)
        self._s = s
        self._dark = dark
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedWidth(580)
        self._build()

    # ── Construction ──────────────────────────────────────────────────────────

    def _build(self):
        s = self._s
        n_ok, n_skip, n_fail = len(s["success"]), len(s["skipped"]), len(s["failed"])
        src, out = s["src_size"], s["out_size"]
        gain = src - out
        pct = (gain / src * 100) if src else 0.0

        if s.get("cancelled"):
            kind, title = "stop", "Conversion arrêtée"
        elif n_fail:
            kind, title = "warn", "Terminée avec des erreurs"
        else:
            kind, title = "ok", "Conversion terminée"

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        lay = QVBoxLayout()
        lay.setContentsMargins(32, 30, 32, 26)
        lay.setSpacing(0)
        outer.addLayout(lay)

        # En-tête : badge + titre + contexte
        head = QHBoxLayout()
        head.setSpacing(16)
        head.addWidget(_Badge(kind), 0, Qt.AlignmentFlag.AlignTop)
        tbox = QVBoxLayout()
        tbox.setSpacing(4)
        t = QLabel(title)
        t.setStyleSheet(f"color: {_FG}; font-family: Bahnschrift, 'Segoe UI'; font-size: 22px; font-weight: 700;")
        tbox.addWidget(t)
        done = n_ok + n_skip
        ctx = f"{done} fichier{'s' if done > 1 else ''} traité{'s' if done > 1 else ''}"
        if s.get("cancelled") and s.get("total"):
            ctx += f" sur {s['total']}"
        ctx += f"  ·  en {_duration(s.get('duration', 0))}"
        c = QLabel(ctx)
        c.setStyleSheet(f"color: {_FG2}; font-size: 13px;")
        tbox.addWidget(c)
        if s.get("fmt_label"):
            f = QLabel(s["fmt_label"])
            f.setWordWrap(True)
            f.setStyleSheet(f"color: {_FG3}; font-size: 12px;")
            tbox.addWidget(f)
        head.addLayout(tbox, 1)
        lay.addLayout(head)
        lay.addSpacing(26)

        # Le chiffre qui compte
        if done and src:
            if gain >= 0:
                num = _GradientNumber(f"−{fmt_bytes(gain)}")
                if s.get("recycled"):
                    cap = f"libérés sur le disque  ·  {pct:.0f} % de moins"
                else:
                    cap = f"de moins que les originaux  ·  {pct:.0f} %"
            else:
                num = _GradientNumber(f"+{fmt_bytes(-gain)}", ("#f59e0b", "#f97316", "#ec4899"))
                cap = "les fichiers convertis sont plus lourds que les originaux"
            lay.addWidget(num)
            capl = QLabel(cap)
            col = gain_color(pct).name() if gain >= 0 else "#fbbf24"
            capl.setStyleSheet(f"color: {col}; font-size: 14px; font-weight: 600;")
            lay.addWidget(capl)
            lay.addSpacing(18)
            lay.addWidget(_CompareBars(src, out))
            lay.addSpacing(16)

        # Compteurs
        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(10)
        chips = [("check", "#4ade80", n_ok, "converti" + ("s" if n_ok > 1 else ""))]
        if n_skip:
            chips.append(("select_none", "#93c5fd", n_skip, "gardés tels quels" if n_skip > 1 else "gardé tel quel"))
        if n_fail:
            chips.append(("close", "#f87171", n_fail, "erreur" + ("s" if n_fail > 1 else "")))
        if s.get("recycled"):
            chips.append(("trash", "#c4b5fd", s["recycled"], "à la corbeille"))
        for i, (ic, col, n, lbl) in enumerate(chips):
            grid.addWidget(self._chip(ic, col, n, lbl), i // 2, i % 2)
        lay.addLayout(grid)

        if s.get("recycle_error"):
            lay.addSpacing(10)
            w = QLabel("⚠  Les originaux n'ont pas tous pu être envoyés à la corbeille : ils sont restés en place.")
            w.setWordWrap(True)
            w.setStyleSheet("color: #fbbf24; font-size: 12px;")
            lay.addWidget(w)

        # Erreurs détaillées
        if n_fail:
            lay.addSpacing(16)
            h = QLabel("ERREURS")
            h.setStyleSheet("color: #f87171; font-size: 11px; font-weight: 700; letter-spacing: 1px;")
            lay.addWidget(h)
            lay.addSpacing(6)
            box = QWidget()
            bl = QVBoxLayout(box)
            bl.setContentsMargins(0, 0, 0, 0)
            bl.setSpacing(4)
            for name, msg in s["failed"]:
                e = QLabel(f"<b>{name}</b>  <span style='color:{_FG3}'>— {msg.strip()[:90]}</span>")
                e.setStyleSheet(f"color: {_FG2}; font-size: 12px;")
                e.setToolTip(msg)
                bl.addWidget(e)
            bl.addStretch()
            sc = QScrollArea()
            sc.setWidget(box)
            sc.setWidgetResizable(True)
            sc.setFrameShape(QFrame.Shape.NoFrame)
            sc.setMaximumHeight(min(130, 22 * n_fail + 8))
            sc.setStyleSheet("background: transparent;")
            lay.addWidget(sc)

        # Actions
        lay.addSpacing(24)
        row = QHBoxLayout()
        row.setSpacing(10)
        folder = s.get("folder", "")
        if folder and os.path.isdir(folder):
            b_open = QPushButton(" Ouvrir le dossier")
            b_open.setObjectName("sum_secondary")
            b_open.setIcon(icon("folder", _FG, 16))
            b_open.setIconSize(QSize(16, 16))
            b_open.setFixedHeight(42)
            b_open.setCursor(Qt.CursorShape.PointingHandCursor)
            b_open.clicked.connect(lambda: subprocess.Popen(["explorer", os.path.normpath(folder)]))
            row.addWidget(b_open)
        row.addStretch()
        b_ok = QPushButton("Terminé")
        b_ok.setObjectName("sum_primary")
        b_ok.setFixedHeight(42)
        b_ok.setMinimumWidth(140)
        b_ok.setDefault(True)
        b_ok.setCursor(Qt.CursorShape.PointingHandCursor)
        b_ok.clicked.connect(self.accept)
        row.addWidget(b_ok)
        lay.addLayout(row)

        self.setStyleSheet(f"""
            QPushButton#sum_secondary {{
                background: rgba(255,255,255,18); color: {_FG};
                border: 1px solid rgba(255,255,255,40); border-radius: 12px;
                padding: 0 16px; font-size: 13px; font-weight: 600;
            }}
            QPushButton#sum_secondary:hover {{ background: rgba(255,255,255,34); }}
            QPushButton#sum_primary {{
                border: none; border-radius: 12px; color: white;
                font-size: 14px; font-weight: 700; padding: 0 22px;
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 {_GRAD[0]}, stop:0.5 {_GRAD[1]}, stop:1 {_GRAD[2]});
            }}
            QPushButton#sum_primary:hover {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 {_GRAD[1]}, stop:0.5 {_GRAD[2]}, stop:1 {_GRAD[0]});
            }}
            QScrollArea, QScrollArea > QWidget > QWidget {{ background: transparent; }}
        """)

    def _chip(self, ic: str, color: str, n: int, label: str) -> QWidget:
        w = QFrame()
        w.setObjectName("sum_chip")
        w.setStyleSheet("QFrame#sum_chip { background: rgba(255,255,255,10); "
                        "border: 1px solid rgba(255,255,255,22); border-radius: 12px; }")
        l = QHBoxLayout(w)
        l.setContentsMargins(14, 10, 14, 10)
        l.setSpacing(10)
        i = QLabel()
        i.setPixmap(icon(ic, color, 18).pixmap(QSize(18, 18)))
        i.setStyleSheet("background: transparent; border: none;")
        l.addWidget(i)
        v = QLabel(f"<span style='font-size:18px; font-weight:700; color:{_FG}'>{n}</span>"
                   f"&nbsp;&nbsp;<span style='color:{_FG2}'>{label}</span>")
        v.setStyleSheet("background: transparent; border: none; font-size: 13px;")
        l.addWidget(v, 1)
        return w

    # ── Fond de carte ─────────────────────────────────────────────────────────

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        g = QLinearGradient(0, 0, r.width() * 0.5, r.height())
        g.setColorAt(0, QColor("#12121a"))
        g.setColorAt(1, QColor("#1e1e2c"))
        p.setPen(QPen(QColor(255, 255, 255, 34), 1))
        p.setBrush(QBrush(g))
        p.drawRoundedRect(r, 22, 22)
        # Liseré en dégradé en haut de la carte
        strip = QLinearGradient(r.left(), 0, r.right(), 0)
        for pos, col in zip((0.0, 0.5, 1.0), _GRAD):
            strip.setColorAt(pos, QColor(col))
        path = QPainterPath()
        path.addRoundedRect(r, 22, 22)
        p.setClipPath(path)
        p.fillRect(QRectF(r.left(), r.top(), r.width(), 4), QBrush(strip))
        p.end()

    def keyPressEvent(self, e):
        if e.key() in (Qt.Key.Key_Escape, Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.accept()
        else:
            super().keyPressEvent(e)
