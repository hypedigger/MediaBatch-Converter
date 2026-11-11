import json
import os
from datetime import datetime
from typing import List, Optional

from PyQt6.QtCore    import Qt, QSize, QTimer, QPoint, QEvent, pyqtSignal
from PyQt6.QtWidgets import (
    QApplication,
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QLineEdit, QFileDialog, QCheckBox,
    QTableWidget, QTableWidgetItem, QHeaderView, QComboBox,
    QProgressBar, QSizePolicy, QFrame, QAbstractItemView,
    QMessageBox, QDialog, QScrollArea, QMenu, QSlider, QStackedWidget,
    QButtonGroup,
)
from PyQt6.QtGui import QFont, QCursor, QIcon, QIntValidator

from core.config    import (APP_TITLE, SUPPORTED_INPUT_FORMATS, OUTPUT_FORMATS,
                             IMAGE_INPUT_FORMATS, IMAGE_OUTPUT_FORMATS,
                             IMAGE_RESIZE_OPTIONS, DEFAULT_SETTINGS, CONFIG_FILE)
from core.scanner   import FileInfo, scan_directory, file_info_from_path
from core.converter import ConversionThread, detect_conflicts, clean_name
from core.image_converter import ImageConversionThread, SKIPPED, REPLACED
from core.image_estimator import EstimateThread, Estimate
from core.logger    import get_app_logger
from core.tags      import is_editable
from ui.styles      import get_theme
from ui.effects     import apply_acrylic
from ui.icon        import create_app_icon
from ui.log_window  import LogWindow
from ui.settings_dialog import SettingsDialog
from ui.tag_editor_dialog import TagEditorDialog
from ui.preview_player import PreviewPlayer
from ui.image_tree  import ImageTreePanel, fmt_bytes, gain_color
from ui.table_style import style_table
from ui.toast       import Toast
from ui.icons       import icon, PALETTE
from ui.home_screen import HomeScreen
from ui.summary_dialog import SummaryDialog
from ui.notify      import Notifier
from core.recycle   import send_to_recycle_bin

# Formats d'entrée par mode : nom affiché → liste d'extensions
_INPUT_FORMATS = {
    "audio": {name: [ext] for name, ext in SUPPORTED_INPUT_FORMATS.items()},
    "image": IMAGE_INPUT_FORMATS,
}
_SELECTED_KEY = {"audio": "selected_formats", "image": "image_selected_formats"}


# ── Sortable table items ──────────────────────────────────────────────────────

class _SizeItem(QTableWidgetItem):
    def __init__(self, size: int, label: str):
        super().__init__(label)
        self._size = size
    def __lt__(self, other):
        if isinstance(other, _SizeItem):
            return self._size < other._size
        return super().__lt__(other)


class _DateItem(QTableWidgetItem):
    def __init__(self, ts: float, label: str):
        super().__init__(label)
        self._ts = ts
    def __lt__(self, other):
        if isinstance(other, _DateItem):
            return self._ts < other._ts
        return super().__lt__(other)


# ── Custom table with Space-key checkbox toggle ───────────────────────────────

class _FileTable(QTableWidget):
    """QTableWidget that toggles checkboxes with Space and supports multi-row selection."""

    mouse_left = pyqtSignal()   # curseur sorti de la table (efface le ▶ de survol)

    def leaveEvent(self, event):
        self.mouse_left.emit()
        super().leaveEvent(event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Space:
            rows = {idx.row() for idx in self.selectedIndexes()}
            if not rows:
                super().keyPressEvent(event)
                return
            # If any selected row is unchecked → check all; else uncheck all
            has_unchecked = any(
                self.item(r, COL_CHECK) and
                self.item(r, COL_CHECK).checkState() == Qt.CheckState.Unchecked
                for r in rows
            )
            new_state = Qt.CheckState.Checked if has_unchecked else Qt.CheckState.Unchecked
            self.blockSignals(True)
            for r in rows:
                item = self.item(r, COL_CHECK)
                if item:
                    item.setCheckState(new_state)
            self.blockSignals(False)
            # Notify parent via itemChanged on the first item
            first_item = self.item(min(rows), COL_CHECK)
            if first_item:
                self.itemChanged.emit(first_item)
            event.accept()
        else:
            super().keyPressEvent(event)


# ── Conflict dialog ───────────────────────────────────────────────────────────

GAIN_SELECT_DEFAULT = 30        # % de gain par défaut du bouton « Gain ≥ »


class _ConflictDialog(QDialog):
    def __init__(self, conflicts: List[FileInfo], out_ext: str, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedWidth(480)
        self._choice = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        card = QWidget()
        card.setObjectName("central_widget")
        outer.addWidget(card)

        lay = QVBoxLayout(card)
        lay.setContentsMargins(28, 24, 28, 24)
        lay.setSpacing(14)

        title = QLabel("⚠️  Conflits détectés")
        title.setFont(QFont("Segoe UI Variable", 14, QFont.Weight.Bold))
        title.setStyleSheet("color: #f0c060;")
        lay.addWidget(title)

        n = len(conflicts)
        msg = QLabel(
            f"{n} fichier(s) existent déjà en .{out_ext} dans le répertoire cible.\n"
            "Que souhaitez-vous faire ?"
        )
        msg.setWordWrap(True)
        msg.setStyleSheet("color: rgba(255,255,255,180); font-size:13px;")
        lay.addWidget(msg)

        sep = QFrame(); sep.setFrameShape(QFrame.Shape.HLine)
        lay.addWidget(sep)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)

        btn_cancel = QPushButton("Annuler")
        btn_cancel.clicked.connect(lambda: self._choose(None))
        btn_row.addWidget(btn_cancel)

        btn_ren = QPushButton("Renommer  (_v1, _v2…)")
        btn_ren.clicked.connect(lambda: self._choose("rename"))
        btn_row.addWidget(btn_ren)

        btn_ow = QPushButton("Écraser")
        btn_ow.setObjectName("btn_primary")
        btn_ow.clicked.connect(lambda: self._choose("overwrite"))
        btn_row.addWidget(btn_ow)

        lay.addLayout(btn_row)
        self.adjustSize()

    def _choose(self, val):
        self._choice = val
        if val is None:
            self.reject()
        else:
            self.accept()

    def get_choice(self) -> Optional[str]:
        return self._choice

    def showEvent(self, e):
        super().showEvent(e)
        apply_acrylic(int(self.winId()), dark=True)


# ── Main Window ───────────────────────────────────────────────────────────────

COL_PLAY  = 0
COL_CHECK = 1
COL_NAME  = 2
COL_DIR   = 3
COL_SIZE  = 4
COL_DATE  = 5
COL_EXT   = 6


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self._settings      = self._load_settings()
        self._files: List[FileInfo] = []
        self._thread: Optional[ConversionThread] = None
        self._playing_path  = ""           # fichier en cours de pré-écoute
        self._hover_row     = -1
        self._log_window: Optional[LogWindow] = None
        self._drag_pos      = None
        self._resize_edge   = None
        self._resize_start  = None
        self._resize_geom   = None
        self._RESIZE_MARGIN = 8
        self._conv_summary: dict = {}
        self._mode = self._settings.get("mode", "audio")
        if self._mode not in _INPUT_FORMATS:
            self._mode = "audio"
        self._estimate_thread: Optional[EstimateThread] = None
        self._estimate_pending = False
        self._icon_buttons: list = []            # (bouton, nom, rôle, taille)
        self._refresh_buttons: list = []         # un bouton Actualiser par mode
        self._scanned_exts = None                # formats de la liste affichée
        self._pulse_on = False
        self._pulse_timer = QTimer(self)
        self._pulse_timer.setInterval(550)
        self._pulse_timer.timeout.connect(self._pulse_step)
        self._estimate_timer = QTimer(self)
        self._estimate_timer.setSingleShot(True)
        self._estimate_timer.setInterval(400)
        self._estimate_timer.timeout.connect(self._run_estimate)

        self.setWindowIcon(create_app_icon())
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.Window
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setMinimumSize(1000, 660)
        self.resize(1260, 780)
        self.setMouseTracking(True)
        self.setAcceptDrops(True)

        self._build_ui()
        self._apply_theme()
        self._apply_mode()
        self._show_home()

    # ═════════════════════════════════════════════════════════════════════════
    # UI BUILD
    # ═════════════════════════════════════════════════════════════════════════

    def _build_ui(self):
        root = QWidget()
        root.setObjectName("root_widget")
        self.setCentralWidget(root)
        root_lay = QVBoxLayout(root)
        root_lay.setContentsMargins(0, 0, 0, 0)

        self._central = QWidget()
        self._central.setObjectName("central_widget")
        self._central.setMouseTracking(True)
        root_lay.addWidget(self._central)

        main_lay = QVBoxLayout(self._central)
        main_lay.setContentsMargins(0, 0, 0, 0)
        main_lay.setSpacing(0)

        main_lay.addWidget(self._make_title_bar())
        main_lay.addWidget(self._make_body(), 1)
        main_lay.addWidget(self._make_status_bar())

        self._toast = Toast(self._central)

    # ── Title bar ─────────────────────────────────────────────────────────────

    def _make_title_bar(self) -> QWidget:
        tb = QWidget()
        tb.setObjectName("title_bar")
        tb.setFixedHeight(44)
        lay = QHBoxLayout(tb)
        lay.setContentsMargins(16, 0, 0, 0)
        lay.setSpacing(0)

        # Icon (celle de l'app)
        self._title_icon = QLabel()
        self._title_icon.setPixmap(create_app_icon().pixmap(22, 22))
        self._title_icon.setStyleSheet("margin-right:10px;")
        lay.addWidget(self._title_icon)

        # Title
        lbl = QLabel(APP_TITLE)
        lbl.setObjectName("title_label")
        lay.addWidget(lbl)
        lay.addSpacing(24)

        # Mode Audio / Images (retenu d'une session à l'autre)
        self._mode_group = QButtonGroup(self)
        self._mode_group.setExclusive(True)
        self._mode_buttons = {}
        for mode, txt, ic in (("audio", " Audio", "music"), ("image", " Images", "image")):
            b = QPushButton(txt)
            b.setObjectName("btn_mode")
            self._set_icon(b, ic, "text", 15)
            b.setCheckable(True)
            b.setFixedHeight(28)
            b.setChecked(mode == self._mode)
            b.clicked.connect(lambda _c, m=mode: self._set_mode(m))
            self._mode_group.addButton(b)
            self._mode_buttons[mode] = b
            lay.addWidget(b)
            lay.addSpacing(4)
        lay.addStretch()

        # Log button
        self._btn_log = QPushButton(" Logs")
        self._btn_log.setObjectName("btn_icon")
        self._btn_log.setFixedHeight(32)
        self._set_icon(self._btn_log, "logs", "muted", 17)
        self._btn_log.clicked.connect(self._toggle_log)
        lay.addWidget(self._btn_log)

        lay.addSpacing(12)   # séparation avant les contrôles fenêtre

        # Settings
        btn_settings = QPushButton()
        btn_settings.setObjectName("btn_icon")
        btn_settings.setFixedSize(40, 32)
        btn_settings.setToolTip("Réglages")
        self._set_icon(btn_settings, "settings", "muted", 18)
        btn_settings.clicked.connect(self._open_settings)
        lay.addWidget(btn_settings)

        # Win controls
        for name, ic, slot in [
            ("btn_minimize", "minimize", self.showMinimized),
            ("btn_maximize", "maximize", self._toggle_maximize),
            ("btn_close",    "close",    self.close),
        ]:
            b = QPushButton()
            b.setObjectName(name)
            self._set_icon(b, ic, "muted", 15 if ic == "maximize" else 16)
            b.clicked.connect(slot)
            lay.addWidget(b)

        # Dragging
        tb.mousePressEvent   = self._tb_press
        tb.mouseMoveEvent    = self._tb_move
        tb.mouseReleaseEvent = self._tb_release
        tb.mouseDoubleClickEvent = self._tb_double_click     # double-clic : agrandir / restaurer
        return tb

    # ── Body ──────────────────────────────────────────────────────────────────

    def _make_body(self) -> QWidget:
        # Écran 1 : choix du dossier (récents / Parcourir) ; écran 2 : la liste
        self._home = HomeScreen()
        self._home.browse_requested.connect(self._browse_directory)
        self._home.open_requested.connect(self._open_directory)
        self._home.clear_requested.connect(self._clear_history)

        self._screens = QStackedWidget()
        self._screens.addWidget(self._home)
        self._screens.addWidget(self._make_work_screen())
        return self._screens

    def _make_work_screen(self) -> QWidget:
        body = QWidget()
        lay  = QVBoxLayout(body)
        lay.setContentsMargins(14, 10, 14, 10)
        lay.setSpacing(10)

        lay.addWidget(self._make_top_panel())
        lay.addWidget(self._make_list_panel(), 1)

        self._preview = PreviewPlayer()
        self._preview.stopped.connect(self._on_preview_stopped)
        lay.addWidget(self._preview)

        lay.addWidget(self._make_bottom_panel())
        return body

    # ── Top panel (directory + formats) ──────────────────────────────────────

    def _make_top_panel(self) -> QWidget:
        panel = QWidget()
        panel.setObjectName("panel_top")
        self._panel_top = panel
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(12)

        # Directory row
        dir_row = QHBoxLayout()
        btn_home = QPushButton(" Accueil")
        btn_home.setObjectName("btn_secondary")
        btn_home.setFixedHeight(38)
        btn_home.setToolTip("Revenir au choix du dossier (dossiers récents)")
        self._set_icon(btn_home, "back", "text", 17)
        btn_home.clicked.connect(self._show_home)
        dir_row.addWidget(btn_home)

        self._dir_edit = QLineEdit()
        self._dir_edit.setReadOnly(True)
        self._dir_edit.setPlaceholderText("Sélectionner un répertoire…")
        last = self._settings.get("last_directory", "")
        if last and os.path.isdir(last):
            self._dir_edit.setText(last)
        dir_row.addWidget(self._dir_edit, 1)

        btn_browse = QPushButton(" Changer de dossier")
        btn_browse.setObjectName("btn_secondary")
        btn_browse.setFixedHeight(38)
        self._set_icon(btn_browse, "folder", "text", 17)
        btn_browse.clicked.connect(self._browse_directory)
        dir_row.addWidget(btn_browse)

        lay.addLayout(dir_row)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        lay.addWidget(sep)

        # Formats row
        fmt_row = QHBoxLayout()
        fmt_row.setSpacing(0)

        lbl_fmt = QLabel("FORMATS")
        lbl_fmt.setObjectName("label_section")
        lbl_fmt.setFixedWidth(90)
        fmt_row.addWidget(lbl_fmt)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setFixedHeight(34)
        scroll.setStyleSheet("background: transparent;")

        # Une rangée de cases par mode ; la pile affiche celle du mode courant
        self._fmt_stack = QStackedWidget()
        self._fmt_stack.setStyleSheet("background: transparent;")
        self._format_checks_by_mode = {}
        for mode, formats in _INPUT_FORMATS.items():
            fmt_inner = QWidget()
            fmt_inner.setStyleSheet("background: transparent;")
            fmt_lay = QHBoxLayout(fmt_inner)
            fmt_lay.setContentsMargins(0, 0, 0, 0)
            fmt_lay.setSpacing(10)
            checks = {}
            selected = self._settings.get(_SELECTED_KEY[mode], list(formats.keys()))
            for name in formats:
                cb = QCheckBox(name)
                cb.setChecked(name in selected)
                checks[name] = cb
                fmt_lay.addWidget(cb)
            fmt_lay.addSpacing(6)
            for txt, state in (("Tous", True), ("Aucun", False)):
                b = QPushButton(txt)
                b.setObjectName("btn_chip")
                b.setFixedHeight(26)
                b.clicked.connect(lambda _c, st=state: self._set_all_formats(st))
                fmt_lay.addWidget(b)
            # Relire le dossier : clignote quand les formats cochés ont changé
            btn_refresh = QPushButton()
            btn_refresh.setObjectName("btn_tool")
            btn_refresh.setFixedSize(30, 26)
            self._set_icon(btn_refresh, "refresh", "text", 15)
            btn_refresh.setToolTip(self._REFRESH_TIP)
            btn_refresh.clicked.connect(self._scan_directory)
            self._refresh_buttons.append(btn_refresh)
            fmt_lay.addWidget(btn_refresh)
            for cb in checks.values():
                cb.toggled.connect(self._on_formats_changed)
            fmt_lay.addStretch()
            self._format_checks_by_mode[mode] = checks
            self._fmt_stack.addWidget(fmt_inner)

        scroll.setWidget(self._fmt_stack)
        fmt_row.addWidget(scroll, 1)

        self._btn_analyze = QPushButton(" Estimer le gain d'espace")
        self._btn_analyze.setObjectName("btn_accent")
        self._btn_analyze.setFixedHeight(38)
        self._set_icon(self._btn_analyze, "estimate", "on_accent", 18)
        self._btn_analyze.setToolTip(
            "Calcule, dossier par dossier, la place que la conversion ferait gagner\n"
            "avec le format et la qualité choisis — sans rien modifier."
        )
        self._btn_analyze.clicked.connect(self._toggle_estimate)
        fmt_row.addSpacing(12)
        fmt_row.addWidget(self._btn_analyze)

        lay.addLayout(fmt_row)
        return panel

    # ── List panel ────────────────────────────────────────────────────────────

    def _make_list_panel(self) -> QWidget:
        panel = QWidget()
        panel.setObjectName("panel_list")
        panel.installEventFilter(self)           # redimensionnement → réaligner la case
        self._list_panel = panel
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(8)

        # Toolbar row : sélection (au-dessus de la colonne des cases), compteur
        tool_row = QHBoxLayout()
        tool_row.setSpacing(6)
        # Décalage calculé pour que la case globale tombe pile au-dessus des cases des lignes
        self._sel_spacer = QWidget()
        self._sel_spacer.setFixedWidth(0)
        tool_row.addWidget(self._sel_spacer)
        # Une seule case à trois états (vide / partielle / cochée), comme un en-tête de colonne
        self._btn_select = QPushButton()
        self._btn_select.setObjectName("btn_tool")
        self._btn_select.setFixedSize(30, 28)
        self._btn_select.clicked.connect(self._toggle_select_all)
        tool_row.addWidget(self._btn_select)
        self._sel_count, self._sel_total = 0, 0
        self._update_select_button(0, 0)

        # Mode Images : cocher les dossiers où l'estimation promet ≥ 30 % de gain
        # [Gain ≥] [30] %  — seuil modifiable, appliqué par le bouton ou Entrée
        self._gain_box = QWidget()
        gb = QHBoxLayout(self._gain_box)
        gb.setContentsMargins(0, 0, 0, 0)
        gb.setSpacing(4)
        self._btn_select_gain = QPushButton("Gain ≥")
        self._btn_select_gain.setObjectName("btn_tool")
        self._btn_select_gain.setFixedHeight(28)
        self._btn_select_gain.clicked.connect(self._select_by_gain)
        gb.addWidget(self._btn_select_gain)
        self._edit_gain = QLineEdit(str(self._settings.get("gain_select_threshold", GAIN_SELECT_DEFAULT)))
        self._edit_gain.setValidator(QIntValidator(0, 99, self._edit_gain))
        self._edit_gain.setFixedSize(40, 28)
        self._edit_gain.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._edit_gain.setStyleSheet("padding: 0 4px;")
        self._edit_gain.setToolTip("Seuil de gain estimé (%) pour la sélection — Entrée pour appliquer")
        self._edit_gain.returnPressed.connect(self._select_by_gain)
        self._edit_gain.textChanged.connect(self._on_gain_threshold_changed)
        gb.addWidget(self._edit_gain)
        lbl_pct = QLabel("%")
        lbl_pct.setObjectName("label_field")
        gb.addWidget(lbl_pct)
        tool_row.addWidget(self._gain_box)
        tool_row.addSpacing(10)

        self._lbl_count = QLabel("Aucun fichier — glissez un dossier ici")
        self._lbl_count.setObjectName("label_count")
        tool_row.addWidget(self._lbl_count)
        tool_row.addStretch(1)
        # Emplacement de la ligne d'activité (mode Images) quand elle tient ici,
        # centrée entre le compteur et la légende ; sinon elle reste sous la ligne
        self._act_slot = QHBoxLayout()
        self._act_slot.setSpacing(12)
        tool_row.addLayout(self._act_slot)
        tool_row.addStretch(1)
        self._legend_slot = QHBoxLayout()
        tool_row.addLayout(self._legend_slot)
        self._tool_row = tool_row
        lay.addLayout(tool_row)

        # Table
        self._table = _FileTable()
        self._table.setColumnCount(7)
        self._table.setHorizontalHeaderLabels(
            ["", "", "Nom", "Répertoire", "Taille", "Date", "Ext."]
        )
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self._table.setSortingEnabled(True)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setShowGrid(False)
        self._table.verticalHeader().setVisible(False)
        style_table(self._table, self._settings.get("theme", "dark"))
        self._table.setIconSize(QSize(14, 14))

        hdr = self._table.horizontalHeader()
        hdr.setSectionResizeMode(COL_PLAY,  QHeaderView.ResizeMode.Fixed)
        hdr.setSectionResizeMode(COL_CHECK, QHeaderView.ResizeMode.Fixed)
        hdr.setSectionResizeMode(COL_NAME,  QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(COL_DIR,   QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(COL_SIZE,  QHeaderView.ResizeMode.Fixed)
        hdr.setSectionResizeMode(COL_DATE,  QHeaderView.ResizeMode.Fixed)
        hdr.setSectionResizeMode(COL_EXT,   QHeaderView.ResizeMode.Fixed)
        self._table.setColumnWidth(COL_PLAY,  36)
        self._table.setColumnWidth(COL_CHECK, 36)
        self._table.setColumnWidth(COL_SIZE,  90)
        self._table.setColumnWidth(COL_DATE,  140)
        self._table.setColumnWidth(COL_EXT,   70)
        self._table.verticalHeader().setDefaultSectionSize(38)

        # Survol → bouton ▶ en début de ligne ; clic → lecture / tags
        self._table.setMouseTracking(True)
        self._table.cellEntered.connect(self._on_cell_entered)
        self._table.cellClicked.connect(self._on_cell_clicked)
        self._table.mouse_left.connect(self._on_table_left)

        self._table.itemChanged.connect(self._on_item_changed)
        self._table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._table.customContextMenuRequested.connect(self._on_context_menu)

        # Mode Images : arborescence par dossier, colonnes d'estimation intégrées
        self._image_panel = ImageTreePanel(self._settings.get("theme", "dark"))
        self._image_panel.selection_changed.connect(self._update_convert_btn)
        self._image_panel.running_changed.connect(self._on_estimate_running)
        self._image_panel.activity_changed.connect(self._schedule_place_activity)
        self._image_panel.estimate_finished.connect(
            lambda text: self._notify_done("Analyse terminée", text))
        self._update_gain_button()

        self._list_stack = QStackedWidget()
        self._list_stack.addWidget(self._table)
        self._list_stack.addWidget(self._image_panel)
        lay.addWidget(self._list_stack, 1)
        return panel

    # ── Bottom panel (conversion controls + progress) ─────────────────────────

    def _make_bottom_panel(self) -> QWidget:
        self._panel_bottom = QWidget()
        self._panel_bottom.setObjectName("panel_bottom")
        lay = QVBoxLayout(self._panel_bottom)
        lay.setContentsMargins(16, 12, 16, 12)
        lay.setSpacing(10)

        # Progress row (hidden until conversion starts)
        self._progress_row = QWidget()
        pr_lay = QVBoxLayout(self._progress_row)
        pr_lay.setContentsMargins(0, 0, 0, 0)
        pr_lay.setSpacing(4)

        self._lbl_progress = QLabel("Conversion en cours…  0 / 0")
        self._lbl_progress.setObjectName("label_desc")
        pr_lay.addWidget(self._lbl_progress)

        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 100)
        self._progress_bar.setValue(0)
        self._progress_bar.setFixedHeight(8)
        pr_lay.addWidget(self._progress_bar)

        self._progress_row.hide()
        lay.addWidget(self._progress_row)

        # Image options row (mode Images uniquement)
        self._img_opts_row = QWidget()
        io_lay = QHBoxLayout(self._img_opts_row)
        io_lay.setContentsMargins(0, 0, 0, 0)
        io_lay.setSpacing(12)

        self._lbl_quality = QLabel("Qualité :")
        self._lbl_quality.setObjectName("label_field")
        io_lay.addWidget(self._lbl_quality)
        self._slider_quality = QSlider(Qt.Orientation.Horizontal)
        self._slider_quality.setRange(1, 100)
        self._slider_quality.setFixedWidth(120)
        self._slider_quality.valueChanged.connect(self._on_quality_changed)
        io_lay.addWidget(self._slider_quality)
        self._lbl_quality_val = QLabel("85")
        self._lbl_quality_val.setFixedWidth(28)
        io_lay.addWidget(self._lbl_quality_val)

        io_lay.addSpacing(4)
        lbl_size = QLabel("Côté max :")
        lbl_size.setObjectName("label_field")
        io_lay.addWidget(lbl_size)
        self._combo_max_side = QComboBox()
        cur_side = self._settings.get("image_max_side", 0)
        for i, px in enumerate(IMAGE_RESIZE_OPTIONS):
            self._combo_max_side.addItem("Taille d'origine" if px == 0 else f"{px} px", userData=px)
            if px == cur_side:
                self._combo_max_side.setCurrentIndex(i)
        self._combo_max_side.currentIndexChanged.connect(self._on_image_option_changed)
        io_lay.addWidget(self._combo_max_side)

        io_lay.addSpacing(4)
        self._chk_keep = QCheckBox("Garder l'original si plus lourd")
        self._chk_keep.setToolTip(
            "Si l'image convertie est plus lourde que l'original,\n"
            "l'original reste en place, intact, et aucune sortie n'est écrite.")
        self._chk_keep.setChecked(self._settings.get("image_keep_if_larger", True))
        self._chk_keep.toggled.connect(self._on_image_option_changed)
        io_lay.addWidget(self._chk_keep)

        # Conflits : renommer avec un suffixe (sinon écraser)
        io_lay.addSpacing(4)
        self._chk_rename = QCheckBox("Renommer les conflits")
        self._chk_rename.setToolTip(
            "Si le fichier de sortie existe déjà (par ex. JPEG → JPEG au même endroit),\n"
            "le suffixe est ajouté au nom : photo_v2.jpg, puis _v3…\n"
            "Décoché : le fichier existant est écrasé (l'original passe d'abord par la\n"
            "corbeille si « Envoyer les originaux à la corbeille » est coché).")
        self._chk_rename.setChecked(self._settings.get("image_rename_conflicts", True))
        io_lay.addWidget(self._chk_rename)
        self._edit_suffix = QLineEdit(self._settings.get("image_rename_suffix", "_v2"))
        self._edit_suffix.setPlaceholderText("_v2")
        self._edit_suffix.setFixedWidth(64)
        self._edit_suffix.setToolTip("Suffixe ajouté au nom en cas de conflit")
        io_lay.addWidget(self._edit_suffix)

        # Sous-dossier de sortie, créé dans le dossier de chaque original
        io_lay.addSpacing(4)
        self._chk_subdir = QCheckBox("Sous-dossier")
        self._chk_subdir.setToolTip(
            "Enregistre les images converties dans un sous-dossier créé à côté de\n"
            "chaque original (par ex. Vacances\\Reduced\\photo.jpg).")
        self._chk_subdir.setChecked(self._settings.get("image_use_subdir", False))
        io_lay.addWidget(self._chk_subdir)
        self._edit_subdir = QLineEdit(self._settings.get("image_subdir", "Reduced"))
        self._edit_subdir.setPlaceholderText("Reduced")
        self._edit_subdir.setFixedWidth(96)
        self._edit_subdir.setToolTip("Nom du sous-dossier")
        io_lay.addWidget(self._edit_subdir)

        for w in (self._chk_rename, self._chk_subdir):
            w.toggled.connect(self._on_output_option_changed)
        for w in (self._edit_suffix, self._edit_subdir):
            w.textChanged.connect(self._on_output_option_changed)
        self._on_output_option_changed()

        io_lay.addStretch()
        self._lbl_estimate = QLabel()
        self._lbl_estimate.setObjectName("label_count")
        # Prend la place restante sans jamais tasser les options à sa gauche
        self._lbl_estimate.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self._lbl_estimate.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self._lbl_estimate.setToolTip(
            "Estimation : une partie de la sélection est convertie en mémoire\n"
            "et le résultat extrapolé à l'ensemble des fichiers."
        )
        io_lay.addWidget(self._lbl_estimate)
        lay.addWidget(self._img_opts_row)

        # Controls row
        ctrl_row = QHBoxLayout()
        ctrl_row.setSpacing(12)

        # Format selector
        lbl_fmt = QLabel("Format de sortie :")
        lbl_fmt.setObjectName("label_field")
        ctrl_row.addWidget(lbl_fmt)

        # Rempli selon le mode par _apply_mode()
        self._combo_out_fmt = QComboBox()
        self._combo_out_fmt.setMinimumWidth(260)
        self._combo_out_fmt.currentIndexChanged.connect(self._on_format_changed)
        ctrl_row.addWidget(self._combo_out_fmt)

        # Description label
        self._lbl_fmt_desc = QLabel()
        self._lbl_fmt_desc.setObjectName("label_desc")
        self._lbl_fmt_desc.setWordWrap(True)
        self._lbl_fmt_desc.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        ctrl_row.addWidget(self._lbl_fmt_desc, 1)

        # Delete source checkbox
        self._chk_delete = QCheckBox("Envoyer les originaux à la corbeille")
        self._chk_delete.setToolTip(
            "Après conversion, les fichiers d'origine convertis partent à la Corbeille Windows\n"
            "(récupérables). Les originaux gardés tels quels ou en erreur ne sont pas touchés.")
        ctrl_row.addWidget(self._chk_delete)

        ctrl_row.addStretch()

        # Convert button
        self._btn_convert = QPushButton(" Convertir")
        self._set_icon(self._btn_convert, "play", "on_accent", 15)
        self._btn_convert.setObjectName("btn_primary")
        self._btn_convert.setEnabled(False)
        self._btn_convert.clicked.connect(self._start_conversion)
        ctrl_row.addWidget(self._btn_convert)

        # Cancel button (hidden)
        self._btn_cancel_conv = QPushButton(" Annuler")
        self._set_icon(self._btn_cancel_conv, "stop", "text", 15)
        self._btn_cancel_conv.clicked.connect(self._cancel_conversion)
        self._btn_cancel_conv.hide()
        ctrl_row.addWidget(self._btn_cancel_conv)

        lay.addLayout(ctrl_row)
        return self._panel_bottom

    # ── Status bar ────────────────────────────────────────────────────────────

    def _make_status_bar(self) -> QWidget:
        sb = QWidget()
        sb.setObjectName("status_bar")
        sb.setFixedHeight(28)
        lay = QHBoxLayout(sb)
        lay.setContentsMargins(16, 0, 16, 0)

        self._status_lbl = QLabel("Prêt")
        self._status_lbl.setObjectName("status_label")
        lay.addWidget(self._status_lbl)
        lay.addStretch()

        ver_lbl = QLabel(APP_TITLE.split('—')[1].strip())
        ver_lbl.setObjectName("status_label")
        lay.addWidget(ver_lbl)
        return sb

    # ═════════════════════════════════════════════════════════════════════════
    # ACTIONS
    # ═════════════════════════════════════════════════════════════════════════

    def _browse_directory(self):
        last = self._dir_edit.text() or os.path.expanduser("~")
        path = QFileDialog.getExistingDirectory(self, "Sélectionner un répertoire", last)
        if path:
            self._open_directory(path)

    _REFRESH_TIP = ("Actualiser la liste\n"
                    "Relit le dossier : à utiliser après avoir changé les formats cochés,\n"
                    "ou si des fichiers ont été ajoutés, renommés ou supprimés entre-temps.")
    _REFRESH_TIP_PENDING = ("Les formats cochés ont changé\n"
                            "Cliquez pour mettre à jour la liste.")

    def _on_formats_changed(self, *_):
        """Formats cochés ≠ ceux de la liste affichée → le bouton Actualiser clignote."""
        pending = (self._scanned_exts is not None
                   and (set(self._selected_exts()) != self._scanned_exts
                        or (self._mode == "image"
                            and self._output_target()[1] != getattr(self, "_scanned_excl", ""))))
        self._set_refresh_pulse(pending)

    def _set_refresh_pulse(self, on: bool):
        for b in self._refresh_buttons:
            b.setToolTip(self._REFRESH_TIP_PENDING if on else self._REFRESH_TIP)
        if on and not self._pulse_timer.isActive():
            self._pulse_timer.start()
            self._pulse_step()
        elif not on:
            self._pulse_timer.stop()
            self._pulse_on = True              # → le pas suivant éteint
            self._pulse_step()

    def _pulse_step(self):
        self._pulse_on = not self._pulse_on
        for b in self._refresh_buttons:
            b.setProperty("pulse", self._pulse_on)
            b.style().unpolish(b)
            b.style().polish(b)

    # ── Dossiers récents ──────────────────────────────────────────────────────

    def _remember_directory(self, path: str):
        path = os.path.normpath(path)
        recent = [p for p in self._settings.get("recent_directories", [])
                  if os.path.normcase(p) != os.path.normcase(path)]
        self._settings["recent_directories"] = [path] + recent[:4]
        self._save_settings()
        if hasattr(self, "_home"):
            self._refresh_home()

    def _clear_history(self):
        self._settings["recent_directories"] = []
        self._save_settings()
        self._refresh_home()
        self._set_status("Historique des dossiers effacé.")

    # ── Navigation accueil ↔ liste ────────────────────────────────────────────

    def _refresh_home(self):
        self._home.set_recents(self._settings.get("recent_directories", []),
                               self._dir_edit.text().strip())

    def _show_home(self):
        self._toast.dismiss()
        self._refresh_home()
        self._screens.setCurrentWidget(self._home)

    def _show_work(self):
        self._screens.setCurrentIndex(1)

    def _open_directory(self, path: str):
        """Dossier choisi (Parcourir ou récent) : on l'affiche dans la liste."""
        if not os.path.isdir(path):
            self._set_status(f"Dossier introuvable : {path}")
            self._refresh_home()
            return
        self._dir_edit.setText(path)
        self._settings["last_directory"] = path
        self._save_settings()
        self._show_work()
        self._scan_directory()
        self._suggest_estimate(path)

    @property
    def _format_checks(self) -> dict:
        return self._format_checks_by_mode[self._mode]

    def _selected_exts(self) -> List[str]:
        return [ext for name, exts in _INPUT_FORMATS[self._mode].items()
                if self._format_checks[name].isChecked() for ext in exts]

    def _all_exts(self) -> set:
        return {ext for exts in _INPUT_FORMATS[self._mode].values() for ext in exts}

    def _set_all_formats(self, state: bool):
        for cb in self._format_checks.values():
            cb.setChecked(state)

    def _scan_directory(self):
        path = self._dir_edit.text().strip()
        if not path or not os.path.isdir(path):
            self._set_status("Veuillez sélectionner un répertoire valide.")
            return

        selected_fmts = self._selected_exts()
        if not selected_fmts:
            self._set_status("Veuillez sélectionner au moins un format.")
            return

        self._set_status("Scan en cours…")
        self._files = scan_directory(path, selected_fmts)
        self._scanned_exts = set(selected_fmts)
        # Sous-dossiers de sortie (« Reduced ») écartés : on ne reconvertit pas
        # les images déjà converties
        self._scanned_excl = self._output_target()[1] if self._mode == "image" else ""
        if self._scanned_excl:
            excl = self._scanned_excl.lower()
            root = os.path.normpath(path)
            self._files = [
                f for f in self._files
                if excl not in (part.lower() for part in
                                os.path.relpath(os.path.dirname(f.path), root).split(os.sep))]
        self._set_refresh_pulse(False)
        self._remember_directory(path)
        self._refresh_list()

        n = len(self._files)
        self._set_status(f"{n} fichier(s) trouvé(s) dans {path}")
        get_app_logger().info("Scan: %d fichiers dans %s", n, path)

    def _populate_table(self):
        self._table.setSortingEnabled(False)
        self._table.setRowCount(0)
        self._table.blockSignals(True)

        for fi in self._files:
            row = self._table.rowCount()
            self._table.insertRow(row)

            # Play (icône affichée au survol de la ligne)
            play = QTableWidgetItem("")
            play.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            play.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self._table.setItem(row, COL_PLAY, play)

            # Checkbox — stores FileInfo as UserRole data
            chk = QTableWidgetItem()
            chk.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
            chk.setCheckState(Qt.CheckState.Unchecked)
            chk.setData(Qt.ItemDataRole.UserRole, fi)
            self._table.setItem(row, COL_CHECK, chk)

            # Name
            self._table.setItem(row, COL_NAME, QTableWidgetItem(fi.name))

            # Directory (relative if long)
            self._table.setItem(row, COL_DIR,  QTableWidgetItem(fi.directory))

            # Size
            size_item = _SizeItem(fi.size, fi.size_str())
            size_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self._table.setItem(row, COL_SIZE, size_item)

            # Date
            dt = datetime.fromtimestamp(fi.date_created).strftime("%d/%m/%Y  %H:%M")
            self._table.setItem(row, COL_DATE, _DateItem(fi.date_created, dt))

            # Extension
            ext_item = QTableWidgetItem(fi.extension.upper())
            ext_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self._table.setItem(row, COL_EXT, ext_item)

        self._table.blockSignals(False)
        self._table.setSortingEnabled(True)
        self._hover_row = -1
        self._update_convert_btn()

    def _refresh_list(self):
        """Affiche self._files dans la liste du mode courant."""
        if self._mode == "image":
            self._image_panel.populate(self._files, self._dir_edit.text().strip())
            n, d = self._image_panel.file_count(), self._image_panel.folder_count()
            self._lbl_count.setText(
                f"{n} image(s)" + (f" dans {d} dossier(s)" if d else "") if n
                else "Aucune image — glissez un dossier ici")
        else:
            self._populate_table()
            n = len(self._files)
            self._lbl_count.setText(f"{n} fichier(s) trouvé(s)" if n
                                    else "Aucun fichier — glissez un dossier ici")

    def _set_all_checked(self, state: bool):
        if self._mode == "image":
            self._image_panel.set_all_checked(state)
            return
        self._table.blockSignals(True)
        cs = Qt.CheckState.Checked if state else Qt.CheckState.Unchecked
        for row in range(self._table.rowCount()):
            item = self._table.item(row, COL_CHECK)
            if item:
                item.setCheckState(cs)
        self._table.blockSignals(False)
        self._update_convert_btn()

    def _on_item_changed(self, item: QTableWidgetItem):
        if item.column() != COL_CHECK:
            return
        selected_rows = {idx.row() for idx in self._table.selectedIndexes()}
        if item.row() in selected_rows and len(selected_rows) > 1:
            new_state = item.checkState()
            self._table.blockSignals(True)
            for r in selected_rows:
                if r == item.row():
                    continue
                chk = self._table.item(r, COL_CHECK)
                if chk:
                    chk.setCheckState(new_state)
            self._table.blockSignals(False)
        self._update_convert_btn()

    def _on_context_menu(self, pos):
        import subprocess
        row = self._table.rowAt(pos.y())
        if row < 0:
            return
        chk = self._table.item(row, COL_CHECK)
        if not chk:
            return
        fi: FileInfo = chk.data(Qt.ItemDataRole.UserRole)
        if not fi:
            return

        menu = QMenu(self)
        menu.setStyleSheet(self.styleSheet() + """
            QMenu {
                background: rgba(20, 18, 35, 252);
                border: 1px solid rgba(255,255,255,16);
                border-radius: 8px;
                padding: 4px;
            }
            QMenu::item {
                padding: 8px 20px 8px 14px;
                border-radius: 6px;
                color: rgba(255,255,255,200);
                font-size: 13px;
            }
            QMenu::item:selected {
                background: rgba(110,88,220,160);
                color: white;
            }
            QMenu::separator {
                height: 1px;
                background: rgba(255,255,255,12);
                margin: 4px 8px;
            }
        """)

        file_exists = os.path.isfile(fi.path)

        mc = PALETTE["dark"]["text"]                 # menu toujours sombre
        act_tags      = menu.addAction(icon("tag", mc, 16), "Éditer les tags…")
        act_tags.setEnabled(file_exists and is_editable(fi.extension))
        act_tags.setVisible(self._mode == "audio")
        menu.addSeparator()
        act_open_dir  = menu.addAction(icon("folder", mc, 16), "Ouvrir le répertoire")
        act_open_file = menu.addAction(icon("open", mc, 16), "Ouvrir le fichier")
        act_open_file.setEnabled(file_exists)
        menu.addSeparator()
        act_sel_dir   = menu.addAction(icon("select", mc, 16),
                                       "Sélectionner tous les fichiers de ce répertoire")
        menu.addSeparator()
        act_delete    = menu.addAction(icon("trash", mc, 16), "Envoyer à la corbeille")
        act_delete.setEnabled(file_exists)

        action = menu.exec(self._table.viewport().mapToGlobal(pos))

        if action == act_tags:
            self._edit_tags(fi.path)

        elif action == act_open_dir:
            norm = os.path.normpath(fi.path)
            if os.path.isfile(norm):
                # File exists → select it in Explorer
                subprocess.Popen(["explorer", "/select,", norm])
            else:
                # File gone → just open the directory
                subprocess.Popen(["explorer", os.path.normpath(fi.directory)])

        elif action == act_open_file:
            try:
                os.startfile(fi.path)
            except Exception as e:
                QMessageBox.warning(self, "Erreur", f"Impossible d'ouvrir le fichier :\n{e}")

        elif action == act_sel_dir:
            target_dir = fi.directory
            self._table.blockSignals(True)
            for r in range(self._table.rowCount()):
                chk_item = self._table.item(r, COL_CHECK)
                if chk_item:
                    row_fi: FileInfo = chk_item.data(Qt.ItemDataRole.UserRole)
                    if row_fi and row_fi.directory == target_dir:
                        chk_item.setCheckState(Qt.CheckState.Checked)
            self._table.blockSignals(False)
            self._update_convert_btn()

        elif action == act_delete:
            reply = QMessageBox.question(
                self, "Confirmer la suppression",
                f"Envoyer ce fichier à la corbeille ?\n\n{fi.path}",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.Yes:
                try:
                    if not send_to_recycle_bin([fi.path]):
                        raise RuntimeError("opération refusée ou annulée")
                    self._table.removeRow(row)
                    self._files = [f for f in self._files if f.path != fi.path]
                    n = self._table.rowCount()
                    self._lbl_count.setText(f"{n} fichier(s)")
                    self._update_convert_btn()
                    get_app_logger().info("Fichier envoyé à la corbeille : %s", fi.path)
                except Exception as e:
                    QMessageBox.critical(self, "Erreur", f"Impossible de mettre à la corbeille :\n{e}")

    # ── Pré-écoute ────────────────────────────────────────────────────────────

    def _preview_file(self, path: str):
        if not self._preview.play_file(path):
            self._set_status("Pré-écoute indisponible (QtMultimedia manquant).")
            return
        self._playing_path = path
        self._refresh_play_column()
        self._set_status(f"Pré-écoute : {os.path.basename(path)}")

    def _on_preview_stopped(self):
        self._playing_path = ""
        self._refresh_play_column()

    # ── Colonne play (survol + lecture) ───────────────────────────────────────

    def _row_fileinfo(self, row: int) -> Optional[FileInfo]:
        chk = self._table.item(row, COL_CHECK)
        return chk.data(Qt.ItemDataRole.UserRole) if chk else None

    def _play_icon_for_row(self, row: int) -> str:
        fi = self._row_fileinfo(row)
        if fi and self._playing_path and fi.path == self._playing_path:
            return "stop"                     # en cours de lecture → clic = stop
        if row == self._hover_row:
            return "play"
        return ""

    def _set_play_cell(self, item: QTableWidgetItem, row: int):
        name = self._play_icon_for_row(row)
        color = PALETTE.get(self._settings.get("theme", "dark"), PALETTE["dark"])["text"]
        item.setIcon(icon(name, color, 14) if name else QIcon())

    def _refresh_play_column(self):
        for row in range(self._table.rowCount()):
            item = self._table.item(row, COL_PLAY)
            if item:
                self._set_play_cell(item, row)

    def _on_cell_entered(self, row: int, _col: int):
        if row == self._hover_row:
            return
        old, self._hover_row = self._hover_row, row
        for r in (old, row):
            if 0 <= r < self._table.rowCount():
                item = self._table.item(r, COL_PLAY)
                if item:
                    self._set_play_cell(item, r)

    def _on_table_left(self):
        old, self._hover_row = self._hover_row, -1
        if 0 <= old < self._table.rowCount():
            item = self._table.item(old, COL_PLAY)
            if item:
                self._set_play_cell(item, old)

    def _on_cell_clicked(self, row: int, col: int):
        if col != COL_PLAY:
            return
        fi = self._row_fileinfo(row)
        if not fi:
            return
        if fi.path == self._playing_path:
            self._preview.stop_and_hide()      # → _on_preview_stopped
        elif os.path.isfile(fi.path):
            self._preview_file(fi.path)

    # ── Éditeur de tags ───────────────────────────────────────────────────────

    def _edit_tags(self, path: str):
        # Le lecteur garde un verrou sur le fichier → le libérer avant écriture
        if self._preview.current_source() == path:
            self._preview.stop_and_hide()

        dlg = TagEditorDialog(
            path,
            dark=(self._settings.get("theme", "dark") == "dark"),
            parent=self,
        )
        dlg.setStyleSheet(self.styleSheet())
        dlg.exec()
        if dlg.saved:
            self._set_status(f"Tags enregistrés : {os.path.basename(path)}")
            get_app_logger().info("Tags modifiés : %s", path)

    # ── Glisser-déposer ───────────────────────────────────────────────────────

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        if getattr(self, "_converting", False):
            self._set_status("Conversion en cours — attendez la fin pour changer de fichiers.")
            return
        paths = [u.toLocalFile() for u in event.mimeData().urls() if u.toLocalFile()]
        dirs  = [p for p in paths if os.path.isdir(p)]
        files = [p for p in paths if os.path.isfile(p)]
        if not dirs and not files:
            return
        event.acceptProposedAction()

        selected_fmts = self._selected_exts()
        all_exts = self._all_exts()

        new_files: List[FileInfo] = []
        for d in dirs:
            new_files += scan_directory(d, selected_fmts or list(all_exts))
        for f in files:
            # Fichier déposé explicitement → accepté quel que soit le filtre
            ext = os.path.splitext(f)[1].lstrip(".").lower()
            if ext in all_exts:
                fi = file_info_from_path(f)
                if fi:
                    new_files.append(fi)

        if dirs:
            self._dir_edit.setText(dirs[0])
            self._settings["last_directory"] = dirs[0]
            self._remember_directory(dirs[0])
            self._scanned_exts = set(selected_fmts or all_exts)
            self._set_refresh_pulse(False)
            self._suggest_estimate(dirs[0])

        existing = {f.path for f in self._files}
        added = [fi for fi in new_files if fi.path not in existing]
        self._files += added
        self._refresh_list()
        self._show_work()

        self._set_status(f"{len(added)} fichier(s) ajouté(s) par glisser-déposer")
        get_app_logger().info("Drag & drop : %d fichier(s) ajouté(s)", len(added))

    def _update_convert_btn(self):
        if self._mode == "image":
            count = self._image_panel.checked_count()
        else:
            count = sum(
                1 for row in range(self._table.rowCount())
                if self._table.item(row, COL_CHECK) and
                   self._table.item(row, COL_CHECK).checkState() == Qt.CheckState.Checked
            )
        self._btn_convert.setEnabled(count > 0)
        if count > 0:
            self._btn_convert.setText(f" Convertir  ({count})")
        else:
            self._btn_convert.setText(" Convertir")
        total = (self._image_panel.file_count() if self._mode == "image"
                 else self._table.rowCount())
        self._update_select_button(count, total)
        QTimer.singleShot(0, self._align_select_button)
        self._schedule_estimate()

    def _update_select_button(self, count: int, total: int):
        """Icône et info-bulle de la case « tout sélectionner » selon la sélection."""
        self._sel_count, self._sel_total = count, total
        if total and count >= total:
            ic, tip = "select_all", f"Tout est sélectionné ({total})\nCliquer pour tout désélectionner"
        elif count:
            ic, tip = "select_some", f"{count} sur {total} sélectionné(s)\nCliquer pour tout sélectionner"
        else:
            ic, tip = "select_none", "Rien n'est sélectionné\nCliquer pour tout sélectionner"
        self._set_icon(self._btn_select, ic, "text", 16)
        self._btn_select.setToolTip(tip)
        self._btn_select.setEnabled(total > 0)

    # Centre de la case à cocher d'une ligne, depuis le début de sa cellule
    # (mesuré : rembourrage de 8 px de ::item + demi-largeur de l'indicateur)
    _CHECK_CENTER = 19

    def _align_select_button(self):
        """Place la case globale exactement au-dessus de la colonne des cases."""
        if not hasattr(self, "_sel_spacer"):
            return
        if self._mode == "image":
            view = self._image_panel.tree
            cell_x = view.header().sectionViewportPosition(0) + view.indentation()
        else:
            view = self._table
            cell_x = view.columnViewportPosition(COL_CHECK)
        if not view.isVisible():
            return
        center = view.viewport().mapTo(self._list_panel, QPoint(cell_x + self._CHECK_CENTER, 0)).x()
        left_margin = self._list_panel.layout().contentsMargins().left()
        row_spacing = 6                     # espacement de tool_row entre la cale et le bouton
        self._sel_spacer.setFixedWidth(max(0, round(
            center - self._btn_select.width() / 2 - left_margin - row_spacing)))

    def eventFilter(self, obj, event):
        if obj is getattr(self, "_list_panel", None) and event.type() == QEvent.Type.Resize:
            QTimer.singleShot(0, self._align_select_button)
            self._schedule_place_activity()
        return super().eventFilter(obj, event)

    # ── Ligne d'activité : sur la ligne des cases si elle y tient ──────────────

    def _schedule_place_activity(self):
        if not hasattr(self, "_act_timer"):
            self._act_timer = QTimer(self)
            self._act_timer.setSingleShot(True)
            self._act_timer.setInterval(0)
            self._act_timer.timeout.connect(self._place_activity)
        self._act_timer.start()

    def _place_activity(self):
        self._update_gain_button()
        P = self._image_panel
        act, legend = P.activity, P.legend
        left = (self._sel_spacer.width() + self._btn_select.width()
                + (self._gain_box.sizeHint().width() + 6 if self._gain_box.isVisible() else 0)
                + self._lbl_count.sizeHint().width() + 6 * 3 + 10)
        need = act.sizeHint().width() + 2 * 24
        if legend.isVisible() or legend.parent() is not P.act_row:
            need += legend.sizeHint().width() + 12
        avail = self._list_panel.width() - 24 - left
        up = self._mode == "image" and need <= avail
        if up and act.parent() is P.act_row:
            P.act_layout.removeWidget(act)
            P.act_layout.removeWidget(legend)
            self._act_slot.addWidget(act)
            self._legend_slot.addWidget(legend)
        elif not up and act.parent() is not P.act_row:
            self._act_slot.removeWidget(act)
            self._legend_slot.removeWidget(legend)
            P.act_layout.insertWidget(0, act, 1)
            P.act_layout.addWidget(legend)
        P.act_row.setVisible(act.parent() is P.act_row)
        # Centrée sur la ligne des cases, alignée à gauche sous celle-ci
        P._lbl_activity.setAlignment(
            (Qt.AlignmentFlag.AlignCenter if up else Qt.AlignmentFlag.AlignLeft)
            | Qt.AlignmentFlag.AlignVCenter)
        act.setVisible(bool(P._lbl_activity.text()))

    # ── Sélection par gain estimé ─────────────────────────────────────────────

    def _update_gain_button(self):
        image = self._mode == "image"
        has = image and self._image_panel.has_estimates()
        t = self._gain_threshold()
        self._gain_box.setVisible(image)
        self._btn_select_gain.setEnabled(has)
        self._btn_select_gain.setToolTip(
            f"Coche les dossiers dont le gain estimé atteint {t} % ou plus\n"
            "(les autres sont décochés). Seuil modifiable à droite." if has else
            f"Sélectionner les dossiers à {t} % de gain ou plus :\n"
            "lancez d'abord « Estimer le gain d'espace ».")

    def _gain_threshold(self) -> int:
        try:
            return int(self._edit_gain.text())
        except ValueError:
            return GAIN_SELECT_DEFAULT

    def _on_gain_threshold_changed(self, *_):
        self._settings["gain_select_threshold"] = self._gain_threshold()
        self._update_gain_button()

    def _select_by_gain(self):
        if not self._image_panel.has_estimates():
            return
        t = self._gain_threshold()
        n_dirs, n_files = self._image_panel.select_by_gain(t)
        self._set_status(
            f"{n_dirs} dossier(s) à {t} % de gain ou plus sélectionné(s) "
            f"— {n_files} image(s).")

    def _toggle_select_all(self):
        # Tout coché → tout décocher ; sinon (rien ou une partie) → tout cocher
        everything = self._sel_total and self._sel_count >= self._sel_total
        self._set_all_checked(not everything)

    def _on_format_changed(self):
        self._update_fmt_desc()
        fmt = self._combo_out_fmt.currentData()
        if self._mode == "image" and fmt:
            self._settings["image_output_format"] = fmt["id"]
            q = self._settings.get("image_quality", {}).get(fmt["id"], fmt["default_quality"])
            self._slider_quality.blockSignals(True)
            self._slider_quality.setValue(q)
            self._slider_quality.blockSignals(False)
            self._lbl_quality_val.setText(str(q) if fmt["quality"] else "—")
            for w in (self._lbl_quality, self._slider_quality, self._lbl_quality_val):
                w.setEnabled(fmt["quality"])
            self._image_panel.mark_stale()
            self._schedule_estimate()

    def _update_fmt_desc(self):
        fmt = self._combo_out_fmt.currentData()
        if fmt:
            self._lbl_fmt_desc.setText(fmt.get("description", ""))

    # ── Mode Audio / Images ───────────────────────────────────────────────────

    def _set_mode(self, mode: str):
        if mode == self._mode:
            return
        if self._thread and self._thread.isRunning():
            # Pas de changement de mode en pleine conversion
            self._mode_buttons[self._mode].setChecked(True)
            self._set_status("Conversion en cours — changement de mode impossible.")
            return
        self._save_settings()
        self._mode = mode
        self._settings["mode"] = mode
        self._files = []
        self._scanned_exts = None
        self._set_refresh_pulse(False)
        self._image_panel.cancel_estimate(silent=True)
        self._apply_mode()
        self._refresh_list()
        if self._screens.currentIndex() == 1 and os.path.isdir(self._dir_edit.text().strip()):
            self._scan_directory()          # même dossier, formats du nouveau mode
        self._save_settings()

    def _apply_mode(self):
        image = self._mode == "image"
        self._mode_buttons[self._mode].setChecked(True)
        self._home.set_mode(self._mode)
        self._fmt_stack.setCurrentIndex(list(_INPUT_FORMATS).index(self._mode))
        self._btn_analyze.setVisible(image)
        self._list_stack.setCurrentWidget(self._image_panel if image else self._table)
        QTimer.singleShot(0, self._align_select_button)
        if not image:
            self._toast.dismiss()
        self._img_opts_row.setVisible(image)
        if hasattr(self, "_btn_select_gain"):
            self._schedule_place_activity()
        self._lbl_estimate.clear()
        # Pré-écoute et tags n'ont de sens qu'en audio
        self._table.setColumnHidden(COL_PLAY, image)
        if image:
            self._preview.stop_and_hide()

        formats = IMAGE_OUTPUT_FORMATS if image else OUTPUT_FORMATS
        default_id = self._settings.get(
            "image_output_format" if image else "default_output_format", formats[0]["id"])
        self._combo_out_fmt.blockSignals(True)
        self._combo_out_fmt.clear()
        for i, fmt in enumerate(formats):
            self._combo_out_fmt.addItem(fmt["label"], userData=fmt)
            if fmt["id"] == default_id:
                self._combo_out_fmt.setCurrentIndex(i)
        self._combo_out_fmt.blockSignals(False)
        self._on_format_changed()

    def _image_options(self):
        """(format, qualité, côté max, garder si plus léger) du mode Images."""
        fmt = self._combo_out_fmt.currentData()
        quality = self._slider_quality.value() if fmt["quality"] else 100
        return fmt, quality, self._combo_max_side.currentData(), self._chk_keep.isChecked()

    def _image_options_summary(self) -> str:
        fmt, quality, max_side, keep = self._image_options()
        parts = [fmt["label"]]
        if fmt["quality"]:
            parts.append(f"qualité {quality}")
        parts.append(f"côté max {max_side} px" if max_side else "taille d'origine")
        if keep:
            parts.append("original gardé si plus lourd")
        suffix, subdir = self._output_target()
        if subdir:
            parts.append(f"dans .\\{subdir}")
        parts.append(f"conflits renommés « {suffix} »" if suffix else "conflits écrasés")
        return ", ".join(parts)

    def _output_target(self):
        """(suffixe de renommage ou "" pour écraser, sous-dossier ou "")."""
        suffix = clean_name(self._edit_suffix.text(), "_v2") if self._chk_rename.isChecked() else ""
        subdir = clean_name(self._edit_subdir.text(), "Reduced") if self._chk_subdir.isChecked() else ""
        return suffix, subdir

    def _on_output_option_changed(self, *_):
        self._edit_suffix.setEnabled(self._chk_rename.isChecked())
        self._edit_subdir.setEnabled(self._chk_subdir.isChecked())
        self._settings["image_rename_conflicts"] = self._chk_rename.isChecked()
        self._settings["image_rename_suffix"]    = self._edit_suffix.text()
        self._settings["image_use_subdir"]       = self._chk_subdir.isChecked()
        self._settings["image_subdir"]           = self._edit_subdir.text()
        if hasattr(self, "_refresh_buttons"):
            self._on_formats_changed()      # sous-dossier exclu de la liste → Actualiser

    def _on_quality_changed(self, value: int):
        self._lbl_quality_val.setText(str(value))
        fmt = self._combo_out_fmt.currentData()
        if fmt:
            self._settings.setdefault("image_quality", {})[fmt["id"]] = value
        self._image_panel.mark_stale()
        self._schedule_estimate()

    def _on_image_option_changed(self, *_):
        self._settings["image_max_side"]       = self._combo_max_side.currentData()
        self._settings["image_keep_if_larger"] = self._chk_keep.isChecked()
        self._image_panel.mark_stale()
        self._schedule_estimate()

    # ── Estimation de la taille (mode Images) ─────────────────────────────────

    def _schedule_estimate(self):
        if self._mode != "image":
            return
        self._estimate_timer.start()      # relancé à chaque changement (anti-rebond)

    def _run_estimate(self):
        if self._mode != "image":
            return
        if self._estimate_thread and self._estimate_thread.isRunning():
            # Résultat bientôt périmé : on l'abandonne et on relance à la fin
            self._estimate_thread.cancel()
            self._estimate_pending = True
            return
        files = self._get_selected_files()
        if not files:
            self._lbl_estimate.setText("")
            return
        fmt, quality, max_side, keep = self._image_options()
        self._lbl_estimate.setText(f"Estimation en cours…  ({len(files)} image(s))")
        self._estimate_thread = EstimateThread(
            files, fmt, quality, max_side, keep,
            parallel=os.cpu_count() or 4,
        )
        self._estimate_thread.finished_estimate.connect(self._on_estimate)
        self._estimate_thread.finished.connect(self._on_estimate_thread_finished)
        self._estimate_thread.start()

    def _on_estimate_thread_finished(self):
        if self._estimate_pending:
            self._estimate_pending = False
            self._run_estimate()

    def _on_estimate(self, est: Optional[Estimate]):
        if self._estimate_pending or est is None or self._mode != "image":
            return
        approx = "" if est.exact else "≈ "
        margin = "" if est.exact else f"  (± {est.margin * 100:.0f} %)"
        sign = "−" if est.gain_pct >= 0 else "+"
        color = gain_color(est.gain_pct).name()
        self._lbl_estimate.setText(
            f"Sélection : {fmt_bytes(est.src_bytes)}  →  {approx}{fmt_bytes(est.est_bytes)}"
            f"&nbsp;&nbsp; <b style='color:{color}'>{sign}{abs(est.gain_pct):.0f} %</b>{margin}"
        )
        self._lbl_estimate.setToolTip(
            f"{est.n_samples} image(s) convertie(s) en test sur {est.n_files}.\n"
            "Le reste est extrapolé d'après la qualité et la taille de chaque fichier."
        )

    # ── Estimation du gain d'espace (colonnes de la liste) ────────────────────

    def _suggest_estimate(self, path: str):
        """Toast non bloquant proposant d'estimer le gain d'espace (mode Images)."""
        if self._mode != "image":
            return
        name = os.path.basename(os.path.normpath(path)) or path
        # Au-dessus du panneau du bas et de la barre d'état
        self._central.toast_bottom_offset = (
            self._panel_bottom.height() + self._status_lbl.parentWidget().height() + 26)
        self._toast.show_message(
            f"Voulez-vous savoir combien de place la conversion ferait gagner dans "
            f"<b>{name}</b> et ses sous-dossiers ?",
            " Estimer", self._start_estimate, action_icon="estimate")

    def _toggle_estimate(self):
        if self._image_panel.is_running():
            self._image_panel.cancel_estimate()
        else:
            self._start_estimate()

    def _start_estimate(self):
        self._toast.dismiss()       # lancée depuis le bouton du haut : la suggestion est caduque
        # Rien d'affiché : on charge d'abord le dossier choisi
        if not self._image_panel.file_count():
            self._scan_directory()
        if not self._image_panel.file_count():
            return
        fmt, quality, max_side, keep = self._image_options()
        parallel = self._settings.get("parallel", 8) or (os.cpu_count() or 4)
        self._image_panel.start_estimate(fmt, quality, max_side, keep, parallel)

    def _on_estimate_running(self, running: bool):
        self._update_gain_button()
        self._btn_analyze.setText(" Arrêter l'estimation" if running
                                  else " Estimer le gain d'espace")
        self._set_icon(self._btn_analyze, "stop" if running else "estimate", "on_accent",
                       15 if running else 18)

    # ── Conversion ────────────────────────────────────────────────────────────

    def _get_selected_files(self) -> List[FileInfo]:
        if self._mode == "image":
            return self._image_panel.checked_files()
        selected = []
        for row in range(self._table.rowCount()):
            chk = self._table.item(row, COL_CHECK)
            if chk and chk.checkState() == Qt.CheckState.Checked:
                # Retrieve FileInfo by matching path (stored as tooltip)
                name_item = self._table.item(row, COL_NAME)
                dir_item  = self._table.item(row, COL_DIR)
                ext_item  = self._table.item(row, COL_EXT)
                if name_item and dir_item and ext_item:
                    name = name_item.text()
                    directory = dir_item.text()
                    ext = ext_item.text().lower()
                    path = os.path.join(directory, f"{name}.{ext}")
                    for fi in self._files:
                        if fi.path == path:
                            selected.append(fi)
                            break
        return selected

    def _start_conversion(self):
        from core.ffmpeg_manager import FFmpegManager
        from core.config import FFMPEG_DIR

        image = self._mode == "image"
        ffmpeg = FFmpegManager()
        if not image and not ffmpeg.is_available():
            self._set_status("FFmpeg introuvable.")
            return

        selected = self._get_selected_files()
        if not selected:
            return

        out_fmt = self._combo_out_fmt.currentData()
        if not out_fmt:
            return

        # Detect conflicts (mode Images : réglés par les options Renommer / Sous-dossier)
        conflicts = [] if image else detect_conflicts(selected, out_fmt)
        conflict_mode = "rename"
        if image:
            suffix, subdir = self._output_target()
            conflict_mode = "rename" if suffix else "overwrite"

        if conflicts:
            dlg = _ConflictDialog(conflicts, out_fmt["ext"], self)
            dlg.setStyleSheet(self.styleSheet())
            if dlg.exec() != QDialog.DialogCode.Accepted:
                return
            choice = dlg.get_choice()
            if choice is None:
                return
            conflict_mode = choice

        # Stop preview: release any file lock before converting/deleting
        self._preview.stop_and_hide()
        if self._estimate_thread and self._estimate_thread.isRunning():
            self._estimate_thread.cancel()

        # Get parallel setting
        parallel = self._settings.get("parallel", 8)
        delete   = self._chk_delete.isChecked()
        self._set_busy(True)

        # Setup UI
        self._progress_row.show()
        self._btn_convert.hide()
        self._btn_cancel_conv.show()
        self._progress_bar.setValue(0)
        self._lbl_progress.setText(f"Conversion en cours…  0 / {len(selected)}")
        self._set_status(f"Conversion de {len(selected)} fichier(s)…")

        # Init summary
        import time
        self._conv_sizes = {f.path: f.size for f in selected}
        self._conv_summary = {
            "total":        len(selected),
            "success":      [],   # list of source paths
            "skipped":      [],   # images laissées intactes (résultat plus lourd)
            "failed":       [],   # list of (basename, error_msg)
            "src_size":     0,    # originaux traités (convertis + gardés)
            "out_size":     0,
            "to_recycle":   [],   # originaux convertis, à envoyer à la Corbeille
            "delete_source": delete,
            "cancelled":    False,
            "t0":           time.monotonic(),
            "fmt_label":    self._image_options_summary() if image else out_fmt["label"],
            "folder":       self._dir_edit.text().strip(),
        }

        # Start thread
        if image:
            _fmt, quality, max_side, keep = self._image_options()
            self._thread = ImageConversionThread(
                files          = selected,
                out_fmt        = out_fmt,
                quality        = quality,
                max_side       = max_side,
                keep_if_larger = keep,
                parallel       = parallel,
                conflict       = conflict_mode,
                suffix         = suffix,
                subdir         = subdir,
                recycle_replaced = delete,
            )
        else:
            self._thread = ConversionThread(
                files         = selected,
                ffmpeg_path   = ffmpeg.get_ffmpeg_path(),
                out_fmt       = out_fmt,
                parallel      = parallel,
                conflict      = conflict_mode,
            )
        self._thread.progress_updated.connect(self._on_progress)
        self._thread.file_completed.connect(self._on_file_done)
        self._thread.all_done.connect(self._on_all_done)
        self._thread.start()

    def _cancel_conversion(self):
        if self._thread:
            self._thread.cancel()
            self._conv_summary["cancelled"] = True
            self._set_status("Annulation en cours…")

    def _on_progress(self, completed: int, total: int):
        pct = int(completed / total * 100) if total else 0
        self._progress_bar.setValue(pct)
        self._lbl_progress.setText(f"Conversion en cours…  {completed} / {total}")

    def _on_file_done(self, src_path: str, out_path: str, success: bool, msg: str):
        s = self._conv_summary
        size = self._conv_sizes.get(src_path, 0)
        if success and msg == SKIPPED:
            s["skipped"].append(src_path)
            s["src_size"] += size
            s["out_size"] += size                          # l'original reste
        elif success:
            s["success"].append(src_path)
            s["src_size"] += size
            if out_path and os.path.exists(out_path):
                s["out_size"] += os.path.getsize(out_path)
            if msg == REPLACED:
                # Original remplacé par sa sortie : déjà passé par la Corbeille
                s["replaced_recycled"] = s.get("replaced_recycled", 0) + 1
            elif os.path.normcase(os.path.abspath(out_path)) != os.path.normcase(os.path.abspath(src_path)):
                s["to_recycle"].append(src_path)
        else:
            s["failed"].append((os.path.basename(src_path), msg))
            self._set_status(f"Erreur : {os.path.basename(src_path)} — {msg[:80]}")

    def _on_all_done(self):
        import time
        s = self._conv_summary
        s["duration"] = time.monotonic() - s["t0"]
        self._progress_bar.setValue(100)
        s["recycled"], s["recycle_error"] = 0, False
        if s["delete_source"] and s["to_recycle"]:
            n = len(s["to_recycle"])
            self._lbl_progress.setText(f"Envoi de {n} original(aux) à la corbeille…")
            self._set_status("Envoi des originaux à la corbeille…")
            QApplication.processEvents()
            if send_to_recycle_bin(s["to_recycle"]):
                s["recycled"] = sum(1 for p in s["to_recycle"] if not os.path.exists(p))
            s["recycle_error"] = s["recycled"] < n
            get_app_logger().info("Corbeille : %d / %d original(aux)", s["recycled"], n)
        s["recycled"] += s.get("replaced_recycled", 0)
        self._lbl_progress.setText("Conversion arrêtée" if s["cancelled"] else "Conversion terminée !")
        self._btn_cancel_conv.hide()
        self._btn_convert.show()
        self._set_busy(False)
        self._set_status("Conversion arrêtée." if s["cancelled"] else "Conversion terminée.")
        QTimer.singleShot(3000, self._hide_progress)
        if not s["cancelled"]:
            n_ok = len(s["success"])
            text = f"{n_ok} fichier(s) converti(s) en {self._fmt_duration(s['duration'])}"
            if s["failed"]:
                text += f", {len(s['failed'])} erreur(s)"
            if s["src_size"]:
                diff = s["src_size"] - s["out_size"]
                text += (f" — {fmt_bytes(diff)} de moins" if diff >= 0
                         else f" — {fmt_bytes(-diff)} de plus")
            self._notify_done("Conversion terminée" if not s["failed"]
                              else "Conversion terminée avec des erreurs", text)
        dlg = SummaryDialog(s, dark=self._settings.get("theme", "dark") == "dark", parent=self)
        dlg.exec()
        # Des originaux ont pu partir à la Corbeille, des fichiers sont apparus : relire
        if s["recycled"] or s["success"]:
            self._scan_directory()

    def _notify_done(self, title: str, text: str):
        """Son si l'app est au premier plan, notification Windows sinon."""
        if not self._settings.get("notify_when_done", True):
            return
        if not hasattr(self, "_notifier"):
            self._notifier = Notifier(self)
        self._notifier.notify(title, text)

    @staticmethod
    def _fmt_duration(sec: float) -> str:
        sec = int(round(sec))
        if sec < 60:
            return f"{sec} s"
        m, s = divmod(sec, 60)
        return f"{m} min {s:02d} s" if m < 60 else f"{m // 60} h {m % 60:02d} min"

    def _set_busy(self, busy: bool):
        """Pendant la conversion : sélection, dossier, formats et réglages verrouillés."""
        self._converting = busy
        for w in (self._panel_top, self._list_panel, self._img_opts_row,
                  self._combo_out_fmt, self._chk_delete, *self._mode_buttons.values()):
            w.setEnabled(not busy)
        if busy:
            self._toast.dismiss()

    def _hide_progress(self):
        self._progress_row.hide()
        self._progress_bar.setValue(0)

    # ── Log window ────────────────────────────────────────────────────────────

    def _toggle_log(self):
        if self._log_window is None:
            self._log_window = LogWindow(
                theme=self._settings.get("theme", "dark")
            )
            self._log_window.setStyleSheet(self.styleSheet())

        if self._log_window.isVisible():
            self._log_window.hide()
        else:
            geo = self.geometry()
            self._log_window.move(geo.x() + 40, geo.y() + geo.height() - 540)
            self._log_window.show()
            self._log_window.raise_()

    # ── Settings ──────────────────────────────────────────────────────────────

    def _open_settings(self):
        dlg = SettingsDialog(self._settings, self)
        dlg.setStyleSheet(self.styleSheet())
        dlg.settings_changed.connect(self._apply_settings)
        dlg.exec()

    def _apply_settings(self, new_settings: dict):
        self._settings.update(new_settings)
        self._save_settings()
        self._apply_theme()

        # Propagate theme to open log window
        if self._log_window:
            self._log_window.apply_stylesheet(self.styleSheet())


    def _apply_theme(self):
        theme = self._settings.get("theme", "dark")
        qss   = get_theme(theme)
        self.setStyleSheet(qss)
        self._refresh_icons()
        style_table(self._table, theme)
        if hasattr(self, "_home"):
            self._home.set_theme(theme)
        if hasattr(self, "_image_panel"):
            self._image_panel.apply_theme(theme)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _set_icon(self, btn: QPushButton, name: str, role: str = "text", px: int = 18):
        """Icône au trait, couleur selon le rôle et le thème (mise à jour au changement)."""
        self._icon_buttons = [e for e in self._icon_buttons if e[0] is not btn]
        self._icon_buttons.append((btn, name, role, px))
        theme = self._settings.get("theme", "dark")
        btn.setIcon(icon(name, PALETTE.get(theme, PALETTE["dark"])[role], px))
        btn.setIconSize(QSize(px, px))

    def _refresh_icons(self):
        for btn, name, role, px in list(getattr(self, "_icon_buttons", [])):
            self._set_icon(btn, name, role, px)

    def _set_status(self, msg: str):
        self._status_lbl.setText(msg)

    def _toggle_maximize(self):
        if self.isMaximized():
            self.showNormal()
        else:
            self.showMaximized()

    # ── Config persistence ────────────────────────────────────────────────────

    def _load_settings(self) -> dict:
        s = dict(DEFAULT_SETTINGS)
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                s.update(json.load(f))
        except (FileNotFoundError, json.JSONDecodeError):
            pass
        return s

    def _save_settings(self):
        # Persist currently checked formats (both modes)
        for mode, checks in getattr(self, "_format_checks_by_mode", {}).items():
            self._settings[_SELECTED_KEY[mode]] = [
                name for name, cb in checks.items() if cb.isChecked()
            ]

        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(self._settings, f, indent=2, ensure_ascii=False)
        except OSError:
            pass

    # ═════════════════════════════════════════════════════════════════════════
    # WINDOW EVENTS (frameless: drag + resize)
    # ═════════════════════════════════════════════════════════════════════════

    def _tb_press(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            self._press_gpos = event.globalPosition().toPoint()

    def _tb_move(self, event):
        if self._drag_pos and event.buttons() == Qt.MouseButton.LeftButton:
            gp = event.globalPosition().toPoint()
            if self.isMaximized():
                if (gp - self._press_gpos).manhattanLength() < QApplication.startDragDistance():
                    return          # simple tremblement du clic (double-clic…)
                # Comme Windows : tirer la barre d'une fenêtre agrandie la restaure,
                # le curseur gardant sa position relative sur la barre
                ratio = self._drag_pos.x() / max(1, self.width())
                self.showNormal()
                self._drag_pos.setX(int(self.width() * ratio))
            self.move(gp - self._drag_pos)

    def _tb_release(self, _event):
        self._drag_pos = None

    def _tb_double_click(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = None
            self._toggle_maximize()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            pos   = event.position().toPoint()
            edge  = self._detect_edge(pos)
            if edge:
                self._resize_edge  = edge
                self._resize_start = event.globalPosition().toPoint()
                self._resize_geom  = self.geometry()

    def mouseMoveEvent(self, event):
        if self._resize_edge and event.buttons() == Qt.MouseButton.LeftButton:
            self._do_resize(event.globalPosition().toPoint())
            return
        # Update cursor
        edge = self._detect_edge(event.position().toPoint())
        cursors = {
            "n": Qt.CursorShape.SizeVerCursor,  "s": Qt.CursorShape.SizeVerCursor,
            "e": Qt.CursorShape.SizeHorCursor,  "w": Qt.CursorShape.SizeHorCursor,
            "ne": Qt.CursorShape.SizeBDiagCursor, "sw": Qt.CursorShape.SizeBDiagCursor,
            "nw": Qt.CursorShape.SizeFDiagCursor, "se": Qt.CursorShape.SizeFDiagCursor,
        }
        if edge:
            self.setCursor(QCursor(cursors.get(edge, Qt.CursorShape.ArrowCursor)))
        else:
            self.unsetCursor()

    def mouseReleaseEvent(self, _event):
        self._resize_edge = None

    def _detect_edge(self, pos) -> Optional[str]:
        m = self._RESIZE_MARGIN
        w, h = self.width(), self.height()
        x, y = pos.x(), pos.y()
        on_l = x < m; on_r = x > w - m
        on_t = y < m; on_b = y > h - m
        if on_l and on_t: return "nw"
        if on_r and on_t: return "ne"
        if on_l and on_b: return "sw"
        if on_r and on_b: return "se"
        if on_l: return "w"
        if on_r: return "e"
        if on_t: return "n"
        if on_b: return "s"
        return None

    def _do_resize(self, gpos):
        dx = gpos.x() - self._resize_start.x()
        dy = gpos.y() - self._resize_start.y()
        g  = self._resize_geom
        x, y, w, h = g.x(), g.y(), g.width(), g.height()
        min_w, min_h = self.minimumWidth(), self.minimumHeight()
        e = self._resize_edge

        if "e" in e: w = max(min_w, w + dx)
        if "s" in e: h = max(min_h, h + dy)
        if "w" in e:
            nw = max(min_w, w - dx)
            x  = x + (w - nw)
            w  = nw
        if "n" in e:
            nh = max(min_h, h - dy)
            y  = y + (h - nh)
            h  = nh
        self.setGeometry(x, y, w, h)

    # ── showEvent: apply Acrylic after window handle is ready ─────────────────

    def showEvent(self, event):
        super().showEvent(event)
        hwnd  = int(self.winId())
        dark  = self._settings.get("theme", "dark") == "dark"
        apply_acrylic(hwnd, dark=dark)

    def closeEvent(self, event):
        self._save_settings()
        self._preview.stop()
        if self._estimate_thread and self._estimate_thread.isRunning():
            self._estimate_thread.cancel()
            self._estimate_thread.wait(3000)
        self._image_panel.cancel_estimate(silent=True)
        if self._log_window:
            self._log_window.close()
        super().closeEvent(event)
