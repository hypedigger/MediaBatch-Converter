import os
import re
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Any

from PyQt6.QtCore import QThread, pyqtSignal

from core.scanner import FileInfo
from core.logger import get_app_logger, get_export_logger


_INVALID_NAME_CHARS = '<>:"/\\|?*'


def clean_name(text: str, fallback: str) -> str:
    """Nom de fichier/dossier sûr (caractères interdits retirés), *fallback* si vide."""
    text = "".join(c for c in (text or "") if c not in _INVALID_NAME_CHARS).strip().rstrip(".")
    return text or fallback


def _suffix_candidates(suffix: str):
    """_v2 → _v2, _v3, _v4…   ·   -small → -small, -small2, -small3…"""
    m = re.match(r"^(.*?)(\d+)$", suffix)
    if m:
        head, n = m.group(1), int(m.group(2))
        while True:
            yield f"{head}{n}"
            n += 1
    yield suffix
    n = 2
    while True:
        yield f"{suffix}{n}"
        n += 1


def get_output_path(src: str, out_ext: str, conflict: str = "rename",
                    suffix: str = "_v1", subdir: str = "") -> str:
    """
    Chemin de sortie.  conflict = "overwrite" | "rename"
    *subdir* : sous-dossier (dans le dossier de l'original) où écrire la sortie.
    En mode "rename", si la cible existe déjà, ajoute *suffix* (_v2, puis _v3…).
    """
    folder, name = os.path.split(src)
    if subdir:
        folder = os.path.join(folder, subdir)
    base = os.path.join(folder, os.path.splitext(name)[0])
    dst  = f"{base}.{out_ext}"

    if conflict == "overwrite" or not os.path.exists(dst):
        return dst

    for sfx in _suffix_candidates(suffix or "_v1"):
        cand = f"{base}{sfx}.{out_ext}"
        if not os.path.exists(cand):
            return cand


def detect_conflicts(files: List[FileInfo], out_fmt: Dict[str, Any],
                     subdir: str = "") -> List[FileInfo]:
    """Return files whose direct output path (same name, new ext) already exists."""
    conflicts = []
    for f in files:
        if os.path.exists(get_output_path(f.path, out_fmt["ext"], "overwrite", subdir=subdir)):
            conflicts.append(f)
    return conflicts


class ConversionThread(QThread):
    """Runs all conversions in a background thread using a thread-pool."""

    progress_updated = pyqtSignal(int, int)             # completed, total
    file_completed   = pyqtSignal(str, str, bool, str)  # src_path, out_path, success, message
    file_started     = pyqtSignal(str)                  # src_path (émis depuis un worker)
    all_done         = pyqtSignal()

    def __init__(
        self,
        files:          List[FileInfo],
        ffmpeg_path:    str,
        out_fmt:        Dict[str, Any],
        parallel:       int,
        conflict:       str,  # "overwrite" | "rename"
    ):
        super().__init__()
        self._files         = files
        self._ffmpeg_path   = ffmpeg_path
        self._out_fmt       = out_fmt
        self._parallel      = parallel if parallel > 0 else self._auto_parallel()
        self._conflict      = conflict
        self._cancelled     = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        total      = len(self._files)
        completed  = 0
        log_app    = get_app_logger()
        log_export = get_export_logger()

        log_app.info(
            "Démarrage conversion : %d fichier(s) → %s | %d threads",
            total, self._out_fmt["label"], self._parallel,
        )

        with ThreadPoolExecutor(max_workers=self._parallel) as pool:
            futures = {
                pool.submit(self._run_one, f): f
                for f in self._files
            }
            for future in as_completed(futures):
                if self._cancelled:
                    pool.shutdown(wait=False, cancel_futures=True)
                    break

                fi = futures[future]
                completed += 1

                try:
                    # _convert_one → chemin de sortie, ou (chemin, message)
                    res = future.result()
                    out_path, msg = res if isinstance(res, tuple) else (res, "")
                    success  = True
                    log_export.info("OK  %s  →  %s  %s", fi.path, out_path, msg)
                except Exception as exc:
                    out_path = ""
                    success  = False
                    msg      = str(exc)
                    log_export.error("ERREUR  %s  —  %s", fi.path, msg)
                    log_app.warning("Conversion échouée : %s — %s", fi.name, msg)

                self.progress_updated.emit(completed, total)
                self.file_completed.emit(fi.path, out_path, success, msg)

        self.all_done.emit()
        log_app.info("Conversion terminée.")

    # ── Private ──────────────────────────────────────────────────────────────

    def _run_one(self, fi: FileInfo):
        if not self._cancelled:
            self.file_started.emit(fi.path)     # → interface (connexion en file d'attente)
        return self._convert_one(fi)

    def _build_cmd(self, src: str, dst: str, with_cover: bool) -> List[str]:
        cmd = [self._ffmpeg_path, "-y", "-i", src, "-map_metadata", "0"]
        if self._out_fmt["ext"] == "mp3":
            # ID3v2.3 : version la mieux reconnue (Windows, autoradios…)
            cmd += ["-id3v2_version", "3"]
        if with_cover:
            # 0:v? = pochette embarquée si présente, recopiée sans ré-encodage
            cmd += ["-map", "0:a", "-map", "0:v?",
                    "-c:v", "copy", "-disposition:v", "attached_pic"]
        else:
            cmd += ["-map", "0:a", "-vn"]
        return cmd + self._out_fmt["ffmpeg_args"] + [dst]

    def _convert_one(self, fi: FileInfo) -> str:
        """Convert one file. Returns the output path. Raises on failure."""
        if self._cancelled:
            raise RuntimeError("Annulé")

        dst = get_output_path(fi.path, self._out_fmt["ext"], self._conflict)

        no_window = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        with_cover = bool(self._out_fmt.get("cover", False))

        result = subprocess.run(
            self._build_cmd(fi.path, dst, with_cover),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=no_window,
        )

        if result.returncode != 0 and with_cover:
            # Pochette absente/incompatible avec le conteneur cible :
            # nouvelle tentative sans le flux image
            result = subprocess.run(
                self._build_cmd(fi.path, dst, False),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                creationflags=no_window,
            )

        if result.returncode != 0:
            stderr = result.stderr.decode("utf-8", errors="replace")
            raise RuntimeError(f"FFmpeg exit {result.returncode}: {stderr[-300:]}")

        # Les originaux éventuellement à supprimer partent à la Corbeille en
        # fin de conversion, depuis l'interface (core/recycle.py)
        return dst

    @staticmethod
    def _auto_parallel() -> int:
        cpu = os.cpu_count() or 4
        return min(max(cpu // 2, 4), 16)
