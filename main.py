"""
MediaBatch Converter — v14 — 04/11/2026
"""

import sys
import os

# ── Project root must be in sys.path BEFORE any local import ─────────────────
ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


# ── Error display (always works, even without PyQt6) ─────────────────────────

def _show_error(title: str, msg: str):
    """Show an error dialog using tkinter (always available in Python stdlib)."""
    # Also write to a file so the user can always read it
    err_file = os.path.join(ROOT, "startup_error.txt")
    try:
        with open(err_file, "w", encoding="utf-8") as f:
            f.write(f"{title}\n\n{msg}\n")
    except Exception:
        pass

    try:
        import tkinter as tk
        from tkinter import messagebox
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(title, msg)
        root.destroy()
    except Exception:
        # Absolute last resort: keep the console open
        print(f"\n{'='*60}\nERREUR : {title}\n{msg}\n{'='*60}")
        input("\nAppuie sur Entrée pour fermer…")


# ── Dependency installer ──────────────────────────────────────────────────────

def _ensure_deps() -> bool:
    """
    Install missing dependencies (PyQt6, mutagen, Pillow).
    Returns True if something was just installed (restart needed),
    False if everything was already present.
    """
    missing = []
    try:
        import PyQt6  # noqa
    except ImportError:
        missing.append("PyQt6")
    try:
        import mutagen  # noqa
    except ImportError:
        missing.append("mutagen")
    try:
        import PIL  # noqa
    except ImportError:
        missing.append("Pillow")

    if not missing:
        return False

    import subprocess

    # Show a tkinter progress window while installing
    _installed = [False]
    _error     = [None]

    try:
        import tkinter as tk
        from tkinter import ttk

        root = tk.Tk()
        root.title("MediaBatch Converter — Installation")
        root.geometry("420x140")
        root.resizable(False, False)
        root.configure(bg="#0e0e1a")
        root.attributes("-topmost", True)

        tk.Label(
            root,
            text=f"Installation de {', '.join(missing)} en cours…",
            bg="#0e0e1a", fg="#c8c8f0",
            font=("Segoe UI", 11),
        ).pack(pady=(22, 8))

        bar = ttk.Progressbar(root, mode="indeterminate", length=360)
        bar.pack(pady=4)
        bar.start(10)

        lbl2 = tk.Label(root, text="(première exécution uniquement)",
                        bg="#0e0e1a", fg="#666688", font=("Segoe UI", 9))
        lbl2.pack()
        root.update()

        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", *missing, "--quiet"],
            capture_output=True,
        )
        if result.returncode != 0:
            _error[0] = result.stderr.decode("utf-8", errors="replace")
        else:
            _installed[0] = True

        root.destroy()

    except Exception as e:
        # No tkinter — silent install
        try:
            result = subprocess.run(
                [sys.executable, "-m", "pip", "install", *missing],
                capture_output=True,
            )
            if result.returncode == 0:
                _installed[0] = True
            else:
                _error[0] = result.stderr.decode("utf-8", errors="replace")
        except Exception as e2:
            _error[0] = str(e2)

    if _error[0]:
        _show_error(
            "Erreur d'installation",
            f"Impossible d'installer {', '.join(missing)} :\n\n{_error[0]}\n\n"
            f"Essaie manuellement : pip install {' '.join(missing)}",
        )
        sys.exit(1)

    return _installed[0]


# ═════════════════════════════════════════════════════════════════════════════

def main():
    just_installed = _ensure_deps()

    if just_installed:
        # Restart the process so the freshly-installed package is importable
        import subprocess
        subprocess.Popen([sys.executable, os.path.abspath(__file__)])
        sys.exit(0)

    # ── From here PyQt6 is guaranteed ────────────────────────────────────────
    try:
        from PyQt6.QtWidgets import QApplication
        from PyQt6.QtGui     import QFont
    except Exception as e:
        _show_error("Erreur PyQt6",
                    f"PyQt6 est installé mais ne peut pas être importé :\n\n{e}\n\n"
                    "Essaie : pip install --force-reinstall PyQt6")
        sys.exit(1)

    try:
        from core.logger import setup_loggers
    except Exception as e:
        _show_error("Erreur au démarrage", f"Impossible de charger core.logger :\n\n{e}")
        sys.exit(1)

    app = QApplication(sys.argv)
    app.setApplicationName("MediaBatch Converter")
    app.setFont(QFont("Segoe UI Variable", 10))

    try:
        setup_loggers()
    except Exception as e:
        _show_error("Erreur logs", f"Impossible d'initialiser les logs :\n\n{e}")
        # Non-fatal — continue

    # ── App icon ──────────────────────────────────────────────────────────────
    try:
        from ui.icon import create_app_icon
        app.setWindowIcon(create_app_icon())
    except Exception:
        pass  # non-fatal

    # ── FFmpeg check ──────────────────────────────────────────────────────────
    try:
        from core.ffmpeg_manager import FFmpegManager
        ffmpeg_mgr = FFmpegManager()
    except Exception as e:
        _show_error("Erreur FFmpeg Manager", str(e))
        sys.exit(1)

    if not ffmpeg_mgr.is_available():
        try:
            from ui.ffmpeg_downloader_window import FFmpegDownloaderWindow
            downloader = FFmpegDownloaderWindow(ffmpeg_mgr)
            # Refus du téléchargement : l'app s'ouvre quand même (le mode
            # Images n'utilise pas FFmpeg ; l'audio signalera son absence)
            downloader.exec()
        except Exception as e:
            _show_error("Erreur fenêtre FFmpeg", str(e))
            sys.exit(1)

    # ── Main window ───────────────────────────────────────────────────────────
    try:
        from ui.main_window import MainWindow
        window = MainWindow()
        window.show()
    except Exception as e:
        import traceback
        _show_error("Erreur fenêtre principale",
                    f"{e}\n\n{traceback.format_exc()}")
        sys.exit(1)

    sys.exit(app.exec())


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as e:
        import traceback
        _show_error("Erreur inattendue", f"{e}\n\n{traceback.format_exc()}")
        sys.exit(1)
