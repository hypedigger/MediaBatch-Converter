"""
Rendu commun des listes (tableau audio, arborescence images) : lignes
alternées, survol de la ligne entière et texte coloré par cellule.

La feuille de style (::item { color: … }) écrase les couleurs posées avec
setForeground() : le délégué dessine donc lui-même le texte des cellules qui
portent une couleur (rôle ACCENT_ROLE).
"""

from PyQt6.QtCore    import Qt, QEvent, QObject, QRect, QPersistentModelIndex
from PyQt6.QtGui     import QColor
from PyQt6.QtWidgets import (QStyledItemDelegate, QStyleOptionViewItem, QStyle,
                              QAbstractItemView, QApplication)

ACCENT_ROLE = Qt.ItemDataRole.UserRole + 1     # QColor du texte de la cellule

_TINTS = {
    #        ligne paire / impaire          survol
    "dark":  (QColor(255, 255, 255, 0), QColor(255, 255, 255, 7), QColor(150, 120, 255, 30)),
    "light": (QColor(0, 0, 0, 0),       QColor(60, 40, 140, 10),  QColor(110, 88, 220, 28)),
}


class _RowDelegate(QStyledItemDelegate):
    def __init__(self, view: QAbstractItemView):
        super().__init__(view)
        self._view = view
        self.hover = QPersistentModelIndex()     # 1re cellule de la ligne survolée
        self.theme = "dark"

    def _is_hover(self, index) -> bool:
        return self.hover.isValid() and index.siblingAtColumn(0) == self.hover

    def paint(self, painter, option, index):
        even, odd, hover = _TINTS.get(self.theme, _TINTS["dark"])
        # Alternance selon la position à l'écran (vaut aussi pour une arborescence)
        h = max(option.rect.height(), 1)
        visual_row = (option.rect.top() + self._view.verticalScrollBar().value()) // h
        bg = hover if self._is_hover(index) else (odd if visual_row % 2 else even)
        if bg.alpha():
            painter.fillRect(option.rect, bg)

        accent = index.data(ACCENT_ROLE)
        if not isinstance(accent, QColor):
            super().paint(painter, option, index)
            return

        # Fond / sélection par le style, texte dessiné ici dans la couleur voulue
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        text, opt.text = opt.text, ""
        style = opt.widget.style() if opt.widget else QApplication.style()
        style.drawControl(QStyle.ControlElement.CE_ItemViewItem, opt, painter, opt.widget)
        painter.save()
        painter.setPen(accent)
        f = painter.font()
        f.setBold(True)
        painter.setFont(f)
        r = QRect(opt.rect).adjusted(8, 0, -8, -3)         # padding de ::item, aligné sur le texte voisin
        painter.drawText(r, int(opt.displayAlignment), text)
        painter.restore()


class _HoverTracker(QObject):
    def __init__(self, view: QAbstractItemView, delegate: _RowDelegate):
        super().__init__(view)
        self._view, self._delegate = view, delegate

    def eventFilter(self, obj, event):
        t = event.type()
        if t == QEvent.Type.MouseMove:
            idx = self._view.indexAt(event.position().toPoint())
            new = QPersistentModelIndex(idx.siblingAtColumn(0)) if idx.isValid() \
                else QPersistentModelIndex()
            if new != self._delegate.hover:
                self._delegate.hover = new
                self._view.viewport().update()
        elif t == QEvent.Type.Leave and self._delegate.hover.isValid():
            self._delegate.hover = QPersistentModelIndex()
            self._view.viewport().update()
        return False


def style_table(view: QAbstractItemView, theme: str = "dark"):
    """Installe (ou met à jour le thème de) le rendu commun sur *view*."""
    delegate = getattr(view, "_row_delegate", None)
    if delegate is None:
        delegate = _RowDelegate(view)
        view._row_delegate = delegate
        view.setItemDelegate(delegate)
        view.setMouseTracking(True)
        # Défilement au pixel : l'alternance des lignes reste calée
        view.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        tracker = _HoverTracker(view, delegate)
        view._hover_tracker = tracker
        view.viewport().installEventFilter(tracker)
    delegate.theme = theme
    view.viewport().update()


def set_hover_row(view: QAbstractItemView, index):
    """Force la ligne survolée (captures d'écran)."""
    view._row_delegate.hover = QPersistentModelIndex(index.siblingAtColumn(0))
    view.viewport().update()
