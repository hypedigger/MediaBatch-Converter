import os
from dataclasses import dataclass
from typing import List, Optional

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


def scan_directory(root: str, extensions: List[str], recursive: bool = True) -> List[FileInfo]:
    """
    Scan *root* (recursively by default) and return FileInfo for every file
    whose extension (lowercase, no dot) is in *extensions*.
    """
    exts = {e.lower().lstrip(".") for e in extensions}
    results: List[FileInfo] = []

    for dirpath, dirs, files in os.walk(root):
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
