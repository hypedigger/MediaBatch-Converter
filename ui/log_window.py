import os

from PyQt6.QtCore    import Qt, QSize, pyqtSignal
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout,
                              QLabel, QPushButton, QTextEdit, QTabWidget)
from PyQt6.QtGui     import QFont, QColor, QTextCharFormat, QTextCursor

from core.config import LOGS_DIR
from core.logger import (set_app_log_callback, set_export_log_callback,
                          get_app_log_buffer, get_export_log_buffer)
from ui.effects  import apply_acrylic
from ui.icons    import icon, PALETTE


_LEVEL_COLORS = {
    "DEBUG":    "#7a7aaa",
    "INFO":     "#c8c8e0",
    "WARNING":  "#f0c060",
    "ERROR":    "#f06060",
    "CRITICAL": "#ff4040",
}


class LogWindow(QWidget):
    # Signals marshal log records from any thread → main thread safely
    _sig_app    = pyqtSignal(str, str)   # level, msg
    _sig_export = pyqtSignal(str, str)

    def __init__(self, theme: str = "dark", parent=None):
        super().__init__(parent)
        self._theme = theme

        self.setWindowFlags(
            Qt.WindowType.Window |
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setMinimumSize(700, 420)
        self.resize(820, 500)
        self.setWindowTitle("Logs")

        self._drag_pos = None
        self._build_ui()
        self._register_callbacks()

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
        title_bar = QWidget()
        title_bar.setObjectName("title_bar")
        title_bar.setFixedHeight(40)
        tb_lay = QHBoxLayout(title_bar)
        tb_lay.setContentsMargins(16, 0, 8, 0)

        lbl = QLabel("Journaux")
        lbl.setObjectName("title_label")
        tb_lay.addWidget(lbl)
        tb_lay.addStretch()

        btn_clear = QPushButton("Effacer")
        btn_clear.setObjectName("btn_icon")
        btn_clear.setFixedHeight(28)
        btn_clear.clicked.connect(self._clear_current_tab)
        tb_lay.addWidget(btn_clear)

        btn_open_dir = QPushButton(" Ouvrir le dossier")
        btn_open_dir.setObjectName("btn_icon")
        btn_open_dir.setIcon(icon("folder", PALETTE.get(self._theme, PALETTE["dark"])["muted"], 16))
        btn_open_dir.setIconSize(QSize(16, 16))
        btn_open_dir.setFixedHeight(28)
        btn_open_dir.clicked.connect(self._open_log_dir)
        tb_lay.addWidget(btn_open_dir)

        btn_close = QPushButton("✕")
        btn_close.setObjectName("btn_close")
        btn_close.clicked.connect(self.hide)
        tb_lay.addWidget(btn_close)

        lay.addWidget(title_bar)

        # ── Tabs ───────────────────────────────────────────────────────────
        self._tabs = QTabWidget()
        self._tabs.setContentsMargins(12, 8, 12, 12)

        self._app_log    = self._make_text_edit()
        self._export_log = self._make_text_edit()

        self._tabs.addTab(self._app_log,    "Application")
        self._tabs.addTab(self._export_log, "Conversions")

        content = QWidget()
        c_lay   = QVBoxLayout(content)
        c_lay.setContentsMargins(12, 8, 12, 12)
        c_lay.addWidget(self._tabs)
        lay.addWidget(content)

        # Title bar dragging
        title_bar.mousePressEvent   = self._tb_press
        title_bar.mouseMoveEvent    = self._tb_move
        title_bar.mouseReleaseEvent = self._tb_release

    def _make_text_edit(self) -> QTextEdit:
        te = QTextEdit()
        te.setReadOnly(True)
        te.setFont(QFont("Cascadia Code", 10))
        return te

    # ── Callbacks from loggers ────────────────────────────────────────────────

    def _register_callbacks(self):
        # Connect signals to slots (always runs on main thread)
        self._sig_app.connect(lambda lv, msg: self._append(self._app_log, lv, msg))
        self._sig_export.connect(lambda lv, msg: self._append(self._export_log, lv, msg))
        # Callbacks may be called from any thread → emit signal instead of direct call
        set_app_log_callback(lambda lv, msg: self._sig_app.emit(lv, msg))
        set_export_log_callback(lambda lv, msg: self._sig_export.emit(lv, msg))
        # Load messages that were logged before the window was opened
        for lv, msg in get_app_log_buffer():
            self._append(self._app_log, lv, msg)
        for lv, msg in get_export_log_buffer():
            self._append(self._export_log, lv, msg)

    def _append(self, edit: QTextEdit, level: str, msg: str):
        color = _LEVEL_COLORS.get(level, "#c8c8e0")
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(color))
        cursor = edit.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertText(msg + "\n", fmt)
        edit.setTextCursor(cursor)
        edit.ensureCursorVisible()

    # ── Actions ───────────────────────────────────────────────────────────────

    def _clear_current_tab(self):
        idx = self._tabs.currentIndex()
        if idx == 0:
            self._app_log.clear()
        else:
            self._export_log.clear()

    def _open_log_dir(self):
        import subprocess
        os.makedirs(LOGS_DIR, exist_ok=True)
        subprocess.Popen(["explorer", LOGS_DIR])

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
        apply_acrylic(hwnd, dark=(self._theme == "dark"))

    def apply_stylesheet(self, qss: str):
        self._card.setStyleSheet("")
        self.setStyleSheet(qss)
