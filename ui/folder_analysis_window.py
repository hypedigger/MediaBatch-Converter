import os
import subprocess
from typing import Callable, Optional

from PyQt6.QtCore    import Qt, pyqtSignal
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                              QPushButton, QTableWidget, QTableWidgetItem,
                              QHeaderView, QAbstractItemView, QProgressBar, QMenu)

from core.image_estimator import Estimate, FolderAnalysisThread
from ui.effects           import apply_acrylic


def fmt_bytes(b: float) -> str:
    sign = "−" if b < 0 else ""
    b = abs(b)
    if b >= 1_073_741_824: return f"{sign}{b/1_073_741_824:.2f} Go"
    if b >= 1_048_576:     return f"{sign}{b/1_048_576:.1f} Mo"
    if b >= 1_024:         return f"{sign}{b/1_024:.0f} Ko"
    return f"{sign}{b:.0f} o"


class _NumItem(QTableWidgetItem):
    """Cellule affichant *label* mais triée selon *value*."""
    def __init__(self, value: float, label: str):
        super().__init__(label)
        self._value = value
        self.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
    def __lt__(self, other):
        if isinstance(other, _NumItem):
            return self._value < other._value
        return super().__lt__(other)


C_DIR, C_COUNT, C_SRC, C_EST, C_GAIN, C_PCT, C_MARGIN = range(7)


class FolderAnalysisWindow(QWidget):
    """
    Fenêtre « Analyser les sous-dossiers » : gain estimé par dossier, triable.
    *get_options* renvoie les réglages courants de la fenêtre principale :
    (racine, extensions, format, qualité, côté max, garder si plus léger, parallélisme, résumé).
    """

    load_requested = pyqtSignal(str)       # dossier à charger dans le convertisseur

    def __init__(self, get_options: Callable[[], tuple], theme: str = "dark", parent=None):
        super().__init__(parent)
        self._get_options = get_options
        self._theme       = theme
        self._thread: Optional[FolderAnalysisThread] = None
        self._root        = ""
        self._n_folders   = 0
        self._n_done      = 0
        self._tot_src     = 0
        self._tot_est     = 0
        self._drag_pos    = None

        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setMinimumSize(820, 480)
        self.resize(1000, 620)
        self.setWindowTitle("Analyse des sous-dossiers")
        self._build_ui()

    # ── UI ────────────────────────────────────────────────────────────────────

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        self._card = QWidget()
        self._card.setObjectName("central_widget")
        outer.addWidget(self._card)

        lay = QVBoxLayout(self._card)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        title_bar = QWidget()
        title_bar.setObjectName("title_bar")
        title_bar.setFixedHeight(40)
        tb_lay = QHBoxLayout(title_bar)
        tb_lay.setContentsMargins(16, 0, 8, 0)
        lbl = QLabel("🔍  Analyse des sous-dossiers — gain estimé")
        lbl.setObjectName("title_label")
        tb_lay.addWidget(lbl)
        tb_lay.addStretch()
        btn_close = QPushButton("✕")
        btn_close.setObjectName("btn_close")
        btn_close.clicked.connect(self.close)
        tb_lay.addWidget(btn_close)
        lay.addWidget(title_bar)

        title_bar.mousePressEvent   = self._tb_press
        title_bar.mouseMoveEvent    = self._tb_move
        title_bar.mouseReleaseEvent = self._tb_release

        content = QWidget()
        c_lay = QVBoxLayout(content)
        c_lay.setContentsMargins(14, 10, 14, 12)
        c_lay.setSpacing(8)

        self._lbl_opts = QLabel()
        self._lbl_opts.setObjectName("label_desc")
        self._lbl_opts.setWordWrap(True)
        c_lay.addWidget(self._lbl_opts)

        self._progress = QProgressBar()
        self._progress.setFixedHeight(8)
        self._progress.setTextVisible(False)
        c_lay.addWidget(self._progress)

        self._table = QTableWidget()
        self._table.setColumnCount(7)
        self._table.setHorizontalHeaderLabels(
            ["Dossier", "Images", "Actuel", "Estimé", "Gain", "Gain %", "Marge"]
        )
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setShowGrid(False)
        self._table.verticalHeader().setVisible(False)
        self._table.verticalHeader().setDefaultSectionSize(34)
        self._table.setSortingEnabled(True)
        hdr = self._table.horizontalHeader()
        hdr.setSectionResizeMode(C_DIR, QHeaderView.ResizeMode.Stretch)
        for col, w in ((C_COUNT, 70), (C_SRC, 95), (C_EST, 95), (C_GAIN, 95),
                       (C_PCT, 75), (C_MARGIN, 70)):
            hdr.setSectionResizeMode(col, QHeaderView.ResizeMode.Fixed)
            self._table.setColumnWidth(col, w)
        self._table.setToolTip("Double-clic : charger le dossier dans le convertisseur")
        self._table.cellDoubleClicked.connect(lambda r, _c: self._load_row(r))
        self._table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._table.customContextMenuRequested.connect(self._on_context_menu)
        c_lay.addWidget(self._table, 1)

        foot = QHBoxLayout()
        self._lbl_total = QLabel()
        self._lbl_total.setObjectName("label_count")
        foot.addWidget(self._lbl_total, 1)

        self._btn_rerun = QPushButton("↻  Relancer avec les réglages actuels")
        self._btn_rerun.clicked.connect(self.start)
        foot.addWidget(self._btn_rerun)

        self._btn_stop = QPushButton("⏹  Arrêter")
        self._btn_stop.clicked.connect(self._stop)
        foot.addWidget(self._btn_stop)
        c_lay.addLayout(foot)

        lay.addWidget(content, 1)

    # ── Analyse ───────────────────────────────────────────────────────────────

    def start(self):
        self._stop()
        root, exts, out_fmt, quality, max_side, keep, parallel, summary = self._get_options()
        self._root = root
        self._lbl_opts.setText(f"Racine : {root}\nSortie : {summary}")
        self._table.setSortingEnabled(False)
        self._table.setRowCount(0)
        self._n_folders = self._n_done = self._tot_src = self._tot_est = 0
        self._progress.setRange(0, 0)                 # indéterminé pendant le parcours
        self._lbl_total.setText("Parcours des dossiers…")
        self._btn_stop.setEnabled(True)

        self._thread = FolderAnalysisThread(root, exts, out_fmt, quality,
                                            max_side, keep, parallel)
        self._thread.folders_found.connect(self._on_found)
        self._thread.folder_done.connect(self._on_folder)
        self._thread.all_done.connect(self._on_done)
        self._thread.start()

    def _stop(self):
        if self._thread and self._thread.isRunning():
            # Un encodage en cours peut finir après l'arrêt : ses résultats
            # ne doivent plus arriver dans le tableau
            for sig in (self._thread.folders_found, self._thread.folder_done,
                        self._thread.all_done):
                sig.disconnect()
            self._thread.cancel()
            self._thread.wait(5000)
            self._on_done()
        self._btn_stop.setEnabled(False)

    def _on_found(self, n: int):
        self._n_folders = n
        self._progress.setRange(0, max(n, 1))
        self._progress.setValue(0)
        self._update_total()

    def _on_folder(self, directory: str, est: Estimate):
        self._n_done   += 1
        self._tot_src  += est.src_bytes
        self._tot_est  += est.est_bytes
        self._progress.setValue(self._n_done)

        rel = os.path.relpath(directory, self._root)
        row = self._table.rowCount()
        self._table.insertRow(row)

        it_dir = QTableWidgetItem("." if rel == "." else rel)
        it_dir.setData(Qt.ItemDataRole.UserRole, directory)
        it_dir.setToolTip(directory)
        self._table.setItem(row, C_DIR, it_dir)
        self._table.setItem(row, C_COUNT, _NumItem(est.n_files, str(est.n_files)))
        self._table.setItem(row, C_SRC,   _NumItem(est.src_bytes, fmt_bytes(est.src_bytes)))
        self._table.setItem(row, C_EST,   _NumItem(est.est_bytes, "≈ " + fmt_bytes(est.est_bytes)))

        # Gain négatif (fichiers déjà très compressés) → signe « − » visible
        self._table.setItem(row, C_GAIN, _NumItem(est.gain_bytes, fmt_bytes(est.gain_bytes)))
        self._table.setItem(row, C_PCT,  _NumItem(est.gain_pct, f"{est.gain_pct:.0f} %"))

        m_label = "exacte" if est.exact else f"± {est.margin * 100:.0f} %"
        it_m = _NumItem(0 if est.exact else est.margin, m_label)
        it_m.setToolTip(f"{est.n_samples} image(s) convertie(s) en test sur {est.n_files}")
        self._table.setItem(row, C_MARGIN, it_m)
        self._update_total()

    def _on_done(self):
        self._btn_stop.setEnabled(False)
        if self._progress.maximum() == 0:
            self._progress.setRange(0, 1)
        self._progress.setValue(self._progress.maximum())
        self._table.setSortingEnabled(True)
        # Classement par défaut : plus gros gain en premier
        self._table.sortItems(C_GAIN, Qt.SortOrder.DescendingOrder)
        self._update_total(done=True)

    def _update_total(self, done: bool = False):
        gain = self._tot_src - self._tot_est
        pct  = (gain / self._tot_src * 100) if self._tot_src else 0
        state = "terminé" if done else f"{self._n_done} / {self._n_folders} dossiers"
        self._lbl_total.setText(
            f"{state}   —   Total : {fmt_bytes(self._tot_src)} → ≈ {fmt_bytes(self._tot_est)}"
            f"   (gain ≈ {fmt_bytes(gain)}, {pct:.0f} %)"
        )

    # ── Actions ───────────────────────────────────────────────────────────────

    def _row_dir(self, row: int) -> str:
        it = self._table.item(row, C_DIR)
        return it.data(Qt.ItemDataRole.UserRole) if it else ""

    def _load_row(self, row: int):
        d = self._row_dir(row)
        if d:
            self.load_requested.emit(d)

    def _on_context_menu(self, pos):
        row = self._table.rowAt(pos.y())
        if row < 0:
            return
        d = self._row_dir(row)
        menu = QMenu(self)
        act_load = menu.addAction("📥  Charger dans le convertisseur")
        act_open = menu.addAction("📂  Ouvrir dans l'Explorateur")
        action = menu.exec(self._table.viewport().mapToGlobal(pos))
        if action == act_load:
            self.load_requested.emit(d)
        elif action == act_open:
            subprocess.Popen(["explorer", os.path.normpath(d)])

    # ── Drag / show / close ───────────────────────────────────────────────────

    def _tb_press(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def _tb_move(self, event):
        if self._drag_pos and event.buttons() == Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)

    def _tb_release(self, _event):
        self._drag_pos = None

    def showEvent(self, event):
        super().showEvent(event)
        apply_acrylic(int(self.winId()), dark=(self._theme == "dark"))

    def closeEvent(self, event):
        self._stop()
        super().closeEvent(event)
