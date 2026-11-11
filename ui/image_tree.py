"""
Liste du mode Images : une ligne repliée par dossier (ses images en dessous),
les images posées directement dans le dossier choisi apparaissant seules.
Le bouton « Estimer le gain d'espace » complète, dans cette même liste, les
colonnes taille estimée / gain / gain % / marge, dossier par dossier.
"""

import os
import subprocess
import time
import unicodedata
from collections import defaultdict
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from PyQt6.QtCore    import Qt, QTimer, QRectF, QPointF, QEvent, pyqtSignal
from PyQt6.QtGui     import QColor, QPainter, QPen
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTreeWidget,
                              QTreeWidgetItem, QHeaderView, QAbstractItemView, QMenu,
                              QMessageBox, QLineEdit)

from core.image_estimator import Estimate, GroupEstimateThread
from core.scanner         import FileInfo
from ui.table_style       import style_table, ACCENT_ROLE
from ui.icons             import icon, PALETTE


# ── Formatage ────────────────────────────────────────────────────────────────

def fmt_bytes(b: float) -> str:
    sign = "−" if b < 0 else ""
    b = abs(b)
    if b >= 1_073_741_824: return f"{sign}{b/1_073_741_824:.2f} Go"
    if b >= 1_048_576:     return f"{sign}{b/1_048_576:.1f} Mo"
    if b >= 1_024:         return f"{sign}{b/1_024:.0f} Ko"
    return f"{sign}{b:.0f} o"


# Intérêt de la conversion selon le gain : (seuil %, couleur, libellé)
GAIN_LEVELS = [
    (50, "#5fe39a", "très rentable"),
    (30, "#b5e46a", "rentable"),
    (15, "#f0c060", "modeste"),
    (-1e9, "#f07a7a", "peu utile"),
]


def gain_color(pct: float) -> QColor:
    return QColor(next(c for t, c, _ in GAIN_LEVELS if pct >= t))


def _gain_label(pct: float) -> str:
    return next(lbl for t, _c, lbl in GAIN_LEVELS if pct >= t)


def _n(v: int) -> str:
    return f"{v:,}".replace(",", " ")        # 12 345


def _short(path: str, width: int = 28) -> str:
    name = os.path.basename(os.path.normpath(path)) or path
    return name if len(name) <= width else name[: width - 1] + "…"


def _duration(sec: float) -> str:
    sec = int(sec)
    return f"{sec // 60} min {sec % 60:02d} s" if sec >= 60 else f"{sec} s"


# ── Colonnes ─────────────────────────────────────────────────────────────────

(C_NAME, C_COUNT, C_SIZE, C_DATE, C_EXT,
 C_EST, C_GAIN, C_PCT, C_MARGIN) = range(9)
_HEADERS = ["Nom", "Images", "Taille", "Date", "Ext.", "Taille compressée", "Gain estimé",
            "Gain %", "Marge"]
_DEFAULT_WIDTHS = {C_COUNT: 70, C_SIZE: 88, C_DATE: 130, C_EXT: 70,
                   C_EST: 150, C_GAIN: 110, C_PCT: 72, C_MARGIN: 86}
_MIN_WIDTH = 40


def _fold(text: str) -> str:
    """Minuscules sans accents, pour un filtre tolérant (« ecosse » → « Écosse »)."""
    return "".join(c for c in unicodedata.normalize("NFD", text.casefold())
                   if not unicodedata.combining(c))
_EST_COLS = (C_EST, C_GAIN, C_PCT, C_MARGIN)
_RIGHT = Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
_CENTER = Qt.AlignmentFlag.AlignCenter


class _Item(QTreeWidgetItem):
    """Ligne triable : chaque colonne peut porter une valeur de tri numérique."""

    def __init__(self):
        super().__init__()
        self.keys: Dict[int, float] = {}

    def set(self, col: int, text: str, key: Optional[float] = None, align=None):
        self.setText(col, text)
        if key is None:
            self.keys.pop(col, None)
        else:
            self.keys[col] = key
        if align is not None:
            self.setTextAlignment(col, align)

    def __lt__(self, other):
        col = self.treeWidget().sortColumn() if self.treeWidget() else 0
        a, b = self.keys.get(col), getattr(other, "keys", {}).get(col)
        if a is not None and b is not None:
            return a < b
        if (a is None) != (b is None):          # lignes sans valeur : toujours en bas
            return a is None if self.treeWidget().header().sortIndicatorOrder() \
                == Qt.SortOrder.DescendingOrder else b is None
        return self.text(col).lower() < other.text(col).lower()


class _Tree(QTreeWidget):
    """Arborescence avec chevrons dessinés (lisibles sur fond sombre)."""

    def drawBranches(self, painter, rect, index):
        item = self.itemFromIndex(index)
        if item is None or item.childCount() == 0:
            return
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor(190, 170, 255, 200), 1.8,
                            cap=Qt.PenCapStyle.RoundCap, join=Qt.PenJoinStyle.RoundJoin))
        c = QPointF(rect.right() - 11, rect.center().y())
        if item.isExpanded():
            pts = [c + QPointF(-4, -2), c + QPointF(0, 2), c + QPointF(4, -2)]
        else:
            pts = [c + QPointF(-2, -4), c + QPointF(2, 0), c + QPointF(-2, 4)]
        painter.drawPolyline(pts)
        painter.restore()


class _Spinner(QWidget):
    """Arc turquoise qui tourne pendant le calcul ; coche (ou carré) à la fin."""

    def __init__(self, size: int = 18):
        super().__init__()
        self.setFixedSize(size, size)
        self._angle = 0
        self._state = "idle"                 # "spin" | "done" | "stopped" | "idle"

    def step(self):
        self._state = "spin"
        self._angle = (self._angle + 30) % 360
        self.update()

    def set_state(self, state: str):
        self._state = state
        self.update()

    def paintEvent(self, _event):
        if self._state == "idle":
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(2, 2, self.width() - 4, self.height() - 4)
        color = QColor("#50d2be")
        if self._state == "spin":
            p.setPen(QPen(QColor(80, 210, 190, 50), 2.4))
            p.drawEllipse(r)
            p.setPen(QPen(color, 2.4, cap=Qt.PenCapStyle.RoundCap))
            p.drawArc(r, -self._angle * 16, 100 * 16)
        elif self._state == "done":
            p.setPen(QPen(color, 2.4, cap=Qt.PenCapStyle.RoundCap,
                          join=Qt.PenJoinStyle.RoundJoin))
            w, h = self.width(), self.height()
            p.drawPolyline([QPointF(w * .2, h * .55), QPointF(w * .42, h * .75),
                            QPointF(w * .8, h * .28)])
        else:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor("#f0c060"))
            p.drawRoundedRect(r.adjusted(3, 3, -3, -3), 2, 2)
        p.end()


# ── Panneau ──────────────────────────────────────────────────────────────────

class ImageTreePanel(QWidget):
    selection_changed = pyqtSignal()
    running_changed   = pyqtSignal(bool)      # estimation en cours / terminée
    activity_changed  = pyqtSignal()          # texte d'activité / légende modifiés
    estimate_finished = pyqtSignal(str)       # estimation menée à son terme : résumé

    def __init__(self, theme: str = "dark", parent=None):
        super().__init__(parent)
        self._theme = theme
        self._root  = ""
        # clé de groupe (dossier) → (ligne du dossier ou None, [(FileInfo, ligne)])
        self._groups: Dict[str, Tuple[Optional[_Item], List[Tuple[FileInfo, _Item]]]] = {}
        self._thread: Optional[GroupEstimateThread] = None
        self._hidden: set = set()           # groupes masqués par le filtre
        self._t0 = 0.0
        self._tot_src = self._tot_est = self._n_done = 0

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)

        # Ligne d'activité : ce qui se passe, ou ce qu'on peut faire. La fenêtre
        # principale peut remonter « activity » et « legend » sur la ligne des
        # cases à cocher quand la place le permet (voir act_row / act_layout)
        self.act_row = QWidget()
        act = QHBoxLayout(self.act_row)
        self.act_layout = act
        act.setContentsMargins(4, 0, 4, 0)
        act.setSpacing(8)
        self.activity = QWidget()
        al = QHBoxLayout(self.activity)
        al.setContentsMargins(0, 0, 0, 0)
        al.setSpacing(8)
        self._spinner = _Spinner()
        al.addWidget(self._spinner)
        self._lbl_activity = QLabel()
        self._lbl_activity.setObjectName("label_activity")
        al.addWidget(self._lbl_activity, 1)
        act.addWidget(self.activity, 1)
        self._legend = QLabel("&nbsp;&nbsp;".join(
            f'<span style="color:{c}">●</span> {"&lt; 15" if t < 0 else f"≥ {t}"} %'
            for t, c, _lbl in GAIN_LEVELS))
        self._legend.setToolTip("\n".join(
            f'{"< 15" if t < 0 else f"≥ {t}"} % : {lbl}' for t, _c, lbl in GAIN_LEVELS))
        self._legend.setObjectName("label_desc")
        self._legend.hide()
        act.addWidget(self._legend)
        self.legend = self._legend
        lay.addWidget(self.act_row)

        self._tree = _Tree()
        self._tree.setColumnCount(len(_HEADERS))
        self._tree.setHeaderLabels(_HEADERS)
        self._tree.setUniformRowHeights(True)
        self._tree.setIndentation(22)
        self._tree.setRootIsDecorated(True)
        self._tree.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self._tree.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._tree.setSortingEnabled(True)
        self._tree.sortByColumn(C_NAME, Qt.SortOrder.AscendingOrder)
        hdr = self._tree.header()
        hdr.setStretchLastSection(False)
        hdr.setSectionResizeMode(C_NAME, QHeaderView.ResizeMode.Stretch)
        hdr.setMinimumSectionSize(_MIN_WIDTH)
        # Colonnes redimensionnables à la souris (double-clic sur le séparateur :
        # largeur ajustée au contenu) ; largeurs mémorisées dans les réglages
        for col, w in _DEFAULT_WIDTHS.items():
            hdr.setSectionResizeMode(col, QHeaderView.ResizeMode.Interactive)
            self._tree.setColumnWidth(col, w)
        self._tree.headerItem().setToolTip(C_EST, "Poids estimé des images après conversion")
        self._tree.headerItem().setToolTip(C_GAIN, "Espace libéré estimé (taille actuelle − taille compressée)")
        for col in range(1, len(_HEADERS)):
            self._tree.headerItem().setTextAlignment(col, _CENTER)
        self._tree.itemChanged.connect(self._on_item_changed)
        self._tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._tree.customContextMenuRequested.connect(self._on_context_menu)
        style_table(self._tree, theme)
        lay.addWidget(self._make_filter_row())
        lay.addWidget(self._tree, 1)

        self._timer = QTimer(self)
        self._timer.setInterval(100)
        self._timer.timeout.connect(self._refresh_activity)

        # Plusieurs itemChanged en rafale (cases d'un dossier) → un seul signal
        self._sel_timer = QTimer(self)
        self._sel_timer.setSingleShot(True)
        self._sel_timer.setInterval(30)
        self._sel_timer.timeout.connect(self.selection_changed.emit)

        self._set_hint()

    # ── Remplissage ───────────────────────────────────────────────────────────

    def populate(self, files: List[FileInfo], root: str):
        self.cancel_estimate()
        self._root = os.path.normpath(root) if root else ""
        tree = self._tree
        tree.setSortingEnabled(False)
        tree.blockSignals(True)
        tree.clear()
        self._groups = {}

        by_dir: Dict[str, List[FileInfo]] = defaultdict(list)
        for fi in files:
            by_dir[os.path.normpath(fi.directory)].append(fi)

        for directory, group in by_dir.items():
            group.sort(key=lambda f: f.name.lower())
            loose = directory == self._root
            folder = None
            if not loose:
                folder = _Item()
                try:
                    rel = os.path.relpath(directory, self._root) if self._root else directory
                except ValueError:              # autre lecteur
                    rel = directory
                folder.set(C_NAME, rel if not rel.startswith("..") else directory)
                folder.setIcon(C_NAME, self._folder_icon())
                folder.setToolTip(C_NAME, directory)
                folder.setData(C_NAME, Qt.ItemDataRole.UserRole, ("dir", directory))
                folder.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable |
                                Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsAutoTristate)
                folder.setCheckState(C_NAME, Qt.CheckState.Unchecked)
                size = sum(f.size for f in group)
                folder.set(C_COUNT, _n(len(group)), len(group), _RIGHT)
                folder.set(C_SIZE, fmt_bytes(size), size, _RIGHT)
                last = max(f.date_created for f in group)
                folder.set(C_DATE, datetime.fromtimestamp(last).strftime("%d/%m/%Y  %H:%M"), last)
                exts = sorted({f.extension.upper() for f in group})
                folder.set(C_EXT, ", ".join(exts), None, _CENTER)
                folder.setToolTip(C_EXT, ", ".join(exts))
                tree.addTopLevelItem(folder)

            items = []
            for fi in group:
                it = _Item()
                it.set(C_NAME, fi.name)
                it.setToolTip(C_NAME, fi.path)
                it.setData(C_NAME, Qt.ItemDataRole.UserRole, fi)
                it.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable |
                            Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemNeverHasChildren)
                it.setCheckState(C_NAME, Qt.CheckState.Unchecked)
                it.set(C_SIZE, fi.size_str(), fi.size, _RIGHT)
                it.set(C_DATE, datetime.fromtimestamp(fi.date_created).strftime("%d/%m/%Y  %H:%M"),
                       fi.date_created)
                it.set(C_EXT, fi.extension.upper(), None, _CENTER)
                (folder.addChild if folder else tree.addTopLevelItem)(it)
                items.append((fi, it))
            self._groups[directory] = (folder, items)

        tree.blockSignals(False)
        tree.setSortingEnabled(True)
        self._hidden = set()
        if self._filter.text().strip():
            self._apply_filter()            # le filtre saisi s'applique au nouveau contenu
        else:
            self._lbl_filter.setText("")
        self._set_hint()
        self.selection_changed.emit()

    def clear(self):
        self.populate([], self._root)

    def file_count(self, visible_only: bool = False) -> int:
        if visible_only:
            return sum(len(items) for _k, _f, items in self._visible_groups())
        return sum(len(items) for _f, items in self._groups.values())

    def folder_count(self) -> int:
        return sum(1 for f, _items in self._groups.values() if f is not None)

    # ── Filtre des dossiers ───────────────────────────────────────────────────
    # Les dossiers masqués par le filtre sont hors jeu : ni cochés par « tout
    # sélectionner » / « Gain ≥ », ni convertis, ni estimés. Leurs cases sont
    # conservées et retrouvent leur effet quand le filtre est effacé.

    def _make_filter_row(self) -> QWidget:
        row = QWidget()
        h = QHBoxLayout(row)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(10)
        self._filter = QLineEdit()
        self._filter.setPlaceholderText("Filtrer les dossiers…")
        self._filter.setClearButtonEnabled(True)
        self._filter.setFixedWidth(340)
        self._filter.setFixedHeight(34)
        self._filter.setToolTip(
            "Affiche seulement les dossiers dont le nom contient ce texte\n"
            "(plusieurs mots : tous doivent y figurer ; accents et majuscules ignorés).\n"
            "Les dossiers masqués ne sont ni sélectionnés, ni estimés, ni convertis.\n"
            "Échap pour effacer.")
        self._filter_action = self._filter.addAction(
            icon("search", PALETTE[self._theme]["muted"], 16),
            QLineEdit.ActionPosition.LeadingPosition)
        self._filter_timer = QTimer(self)
        self._filter_timer.setSingleShot(True)
        self._filter_timer.setInterval(120)
        self._filter_timer.timeout.connect(self._apply_filter)
        self._filter.textChanged.connect(lambda _t: self._filter_timer.start())
        self._filter.installEventFilter(self)
        self._lbl_filter = QLabel()
        self._lbl_filter.setObjectName("label_desc")
        h.addWidget(self._filter)
        h.addWidget(self._lbl_filter)
        h.addStretch(1)
        return row

    def eventFilter(self, obj, event):
        if (obj is getattr(self, "_filter", None) and event.type() == QEvent.Type.KeyPress
                and event.key() == Qt.Key.Key_Escape and self._filter.text()):
            self._filter.clear()
            return True
        return super().eventFilter(obj, event)

    def filter_active(self) -> bool:
        return bool(self._filter.text().strip())

    def _apply_filter(self):
        words = _fold(self._filter.text()).split()
        hidden = set()
        n_dirs = n_shown = 0
        self._tree.setUpdatesEnabled(False)
        for key, (folder, items) in self._groups.items():
            if folder is not None:
                n_dirs += 1
                ok = all(w in _fold(folder.text(C_NAME)) for w in words)
                folder.setHidden(not ok)
                n_shown += ok
                if not ok:
                    hidden.add(key)
            else:
                # Images à la racine du dossier : filtrées sur leur nom
                any_ok = False
                for _fi, it in items:
                    ok = all(w in _fold(it.text(C_NAME)) for w in words)
                    it.setHidden(not ok)
                    any_ok = any_ok or ok
                if not any_ok and words:
                    hidden.add(key)
        self._tree.setUpdatesEnabled(True)
        self._hidden = hidden
        self._lbl_filter.setText(f"{n_shown} / {n_dirs} dossier(s) affiché(s)" if words else "")
        self.selection_changed.emit()

    def _visible_groups(self):
        for key, (folder, items) in self._groups.items():
            if key in self._hidden:
                continue
            if folder is None:
                items = [(fi, it) for fi, it in items if not it.isHidden()]
            yield key, folder, items

    # ── Sélection ─────────────────────────────────────────────────────────────

    def _file_items(self):
        for _folder, items in self._groups.values():
            yield from items

    def _visible_file_items(self):
        for _key, _folder, items in self._visible_groups():
            yield from items

    def checked_files(self) -> List[FileInfo]:
        return [fi for fi, it in self._visible_file_items()
                if it.checkState(C_NAME) == Qt.CheckState.Checked]

    def checked_count(self) -> int:
        return sum(1 for _fi, it in self._visible_file_items()
                   if it.checkState(C_NAME) == Qt.CheckState.Checked)

    def set_all_checked(self, state: bool):
        cs = Qt.CheckState.Checked if state else Qt.CheckState.Unchecked
        self._tree.blockSignals(True)
        for _key, folder, items in self._visible_groups():
            for _fi, it in items:
                it.setCheckState(C_NAME, cs)
            if folder is not None:
                folder.setCheckState(C_NAME, cs)
        self._tree.blockSignals(False)
        self._tree.viewport().update()
        self.selection_changed.emit()

    def has_estimates(self) -> bool:
        return any(C_PCT in it.keys for _fi, it in self._file_items())

    def select_by_gain(self, threshold: float) -> Tuple[int, int]:
        """
        Coche les dossiers dont le gain estimé atteint *threshold* % (les images
        isolées à la racine : chacune selon son propre gain), décoche le reste.
        Retourne (dossiers retenus, images cochées).
        """
        n_dirs = n_files = 0
        self._tree.blockSignals(True)
        for _key, folder, items in self._visible_groups():
            if folder is not None:
                ok = folder.keys.get(C_PCT, -1e9) >= threshold
                cs = Qt.CheckState.Checked if ok else Qt.CheckState.Unchecked
                folder.setCheckState(C_NAME, cs)
                for _fi, it in items:
                    it.setCheckState(C_NAME, cs)
                if ok:
                    n_dirs += 1
                    n_files += len(items)
            else:
                for _fi, it in items:
                    ok = it.keys.get(C_PCT, -1e9) >= threshold
                    it.setCheckState(C_NAME, Qt.CheckState.Checked if ok else Qt.CheckState.Unchecked)
                    n_files += ok
        self._tree.blockSignals(False)
        self._tree.viewport().update()
        self.selection_changed.emit()
        return n_dirs, n_files

    def _on_item_changed(self, _item, column):
        if column == C_NAME:
            self._sel_timer.start()

    # ── Estimation ────────────────────────────────────────────────────────────

    def is_running(self) -> bool:
        return bool(self._thread and self._thread.isRunning())

    def start_estimate(self, out_fmt, quality, max_side, keep, parallel):
        if not self._groups:
            return
        self.cancel_estimate(silent=True)
        self._clear_estimates()
        groups = {k: [fi for fi, _it in items] for k, _f, items in self._visible_groups()}
        if not groups:
            return
        self._tot_src = self._tot_est = self._n_done = 0
        self._t0 = time.monotonic()
        self._legend.show()
        self.activity_changed.emit()
        self._thread = GroupEstimateThread(groups, out_fmt, quality, max_side, keep, parallel)
        self._thread.group_done.connect(self._on_group_done)
        self._thread.all_done.connect(lambda: self._on_done(stopped=False))
        self._thread.start()
        self._timer.start()
        self._refresh_activity()
        self.running_changed.emit(True)

    def column_widths(self) -> dict:
        return {str(c): self._tree.columnWidth(c) for c in _DEFAULT_WIDTHS}

    def set_column_widths(self, widths: dict):
        for c in _DEFAULT_WIDTHS:
            w = (widths or {}).get(str(c))
            if isinstance(w, int) and w >= _MIN_WIDTH:
                self._tree.setColumnWidth(c, w)

    def cancel_estimate(self, silent: bool = False):
        th = self._thread
        if th and th.isRunning():
            # Un encodage en cours peut finir après l'arrêt : ses résultats
            # ne doivent plus arriver dans la liste
            th.group_done.disconnect()
            th.all_done.disconnect()
            th.cancel()
            th.wait(5000)
            if not silent:
                self._on_done(stopped=True)
            else:
                self._timer.stop()
                self.running_changed.emit(False)

    def mark_stale(self):
        """Réglages modifiés : les valeurs affichées ne correspondent plus."""
        if not self._groups:
            return
        if self.is_running():
            self.cancel_estimate(silent=True)
        if any(it.text(C_EST) for _fi, it in self._file_items()):
            self._clear_estimates()
            self._spinner.set_state("idle")
            self._set_activity(
                "Réglages modifiés : cliquez sur « Estimer le gain d'espace » pour mettre à jour "
                "les colonnes Taille compressée / Gain estimé.")

    def _clear_estimates(self):
        self._tree.setSortingEnabled(False)
        for folder, items in self._groups.values():
            rows = [it for _fi, it in items] + ([folder] if folder else [])
            for it in rows:
                for col in _EST_COLS:
                    it.set(col, "")
                    it.setData(col, ACCENT_ROLE, None)
                    it.setToolTip(col, "")
        self._tree.setSortingEnabled(True)

    def _on_group_done(self, key: str, est: Estimate):
        entry = self._groups.get(key)
        if entry is None:
            return
        folder, items = entry
        self._n_done += 1
        self._tot_src += est.src_bytes
        self._tot_est += est.est_bytes

        tree = self._tree
        tree.setSortingEnabled(False)            # sinon les lignes bougent pendant l'écriture
        if folder is not None:
            self._fill(folder, est.src_bytes, est.est_bytes)
            folder.set(C_MARGIN, "exacte" if est.exact else f"± {est.margin * 100:.0f} %",
                       0 if est.exact else est.margin, _RIGHT)
            tip = f"{est.n_samples} image(s) convertie(s) en test sur {est.n_files}, en mémoire"
            if est.headers_read < est.n_files:
                tip += (f"\nDossier volumineux et homogène : en-têtes lus sur "
                        f"{est.headers_read} images, le reste extrapolé d'après la taille")
            folder.setToolTip(C_MARGIN, tip)
        for (fi, it), (est_b, measured) in zip(items, est.per_file or []):
            self._fill(it, fi.size, est_b)
            it.set(C_MARGIN, "mesurée" if measured else "", 0 if measured else 1, _RIGHT)
            it.setToolTip(C_EST, "Mesurée par une conversion d'essai" if measured
                          else "Prédite d'après la qualité et la taille du fichier"
                          if measured is False
                          else "Extrapolée d'après la taille (dossier volumineux)")
        tree.setSortingEnabled(True)

    @staticmethod
    def _fill(it: _Item, src: int, est_b: int):
        gain = src - est_b
        pct = (gain / src * 100) if src else 0.0
        it.set(C_EST, "≈ " + fmt_bytes(est_b), est_b, _RIGHT)
        it.set(C_GAIN, fmt_bytes(gain), gain, _RIGHT)
        it.set(C_PCT, f"{pct:.0f} %", pct, _RIGHT)
        it.setData(C_PCT, ACCENT_ROLE, gain_color(pct))
        it.setToolTip(C_PCT, _gain_label(pct))

    def _on_done(self, stopped: bool):
        self._timer.stop()
        th = self._thread
        snap = th.snapshot() if th else {"samples": 0}
        gain = self._tot_src - self._tot_est
        pct = (gain / self._tot_src * 100) if self._tot_src else 0
        self._spinner.set_state("stopped" if stopped else "done")
        verb = "Analyse arrêtée après" if stopped else "Analyse terminée en"
        color = gain_color(pct).name()
        self._set_activity(
            f"{verb} {_duration(time.monotonic() - self._t0)}  —  "
            f"{fmt_bytes(self._tot_src)} → ≈ {fmt_bytes(self._tot_est)}  "
            f"<b style='color:{color}'>gain ≈ {fmt_bytes(gain)} ({pct:.0f} %)</b>  "
            f"·  {_n(snap['samples'])} conversion(s) d'essai, rien n'a été écrit sur le disque")
        if not stopped:
            # Plus gros gain en premier (modifiable en cliquant les en-têtes)
            self._tree.sortByColumn(C_GAIN, Qt.SortOrder.DescendingOrder)
        self.running_changed.emit(False)
        if not stopped:
            self.estimate_finished.emit(
                f"{fmt_bytes(self._tot_src)} → ≈ {fmt_bytes(self._tot_est)} : "
                f"gain ≈ {fmt_bytes(gain)} ({pct:.0f} %) en {_duration(time.monotonic() - self._t0)}")

    def _refresh_activity(self):
        th = self._thread
        if th is None:
            return
        snap = th.snapshot()
        self._spinner.step()
        parts = []
        # Les dossiers avancent en parallèle : les deux étapes se chevauchent
        if snap["headers"] < snap["total"]:
            parts.append(f"Lecture des en-têtes (dimensions, qualité JPEG) : "
                         f"{_n(snap['headers'])} / {_n(snap['total'])}")
        parts.append(f"conversions d'essai en mémoire : {_n(snap['samples'])}")
        parts.append(f"{_n(self._n_done)} / {_n(len(self._groups))} groupe(s) estimé(s)")
        text = "   ·   ".join(parts)
        cur = snap["current"]
        if cur:
            names = ", ".join(_short(d) for d in cur[:2])
            more = f" (+{len(cur) - 2})" if len(cur) > 2 else ""
            text += f"   ·   en cours : {names}{more}"
        self._set_activity(text[0].upper() + text[1:])

    def _set_activity(self, text: str):
        self._lbl_activity.setText(text)
        self.activity_changed.emit()

    def _set_hint(self):
        self._spinner.set_state("idle")
        self._legend.hide()
        if self._groups:
            self._set_activity(
                "Cliquez sur « Estimer le gain d'espace » pour calculer la taille après "
                "conversion de chaque dossier et de chaque image — sans rien modifier.")
        else:
            self._set_activity("")

    # ── Menu contextuel ───────────────────────────────────────────────────────

    def _on_context_menu(self, pos):
        item = self._tree.itemAt(pos)
        if item is None:
            return
        data = item.data(C_NAME, Qt.ItemDataRole.UserRole)
        menu = QMenu(self)
        mc = PALETTE.get(self._theme, PALETTE["dark"])["text"]
        if isinstance(data, tuple):                     # dossier
            directory = data[1]
            act_open = menu.addAction(icon("folder", mc, 16), "Ouvrir dans l'Explorateur")
            act_exp = menu.addAction(icon("expand", mc, 16), "Tout déplier")
            act_col = menu.addAction(icon("collapse", mc, 16), "Tout replier")
            action = menu.exec(self._tree.viewport().mapToGlobal(pos))
            if action == act_open:
                subprocess.Popen(["explorer", os.path.normpath(directory)])
            elif action == act_exp:
                self._tree.expandAll()
            elif action == act_col:
                self._tree.collapseAll()
        elif isinstance(data, FileInfo):
            act_file = menu.addAction(icon("image", mc, 16), "Ouvrir l'image")
            act_dir = menu.addAction(icon("folder", mc, 16), "Afficher dans l'Explorateur")
            action = menu.exec(self._tree.viewport().mapToGlobal(pos))
            if action == act_file:
                try:
                    os.startfile(data.path)
                except OSError as e:
                    QMessageBox.warning(self, "Erreur", f"Impossible d'ouvrir l'image :\n{e}")
            elif action == act_dir:
                subprocess.Popen(["explorer", "/select,", os.path.normpath(data.path)])

    # ── Thème ─────────────────────────────────────────────────────────────────

    def _folder_icon(self):
        return icon("folder", PALETTE.get(self._theme, PALETTE["dark"])["muted"], 16)

    def apply_theme(self, theme: str):
        self._theme = theme
        style_table(self._tree, theme)
        self._filter_action.setIcon(icon("search", PALETTE[theme]["muted"], 16))
        for folder, _items in self._groups.values():
            if folder is not None:
                folder.setIcon(C_NAME, self._folder_icon())

    @property
    def tree(self) -> QTreeWidget:
        return self._tree
