from PyQt6.QtCore    import Qt, pyqtSignal
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QGridLayout,
                              QLabel, QPushButton, QComboBox, QFrame, QWidget,
                              QCheckBox)
from PyQt6.QtGui     import QFont

from core.config import PARALLEL_OPTIONS
from ui.effects  import apply_acrylic


class SettingsDialog(QDialog):
    settings_changed = pyqtSignal(dict)   # emitted on Apply

    def __init__(self, current_settings: dict, parent=None):
        super().__init__(parent)
        self._settings = dict(current_settings)

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.Dialog
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(460, 350)

        self._drag_pos = None
        self._build_ui()
        self._load_values()

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

        # ── Title bar ──────────────────────────────────────────────────────
        tb = QWidget()
        tb.setObjectName("title_bar")
        tb.setFixedHeight(42)
        tb_lay = QHBoxLayout(tb)
        tb_lay.setContentsMargins(18, 0, 8, 0)

        lbl = QLabel("⚙️  Paramètres")
        lbl.setObjectName("title_label")
        lbl.setFont(QFont("Segoe UI Variable", 12, QFont.Weight.Bold))
        tb_lay.addWidget(lbl)
        tb_lay.addStretch()

        btn_close = QPushButton("✕")
        btn_close.setObjectName("btn_close")
        btn_close.clicked.connect(self.reject)
        tb_lay.addWidget(btn_close)
        lay.addWidget(tb)

        tb.mousePressEvent   = self._tb_press
        tb.mouseMoveEvent    = self._tb_move
        tb.mouseReleaseEvent = self._tb_release

        # ── Content ────────────────────────────────────────────────────────
        content = QWidget()
        c_lay   = QVBoxLayout(content)
        c_lay.setContentsMargins(24, 20, 24, 20)
        c_lay.setSpacing(18)

        grid = QGridLayout()
        grid.setHorizontalSpacing(20)
        grid.setVerticalSpacing(16)

        # Theme
        lbl_theme = QLabel("Thème")
        lbl_theme.setStyleSheet("color: rgba(255,255,255,180); font-weight: 600;")
        self._combo_theme = QComboBox()
        self._combo_theme.addItems(["Sombre", "Clair"])
        grid.addWidget(lbl_theme,         0, 0)
        grid.addWidget(self._combo_theme, 0, 1)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        grid.addWidget(sep, 1, 0, 1, 2)

        # Parallel
        lbl_para = QLabel("Conversions parallèles")
        lbl_para.setStyleSheet("color: rgba(255,255,255,180); font-weight: 600;")
        self._combo_parallel = QComboBox()
        for opt in PARALLEL_OPTIONS:
            self._combo_parallel.addItem(opt["label"], userData=opt["value"])
        grid.addWidget(lbl_para,            2, 0)
        grid.addWidget(self._combo_parallel, 2, 1)

        # Fin de tâche
        self._chk_notify = QCheckBox("Son et notification Windows en fin d'analyse ou de conversion")
        self._chk_notify.setToolTip("Son seul si l'app est au premier plan ; notification Windows sinon.")
        grid.addWidget(self._chk_notify, 3, 0, 1, 2)

        c_lay.addLayout(grid)
        c_lay.addStretch()

        # ── Buttons ────────────────────────────────────────────────────────
        btn_row = QHBoxLayout()
        btn_row.addStretch()

        btn_cancel = QPushButton("Annuler")
        btn_cancel.setFixedWidth(110)
        btn_cancel.clicked.connect(self.reject)
        btn_row.addWidget(btn_cancel)

        btn_apply = QPushButton("Appliquer")
        btn_apply.setObjectName("btn_primary")
        btn_apply.setFixedWidth(120)
        btn_apply.clicked.connect(self._apply)
        btn_row.addWidget(btn_apply)

        c_lay.addLayout(btn_row)
        lay.addWidget(content)

    def _load_values(self):
        theme    = self._settings.get("theme", "dark")
        parallel = self._settings.get("parallel", 8)

        self._combo_theme.setCurrentIndex(0 if theme == "dark" else 1)
        self._chk_notify.setChecked(self._settings.get("notify_when_done", True))

        for i, opt in enumerate(PARALLEL_OPTIONS):
            if opt["value"] == parallel:
                self._combo_parallel.setCurrentIndex(i)
                break

    # ── Actions ───────────────────────────────────────────────────────────────

    def _apply(self):
        self._settings["theme"]    = "dark" if self._combo_theme.currentIndex() == 0 else "light"
        self._settings["parallel"] = self._combo_parallel.currentData()
        self._settings["notify_when_done"] = self._chk_notify.isChecked()
        self.settings_changed.emit(dict(self._settings))
        self.accept()

    # ── Drag ──────────────────────────────────────────────────────────────────

    def _tb_press(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def _tb_move(self, event):
        if self._drag_pos and event.buttons() == Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)

    def _tb_release(self, _event):
        self._drag_pos = None

    # ── Show ──────────────────────────────────────────────────────────────────

    def showEvent(self, event):
        super().showEvent(event)
        hwnd = int(self.winId())
        dark = self._settings.get("theme", "dark") == "dark"
        apply_acrylic(hwnd, dark=dark)
