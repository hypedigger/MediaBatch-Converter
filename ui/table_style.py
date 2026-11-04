"""
Rendu commun des tableaux : lignes alternées, survol de la ligne entière
et texte coloré par cellule.

La feuille de style (QTableWidget::item { color: … }) écrase les couleurs
posées avec setForeground() : le délégué dessine donc lui-même le texte des
cellules qui portent une couleur (rôle ACCENT_ROLE).
"""

from PyQt6.QtCore    import Qt, QEvent, QObject, QRect
from PyQt6.QtGui     import QColor
from PyQt6.QtWidgets import (QStyledItemDelegate, QStyleOptionViewItem, QStyle,
                              QTableWidget, QApplication)

ACCENT_ROLE = Qt.ItemDataRole.UserRole + 1     # QColor du texte de la cellule

_TINTS = {
    #        ligne paire / impaire          survol
    "dark":  (QColor(255, 255, 255, 0), QColor(255, 255, 255, 7), QColor(150, 120, 255, 30)),
    "light": (QColor(0, 0, 0, 0),       QColor(60, 40, 140, 10),  QColor(110, 88, 220, 28)),
}


class _RowDelegate(QStyledItemDelegate):
    def __init__(self, table: QTableWidget):
        super().__init__(table)
        self._table = table
        self.hover_row = -1
        self.theme = "dark"

    def paint(self, painter, option, index):
        even, odd, hover = _TINTS.get(self.theme, _TINTS["dark"])
        bg = hover if index.row() == self.hover_row else (odd if index.row() % 2 else even)
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
    def __init__(self, table: QTableWidget, delegate: _RowDelegate):
        super().__init__(table)
        self._table, self._delegate = table, delegate

    def eventFilter(self, obj, event):
        t = event.type()
        if t == QEvent.Type.MouseMove:
            row = self._table.rowAt(int(event.position().y()))
            if row != self._delegate.hover_row:
                self._delegate.hover_row = row
                self._table.viewport().update()
        elif t == QEvent.Type.Leave and self._delegate.hover_row != -1:
            self._delegate.hover_row = -1
            self._table.viewport().update()
        return False


def style_table(table: QTableWidget, theme: str = "dark"):
    """Installe (ou met à jour le thème de) le rendu commun sur *table*."""
    delegate = getattr(table, "_row_delegate", None)
    if delegate is None:
        delegate = _RowDelegate(table)
        table._row_delegate = delegate
        table.setItemDelegate(delegate)
        table.setMouseTracking(True)
        tracker = _HoverTracker(table, delegate)
        table._hover_tracker = tracker
        table.viewport().installEventFilter(tracker)
    delegate.theme = theme
    table.viewport().update()
