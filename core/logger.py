import logging
import os
from collections import deque

from core.config import LOGS_DIR, APP_VERSION

_app_logger    = None
_export_logger = None
_qt_handler_app    = None
_qt_handler_export = None

# In-memory ring buffers — populated even before the log window is opened
_buffer_app    = deque(maxlen=2000)
_buffer_export = deque(maxlen=2000)


class _QtSignalHandler(logging.Handler):
    """
    Logging handler that:
    - appends every record to an in-memory buffer
    - forwards the record to an optional Qt callback (set at runtime)
    """

    def __init__(self, buffer: deque):
        super().__init__()
        self._buffer   = buffer
        self._callback = None  # callable(level: str, msg: str)

    def set_callback(self, cb):
        self._callback = cb

    def emit(self, record):
        try:
            msg = self.format(record)
            self._buffer.append((record.levelname, msg))
            if self._callback:
                self._callback(record.levelname, msg)
        except Exception:
            pass


def setup_loggers():
    global _app_logger, _export_logger, _qt_handler_app, _qt_handler_export

    os.makedirs(LOGS_DIR, exist_ok=True)

    app_log_file    = os.path.join(LOGS_DIR, f"v{APP_VERSION}_log_app.log")
    export_log_file = os.path.join(LOGS_DIR, f"v{APP_VERSION}_log_export.log")

    fmt_app    = logging.Formatter("[%(asctime)s] %(levelname)s — %(message)s",
                                   datefmt="%Y-%m-%d %H:%M:%S")
    fmt_export = logging.Formatter("[%(asctime)s] %(message)s",
                                   datefmt="%Y-%m-%d %H:%M:%S")

    # ── App logger ──────────────────────────────────────────────────────────
    _app_logger = logging.getLogger("mc.app")
    _app_logger.setLevel(logging.DEBUG)
    _app_logger.propagate = False
    _app_logger.handlers.clear()

    fh = logging.FileHandler(app_log_file, encoding="utf-8")
    fh.setFormatter(fmt_app)
    _app_logger.addHandler(fh)

    _qt_handler_app = _QtSignalHandler(_buffer_app)
    _qt_handler_app.setFormatter(fmt_app)
    _app_logger.addHandler(_qt_handler_app)

    # ── Export logger ────────────────────────────────────────────────────────
    _export_logger = logging.getLogger("mc.export")
    _export_logger.setLevel(logging.DEBUG)
    _export_logger.propagate = False
    _export_logger.handlers.clear()

    fh2 = logging.FileHandler(export_log_file, encoding="utf-8")
    fh2.setFormatter(fmt_export)
    _export_logger.addHandler(fh2)

    _qt_handler_export = _QtSignalHandler(_buffer_export)
    _qt_handler_export.setFormatter(fmt_export)
    _export_logger.addHandler(_qt_handler_export)

    _app_logger.info("MediaBatch Converter démarré — v%s", APP_VERSION)


def get_app_logger() -> logging.Logger:
    return _app_logger or logging.getLogger("mc.app")


def get_export_logger() -> logging.Logger:
    return _export_logger or logging.getLogger("mc.export")


def set_app_log_callback(cb):
    if _qt_handler_app:
        _qt_handler_app.set_callback(cb)


def set_export_log_callback(cb):
    if _qt_handler_export:
        _qt_handler_export.set_callback(cb)


def get_app_log_buffer() -> list:
    """Return a snapshot of buffered app log records as (level, msg) tuples."""
    return list(_buffer_app)


def get_export_log_buffer() -> list:
    """Return a snapshot of buffered export log records as (level, msg) tuples."""
    return list(_buffer_export)
