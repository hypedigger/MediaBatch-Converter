DARK_THEME = """
/* ═══════════════════════════════════════════════
   MediaBatch Converter — Dark Theme
   ═══════════════════════════════════════════════ */

QWidget {
    font-family: "Segoe UI Variable", "Segoe UI", sans-serif;
    font-size: 13px;
    color: #E8E8F0;
}

/* ── Main window (transparent for Acrylic) ─────── */
QMainWindow, #root_widget {
    background: transparent;
}

#central_widget {
    background: rgba(12, 12, 22, 210);
    border-radius: 12px;
    border: 1px solid rgba(255, 255, 255, 12);
}

/* ── Title bar ──────────────────────────────────── */
#title_bar {
    background: rgba(10, 10, 20, 160);
    border-radius: 12px 12px 0 0;
    border-bottom: 1px solid rgba(255, 255, 255, 10);
}

#title_label {
    color: rgba(255, 255, 255, 220);
    font-size: 13px;
    font-weight: 600;
    letter-spacing: 0.4px;
}

#btn_minimize, #btn_maximize, #btn_close {
    background: transparent;
    border: none;
    color: rgba(255, 255, 255, 160);
    font-size: 16px;
    padding: 0;
    min-width: 46px;
    min-height: 32px;
    max-width: 46px;
    max-height: 32px;
    border-radius: 0;
}
#btn_minimize:hover { background: rgba(255, 255, 255, 12); }
#btn_maximize:hover { background: rgba(255, 255, 255, 12); }
#btn_close:hover    { background: rgba(196, 43, 28, 220);  color: white; }

/* ── Panels / Cards ─────────────────────────────── */
#panel_top, #panel_list, #panel_bottom, #panel_player {
    background: rgba(255, 255, 255, 6);
    border: 1px solid rgba(255, 255, 255, 10);
    border-radius: 10px;
}
#panel_player {
    background: rgba(110, 88, 220, 22);
    border: 1px solid rgba(160, 110, 255, 50);
}

/* ── Sliders (pré-écoute) ───────────────────────── */
QSlider::groove:horizontal {
    background: rgba(255, 255, 255, 14);
    height: 5px;
    border-radius: 2px;
}
QSlider::sub-page:horizontal {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 rgba(110, 88, 220, 255),
        stop:1 rgba(190, 140, 255, 255));
    border-radius: 2px;
}
QSlider::handle:horizontal {
    background: white;
    width: 13px;
    height: 13px;
    margin: -4px 0;
    border-radius: 6px;
}
QSlider::handle:horizontal:hover {
    background: rgba(210, 180, 255, 255);
}

/* ── Separator ──────────────────────────────────── */
QFrame[frameShape="4"], QFrame[frameShape="5"] {
    color: rgba(255, 255, 255, 12);
}

/* ── Primary button ─────────────────────────────── */
QPushButton#btn_primary {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 rgba(110, 90, 220, 220),
        stop:1 rgba(160, 110, 255, 220));
    color: white;
    border: none;
    border-radius: 8px;
    padding: 9px 22px;
    font-weight: 600;
    font-size: 13px;
}
QPushButton#btn_primary:hover {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 rgba(130, 110, 240, 255),
        stop:1 rgba(180, 130, 255, 255));
}
QPushButton#btn_primary:pressed {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 rgba(90, 70, 200, 255),
        stop:1 rgba(130, 90, 220, 255));
}
QPushButton#btn_primary:disabled {
    background: rgba(255, 255, 255, 15);
    color: rgba(255, 255, 255, 50);
}

/* ── Secondary / ghost button ───────────────────── */
QPushButton, QPushButton#btn_secondary {
    background: rgba(255, 255, 255, 10);
    color: rgba(255, 255, 255, 180);
    border: 1px solid rgba(255, 255, 255, 14);
    border-radius: 8px;
    padding: 7px 16px;
    font-size: 13px;
}
QPushButton:hover, QPushButton#btn_secondary:hover {
    background: rgba(255, 255, 255, 18);
    color: white;
    border-color: rgba(255, 255, 255, 22);
}
QPushButton:pressed, QPushButton#btn_secondary:pressed {
    background: rgba(255, 255, 255, 8);
}
QPushButton:disabled {
    background: rgba(255, 255, 255, 5);
    color: rgba(255, 255, 255, 35);
    border-color: rgba(255, 255, 255, 6);
}

/* ── Icon-only small buttons ────────────────────── */
QPushButton#btn_icon {
    background: transparent;
    border: none;
    border-radius: 6px;
    padding: 5px 8px;
    color: rgba(255, 255, 255, 150);
    font-size: 16px;
}
QPushButton#btn_icon:hover {
    background: rgba(255, 255, 255, 12);
    color: white;
}

/* ── Line edit ──────────────────────────────────── */
QLineEdit {
    background: rgba(255, 255, 255, 8);
    border: 1px solid rgba(255, 255, 255, 14);
    border-radius: 8px;
    padding: 8px 12px;
    color: rgba(255, 255, 255, 220);
    selection-background-color: rgba(120, 90, 230, 140);
}
QLineEdit:focus {
    border: 1px solid rgba(130, 100, 240, 180);
    background: rgba(255, 255, 255, 11);
}
QLineEdit:read-only {
    color: rgba(255, 255, 255, 140);
}

/* ── ComboBox ───────────────────────────────────── */
QComboBox {
    background: rgba(255, 255, 255, 10);
    color: rgba(255, 255, 255, 210);
    border: 1px solid rgba(255, 255, 255, 16);
    border-radius: 8px;
    padding: 7px 12px;
    min-height: 20px;
}
QComboBox:hover {
    background: rgba(255, 255, 255, 15);
    border-color: rgba(255, 255, 255, 24);
}
QComboBox::drop-down {
    border: none;
    width: 26px;
}
QComboBox::down-arrow {
    image: none;
    width: 0;
    height: 0;
    border-left:   5px solid transparent;
    border-right:  5px solid transparent;
    border-top:    6px solid rgba(255, 255, 255, 150);
}
QComboBox QAbstractItemView {
    background: rgba(20, 18, 35, 252);
    border: 1px solid rgba(255, 255, 255, 16);
    border-radius: 8px;
    color: rgba(255, 255, 255, 210);
    selection-background-color: rgba(110, 88, 220, 160);
    outline: none;
    padding: 4px;
}
QComboBox QAbstractItemView::item {
    padding: 8px 12px;
    border-radius: 6px;
    min-height: 28px;
}

/* ── CheckBox ───────────────────────────────────── */
QCheckBox {
    color: rgba(255, 255, 255, 190);
    spacing: 9px;
}
QCheckBox::indicator {
    width: 18px;
    height: 18px;
    border-radius: 5px;
    border: 2px solid rgba(255, 255, 255, 28);
    background: rgba(255, 255, 255, 5);
}
QCheckBox::indicator:hover {
    border-color: rgba(130, 100, 240, 180);
}
QCheckBox::indicator:checked {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 rgba(120, 90, 230, 255),
        stop:1 rgba(160, 110, 255, 255));
    border-color: transparent;
}
QCheckBox::indicator:indeterminate {
    background: rgba(120, 90, 230, 140);
    border-color: transparent;
}

/* ── Table ──────────────────────────────────────── */
QTableWidget {
    background: transparent;
    border: none;
    gridline-color: rgba(255, 255, 255, 6);
    outline: none;
    selection-background-color: transparent;
}
QTableWidget::item {
    padding: 0px 8px;
    border-bottom: 1px solid rgba(255, 255, 255, 5);
    color: rgba(255, 255, 255, 200);
}
QTableWidget::item:selected {
    background: rgba(110, 88, 220, 55);
    color: white;
}
/* survol : ligne entière, dessiné par ui/table_style.py */
QHeaderView {
    background: transparent;
}
QHeaderView::section {
    background: rgba(255, 255, 255, 8);
    color: rgba(200, 200, 220, 160);
    border: none;
    border-right: 1px solid rgba(255, 255, 255, 8);
    padding: 8px 10px;
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 0.8px;
    text-transform: uppercase;
}
QHeaderView::section:hover {
    background: rgba(255, 255, 255, 14);
    color: white;
}
QHeaderView::section:first {
    border-radius: 8px 0 0 0;
}
QHeaderView::section:last {
    border-right: none;
    border-radius: 0 8px 0 0;
}

/* ── Scrollbars ─────────────────────────────────── */
QScrollBar:vertical {
    background: transparent;
    width: 8px;
    margin: 0;
}
QScrollBar::handle:vertical {
    background: rgba(255, 255, 255, 22);
    border-radius: 4px;
    min-height: 30px;
}
QScrollBar::handle:vertical:hover {
    background: rgba(255, 255, 255, 40);
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }

QScrollBar:horizontal {
    background: transparent;
    height: 8px;
    margin: 0;
}
QScrollBar::handle:horizontal {
    background: rgba(255, 255, 255, 22);
    border-radius: 4px;
    min-width: 30px;
}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }

/* ── Progress bar ───────────────────────────────── */
QProgressBar {
    background: rgba(255, 255, 255, 10);
    border: none;
    border-radius: 5px;
    max-height: 8px;
    text-align: center;
    color: transparent;
}
QProgressBar::chunk {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 rgba(110, 88, 220, 255),
        stop:1 rgba(190, 140, 255, 255));
    border-radius: 5px;
}

/* ── Label ──────────────────────────────────────── */
QLabel#label_section {
    color: rgba(200, 200, 220, 130);
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 1px;
    text-transform: uppercase;
}
QLabel#label_desc {
    color: rgba(200, 200, 220, 120);
    font-size: 11px;
    font-style: italic;
}
QLabel#label_count {
    color: rgba(160, 130, 255, 200);
    font-size: 12px;
    font-weight: 600;
}

/* ── Status bar ─────────────────────────────────── */
#status_bar {
    background: rgba(10, 10, 20, 140);
    border-radius: 0 0 12px 12px;
    border-top: 1px solid rgba(255, 255, 255, 8);
}
#status_label {
    color: rgba(255, 255, 255, 100);
    font-size: 11px;
}

/* ── Dialog ─────────────────────────────────────── */
QDialog {
    background: rgba(18, 16, 30, 250);
    border: 1px solid rgba(255, 255, 255, 14);
    border-radius: 12px;
}

/* ── Text edit (log) ────────────────────────────── */
QTextEdit {
    background: rgba(8, 8, 16, 200);
    border: none;
    border-radius: 8px;
    color: rgba(200, 220, 200, 200);
    font-family: "Cascadia Code", "Consolas", monospace;
    font-size: 11px;
    selection-background-color: rgba(110, 88, 220, 120);
}

/* ── Tab widget ─────────────────────────────────── */
QTabWidget::pane {
    background: transparent;
    border: 1px solid rgba(255, 255, 255, 10);
    border-radius: 8px;
}
QTabBar::tab {
    background: rgba(255, 255, 255, 8);
    color: rgba(255, 255, 255, 140);
    border: none;
    padding: 8px 20px;
    border-radius: 6px 6px 0 0;
}
QTabBar::tab:selected {
    background: rgba(110, 88, 220, 140);
    color: white;
}
QTabBar::tab:hover {
    background: rgba(255, 255, 255, 14);
    color: white;
}
"""

LIGHT_THEME = """
QWidget {
    font-family: "Segoe UI Variable", "Segoe UI", sans-serif;
    font-size: 13px;
    color: #1A1A2E;
}

QMainWindow, #root_widget {
    background: transparent;
}

#central_widget {
    background: rgba(242, 240, 255, 215);
    border-radius: 12px;
    border: 1px solid rgba(0, 0, 0, 12);
}

#title_bar {
    background: rgba(230, 226, 252, 190);
    border-radius: 12px 12px 0 0;
    border-bottom: 1px solid rgba(0, 0, 0, 8);
}

#title_label {
    color: rgba(30, 20, 60, 220);
    font-size: 13px;
    font-weight: 600;
}

#btn_minimize, #btn_maximize, #btn_close {
    background: transparent;
    border: none;
    color: rgba(30, 20, 60, 160);
    font-size: 16px;
    padding: 0;
    min-width: 46px; min-height: 32px;
    max-width: 46px; max-height: 32px;
    border-radius: 0;
}
#btn_minimize:hover { background: rgba(0, 0, 0, 8); }
#btn_maximize:hover { background: rgba(0, 0, 0, 8); }
#btn_close:hover    { background: rgba(196, 43, 28, 200); color: white; }

#panel_top, #panel_list, #panel_bottom, #panel_player {
    background: rgba(255, 255, 255, 120);
    border: 1px solid rgba(0, 0, 0, 8);
    border-radius: 10px;
}
#panel_player {
    background: rgba(110, 88, 220, 28);
    border: 1px solid rgba(110, 88, 220, 70);
}

QSlider::groove:horizontal {
    background: rgba(0, 0, 0, 16);
    height: 5px;
    border-radius: 2px;
}
QSlider::sub-page:horizontal {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 rgba(100, 80, 210, 255),
        stop:1 rgba(170, 120, 255, 255));
    border-radius: 2px;
}
QSlider::handle:horizontal {
    background: rgba(90, 60, 200, 255);
    width: 13px;
    height: 13px;
    margin: -4px 0;
    border-radius: 6px;
}

QPushButton#btn_primary {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 rgba(100, 80, 210, 220),
        stop:1 rgba(150, 100, 240, 220));
    color: white;
    border: none;
    border-radius: 8px;
    padding: 9px 22px;
    font-weight: 600;
}
QPushButton#btn_primary:hover {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 rgba(120, 100, 230, 255),
        stop:1 rgba(170, 120, 255, 255));
}
QPushButton#btn_primary:disabled {
    background: rgba(0, 0, 0, 15);
    color: rgba(0, 0, 0, 40);
}

QPushButton, QPushButton#btn_secondary {
    background: rgba(0, 0, 0, 8);
    color: rgba(30, 20, 60, 200);
    border: 1px solid rgba(0, 0, 0, 12);
    border-radius: 8px;
    padding: 7px 16px;
}
QPushButton:hover {
    background: rgba(0, 0, 0, 14);
    color: rgba(30, 20, 60, 255);
}

QLineEdit {
    background: rgba(255, 255, 255, 160);
    border: 1px solid rgba(0, 0, 0, 14);
    border-radius: 8px;
    padding: 8px 12px;
    color: #1A1A2E;
}
QLineEdit:focus {
    border: 1px solid rgba(100, 80, 210, 180);
}

QComboBox {
    background: rgba(255, 255, 255, 160);
    color: #1A1A2E;
    border: 1px solid rgba(0, 0, 0, 14);
    border-radius: 8px;
    padding: 7px 12px;
}
QComboBox QAbstractItemView {
    background: rgba(245, 243, 255, 252);
    border: 1px solid rgba(0, 0, 0, 14);
    color: #1A1A2E;
    selection-background-color: rgba(110, 88, 220, 100);
}

QCheckBox { color: rgba(30, 20, 60, 200); spacing: 9px; }
QCheckBox::indicator {
    width: 18px; height: 18px;
    border-radius: 5px;
    border: 2px solid rgba(60, 40, 120, 160);
    background: rgba(255, 255, 255, 220);
}
QCheckBox::indicator:hover {
    border-color: rgba(100, 80, 210, 200);
}
QCheckBox::indicator:checked {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 rgba(110, 88, 220, 255),
        stop:1 rgba(150, 110, 255, 255));
    border-color: transparent;
}

QTableWidget {
    background: transparent; border: none;
    gridline-color: rgba(0, 0, 0, 6); outline: none;
}
QTableWidget::item { padding: 0 8px; border-bottom: 1px solid rgba(0,0,0,5); color: #1A1A2E; }
QTableWidget::item:selected { background: rgba(110, 88, 220, 40); }
QAbstractItemView::indicator {
    width: 16px; height: 16px;
    border-radius: 4px;
    border: 2px solid rgba(60, 40, 120, 160);
    background: rgba(255, 255, 255, 220);
}
QAbstractItemView::indicator:checked {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 rgba(110, 88, 220, 255),
        stop:1 rgba(150, 110, 255, 255));
    border-color: transparent;
}
QHeaderView::section {
    background: rgba(0, 0, 0, 6);
    color: rgba(30, 20, 60, 130);
    border: none;
    border-right: 1px solid rgba(0,0,0,6);
    padding: 8px 10px;
    font-size: 11px; font-weight: 600; letter-spacing: 0.8px;
}

QScrollBar:vertical { background: transparent; width: 8px; }
QScrollBar::handle:vertical { background: rgba(0,0,0,18); border-radius: 4px; min-height: 30px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }

QProgressBar {
    background: rgba(0,0,0,10); border: none; border-radius: 5px;
    max-height: 8px; color: transparent;
}
QProgressBar::chunk {
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
        stop:0 rgba(100,80,210,255), stop:1 rgba(170,120,255,255));
    border-radius: 5px;
}

QLabel#label_section { color: rgba(30,20,60,120); font-size:11px; font-weight:600; letter-spacing:1px; }
QLabel#label_desc    { color: rgba(30,20,60,100); font-size:11px; font-style:italic; }
QLabel#label_count   { color: rgba(90,60,200,200); font-size:12px; font-weight:600; }

#status_bar {
    background: rgba(220,216,245,180);
    border-radius: 0 0 12px 12px;
    border-top: 1px solid rgba(0,0,0,8);
}
#status_label { color: rgba(30,20,60,120); font-size:11px; }

QDialog {
    background: rgba(240,238,255,252);
    border: 1px solid rgba(0,0,0,14);
    border-radius: 12px;
}

QTextEdit {
    background: rgba(240,238,255,200);
    border: none; border-radius: 8px;
    color: rgba(30,20,60,200);
    font-family: "Cascadia Code","Consolas",monospace; font-size:11px;
}

QTabBar::tab { background: rgba(0,0,0,8); color: rgba(30,20,60,140); border:none; padding:8px 20px; border-radius:6px 6px 0 0; }
QTabBar::tab:selected { background: rgba(100,80,210,140); color: white; }
"""


# Bascule Audio / Images de la barre de titre
_MODE_DARK = """
QPushButton#btn_mode {
    background: rgba(255, 255, 255, 5);
    border: 1px solid rgba(255, 255, 255, 14);
    border-radius: 6px;
    padding: 3px 14px;
    color: rgba(255, 255, 255, 140);
    font-size: 12px;
}
QPushButton#btn_mode:hover { background: rgba(255, 255, 255, 12); color: white; }
QPushButton#btn_mode:checked {
    background: rgba(110, 88, 220, 170);
    border-color: rgba(170, 130, 255, 140);
    color: white;
}

/* Bouton « Estimer le gain d'espace » et action du toast : se démarque du violet */
QPushButton#btn_accent {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 rgba(20, 160, 130, 230), stop:1 rgba(40, 190, 210, 230));
    border: 1px solid rgba(120, 240, 220, 90);
    border-radius: 8px;
    padding: 7px 16px;
    color: white;
    font-weight: 600;
}
QPushButton#btn_accent:hover {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 rgba(30, 185, 150, 255), stop:1 rgba(60, 210, 230, 255));
}
QPushButton#btn_accent:pressed { background: rgba(20, 140, 120, 255); }

/* Petits boutons Tous / Aucun collés aux cases de formats */
QPushButton#btn_chip {
    background: rgba(255, 255, 255, 6);
    border: 1px solid rgba(255, 255, 255, 14);
    border-radius: 6px;
    padding: 2px 10px;
    color: rgba(255, 255, 255, 150);
    font-size: 12px;
}
QPushButton#btn_chip:hover { background: rgba(255, 255, 255, 14); color: white; }

#toast {
    background: rgba(26, 30, 44, 245);
    border: 1px solid rgba(80, 210, 190, 110);
    border-radius: 12px;
}
#toast_label { color: rgba(235, 240, 255, 220); font-size: 13px; }
QProgressBar#toast_bar { background: transparent; border: none; border-radius: 1px; }
QProgressBar#toast_bar::chunk { background: rgba(80, 210, 190, 160); border-radius: 1px; }
"""

_MODE_LIGHT = """
QPushButton#btn_mode {
    background: rgba(0, 0, 0, 4);
    border: 1px solid rgba(0, 0, 0, 14);
    border-radius: 6px;
    padding: 3px 14px;
    color: rgba(30, 20, 60, 150);
    font-size: 12px;
}
QPushButton#btn_mode:hover { background: rgba(0, 0, 0, 10); }
QPushButton#btn_mode:checked {
    background: rgba(100, 80, 210, 160);
    border-color: rgba(100, 80, 210, 200);
    color: white;
}

QPushButton#btn_accent {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 rgba(16, 150, 120, 255), stop:1 rgba(30, 170, 200, 255));
    border: none;
    border-radius: 8px;
    padding: 7px 16px;
    color: white;
    font-weight: 600;
}
QPushButton#btn_accent:hover { background: rgba(16, 165, 135, 255); }

QPushButton#btn_chip {
    background: rgba(0, 0, 0, 4);
    border: 1px solid rgba(0, 0, 0, 14);
    border-radius: 6px;
    padding: 2px 10px;
    color: rgba(30, 20, 60, 160);
    font-size: 12px;
}
QPushButton#btn_chip:hover { background: rgba(0, 0, 0, 10); }

#toast {
    background: rgba(255, 255, 255, 250);
    border: 1px solid rgba(16, 150, 120, 120);
    border-radius: 12px;
}
#toast_label { color: #1A1A2E; font-size: 13px; }
QProgressBar#toast_bar { background: transparent; border: none; }
QProgressBar#toast_bar::chunk { background: rgba(16, 150, 120, 160); }
"""


def get_theme(name: str) -> str:
    return LIGHT_THEME + _MODE_LIGHT if name == "light" else DARK_THEME + _MODE_DARK
