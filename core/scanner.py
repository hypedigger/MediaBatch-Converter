import os
import time
from dataclasses import dataclass
from typing import Callable, List, Optional

from PyQt6.QtCore import QThread, pyqtSignal

# Directories to skip entirely during recursive scan
_EXCLUDED_DIRS = {".stversions"}


@dataclass
class FileInfo:
    path:         str
    name:         str
    directory:    str
    size:         int          # bytes
    date_created: float        # Unix timestamp
    extension:    str          # lowercase, no dot

    def size_str(self) -> str:
        mb = self.size / (1024 * 1024)
        if mb >= 1:
            return f"{mb:.1f} Mo"
        kb = self.size / 1024
        return f"{kb:.0f} Ko"


def file_info_from_path(path: str) -> Optional[FileInfo]:
    """Build a FileInfo for a single file, or None if it can't be stat'ed."""
    try:
        stat = os.stat(path)
    except OSError:
        return None
    filename = os.path.basename(path)
    return FileInfo(
        path         = path,
        name         = os.path.splitext(filename)[0],
        directory    = os.path.dirname(path),
        size         = stat.st_size,
        date_created = stat.st_ctime,
        extension    = os.path.splitext(filename)[1].lstrip(".").lower(),
    )


def scan_directory(root: str, extensions: List[str], recursive: bool = True,
                   progress: Optional[Callable[[int, str], None]] = None,
                   cancelled: Optional[Callable[[], bool]] = None) -> List[FileInfo]:
    """
    Scan *root* (recursively by default) and return FileInfo for every file
    whose extension (lowercase, no dot) is in *extensions*.
    *progress(n_trouvés, dossier)* est appelé au plus ~10 fois par seconde.
    """
    exts = {e.lower().lstrip(".") for e in extensions}
    results: List[FileInfo] = []
    last = 0.0

    for dirpath, dirs, files in os.walk(root):
        if cancelled and cancelled():
            break
        if progress and time.monotonic() - last > 0.1:
            last = time.monotonic()
            progress(len(results), dirpath)
        # Prune excluded directories in-place so os.walk won't descend into them
        dirs[:] = [d for d in dirs if d not in _EXCLUDED_DIRS] if recursive else []
        for filename in files:
            ext = os.path.splitext(filename)[1].lstrip(".").lower()
            if ext not in exts:
                continue
            full_path = os.path.join(dirpath, filename)
            try:
                stat = os.stat(full_path)
                results.append(FileInfo(
                    path         = full_path,
                    name         = os.path.splitext(filename)[0],
                    directory    = dirpath,
                    size         = stat.st_size,
                    date_created = stat.st_ctime,
                    extension    = ext,
                ))
            except OSError:
                continue

    return results


class ScanThread(QThread):
    """Scan en arrière-plan : l'interface reste fluide pendant le chargement."""
    progress = pyqtSignal(int, str)        # fichiers trouvés, dossier en cours
    done     = pyqtSignal(object)          # List[FileInfo]

    def __init__(self, root: str, extensions: List[str]):
        super().__init__()
        self._root, self._exts = root, extensions
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        files = scan_directory(self._root, self._exts,
                               progress=lambda n, d: self.progress.emit(n, d),
                               cancelled=lambda: self._cancelled)
        if not self._cancelled:
            self.done.emit(files)
