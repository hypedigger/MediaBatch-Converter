"""
Icône de l'app, dessinée en vectoriel (net à toutes les tailles) :
une photo turquoise inclinée derrière une note de musique violette,
pour les deux modes Audio / Images.

Régénérer assets/app.ico (exe, raccourci) :  python -m ui.icon
"""

from PyQt6.QtGui  import (QIcon, QPixmap, QPainter, QColor, QLinearGradient, QBrush,
                          QPen, QPainterPath, QPolygonF)
from PyQt6.QtCore import Qt, QRectF, QPointF

_SIZES = (16, 24, 32, 48, 64, 128, 256)


def _render_icon(size: int) -> QPixmap:
    pix = QPixmap(size, size)
    pix.fill(Qt.GlobalColor.transparent)
    s = float(size)

    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)

    # Fond : carré arrondi violet sombre
    grad = QLinearGradient(0, 0, s, s)
    grad.setColorAt(0.0, QColor(30, 16, 70))
    grad.setColorAt(1.0, QColor(62, 32, 122))
    p.setBrush(QBrush(grad))
    p.setPen(Qt.PenStyle.NoPen)
    radius = s * 0.22
    p.drawRoundedRect(QRectF(0, 0, s, s), radius, radius)

    rim = QLinearGradient(0, 0, s, s)
    rim.setColorAt(0.0, QColor(170, 120, 255, 70))
    rim.setColorAt(1.0, QColor(80, 40, 180, 20))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.setPen(QPen(QBrush(rim), max(1.0, s / 32)))
    p.drawRoundedRect(QRectF(1, 1, s - 2, s - 2), radius - 1, radius - 1)

    # ── Photo (arrière-plan, inclinée) ───────────────────────────────────────
    p.save()
    p.translate(s * 0.62, s * 0.37)
    p.rotate(9)
    w, h = s * 0.56, s * 0.44
    card = QRectF(-w / 2, -h / 2, w, h)
    card_grad = QLinearGradient(card.topLeft(), card.bottomRight())
    card_grad.setColorAt(0.0, QColor(40, 200, 175))
    card_grad.setColorAt(1.0, QColor(30, 150, 200))
    p.setPen(QPen(QColor(235, 255, 250, 230), max(1.0, s * 0.03)))
    p.setBrush(QBrush(card_grad))
    p.drawRoundedRect(card, s * 0.05, s * 0.05)

    # Soleil
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(255, 230, 140))
    r_sun = s * 0.055
    p.drawEllipse(QPointF(w * 0.22, -h * 0.20), r_sun, r_sun)

    # Montagnes
    p.setBrush(QColor(230, 255, 248, 235))
    base = h / 2 - s * 0.03
    mountains = QPolygonF([
        QPointF(-w / 2 + s * 0.03, base),
        QPointF(-w * 0.12, -h * 0.10),
        QPointF(w * 0.08, base * 0.45),
        QPointF(w * 0.24, h * 0.02),
        QPointF(w / 2 - s * 0.03, base),
    ])
    p.drawPolygon(mountains)
    p.restore()

    # ── Note de musique (premier plan) ───────────────────────────────────────
    note = QPainterPath()
    stem_w = s * 0.075
    head_rx, head_ry = s * 0.125, s * 0.095
    x1, x2 = s * 0.30, s * 0.58                # tiges gauche / droite
    top1, top2 = s * 0.42, s * 0.35            # haut des tiges (barre inclinée)
    y1, y2 = s * 0.79, s * 0.72                # centres des têtes
    beam_h = s * 0.11

    # Barre
    note.addPolygon(QPolygonF([
        QPointF(x1, top1), QPointF(x2 + stem_w, top2),
        QPointF(x2 + stem_w, top2 + beam_h), QPointF(x1, top1 + beam_h),
    ]))
    # Tiges
    note.addRect(QRectF(x1, top1, stem_w, y1 - top1))
    note.addRect(QRectF(x2, top2, stem_w, y2 - top2))
    # Têtes (ellipses légèrement inclinées, accrochées à droite des tiges)
    for cx, cy in ((x1 + stem_w - head_rx * 0.95, y1), (x2 + stem_w - head_rx * 0.95, y2)):
        head = QPainterPath()
        head.addEllipse(QPointF(0, 0), head_rx, head_ry)
        note.addPath(_rotated(head, -20, cx, cy))
    note.setFillRule(Qt.FillRule.WindingFill)     # fusionner les formes qui se chevauchent
    note = note.simplified()

    # Contour sombre : détache la note de la photo
    p.setPen(QPen(QColor(30, 16, 70), max(1.0, s * 0.028),
                  Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
    note_grad = QLinearGradient(0, s * 0.3, 0, s * 0.9)
    note_grad.setColorAt(0.0, QColor(225, 190, 255))
    note_grad.setColorAt(1.0, QColor(175, 125, 255))
    p.setBrush(QBrush(note_grad))
    p.drawPath(note)

    p.end()
    return pix


def _rotated(path: QPainterPath, deg: float, dx: float, dy: float) -> QPainterPath:
    from PyQt6.QtGui import QTransform
    t = QTransform()
    t.translate(dx, dy)
    t.rotate(deg)
    return t.map(path)


def create_app_icon() -> QIcon:
    icon = QIcon()
    for sz in _SIZES:
        icon.addPixmap(_render_icon(sz))
    return icon


def save_ico(path: str):
    """Écrit un .ico multi-tailles (via Pillow, à partir des rendus Qt)."""
    import io
    from PIL import Image
    from PyQt6.QtCore import QBuffer, QIODevice
    images = []
    for sz in _SIZES:
        buf = QBuffer()
        buf.open(QIODevice.OpenModeFlag.WriteOnly)
        _render_icon(sz).save(buf, "PNG")
        images.append(Image.open(io.BytesIO(bytes(buf.data()))).convert("RGBA"))
    images[-1].save(path, format="ICO", sizes=[(sz, sz) for sz in _SIZES],
                    append_images=images[:-1])


if __name__ == "__main__":
    import os, sys
    from PyQt6.QtWidgets import QApplication
    app = QApplication(sys.argv)
    out = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "assets", "app.ico")
    save_ico(out)
    print("OK ->", out)
