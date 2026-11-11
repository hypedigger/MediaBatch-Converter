import os
import threading
from typing import List, Dict, Any, Tuple

from core.scanner      import FileInfo
from core.converter    import ConversionThread, get_output_path
from core               import proc_pool
from core.recycle      import send_to_recycle_bin

# Message renvoyé quand l'original est conservé (résultat plus lourd)
SKIPPED = "skipped"
# Message renvoyé quand l'original, remplacé par sa sortie, est parti à la Corbeille
REPLACED = "replaced"

_recycle_lock = threading.Lock()


def _set_created_now(path: str):
    """
    Date de création = maintenant (Windows). La date de modification reste celle
    de la photo, mais la date de création marque la conversion : l'option
    « Ignorer les images créées il y a moins de N h » s'appuie dessus. Sans cela,
    l'effet « tunnel » de NTFS redonne à un fichier remplacé sous le même nom la
    date de création de l'original.
    """
    if os.name != "nt":
        return
    try:
        import ctypes
        from ctypes import wintypes
        k32 = ctypes.windll.kernel32
        k32.CreateFileW.restype = wintypes.HANDLE
        h = k32.CreateFileW(path, 0x0100, 0x7, None, 3, 0x02000000, None)  # FILE_WRITE_ATTRIBUTES
        if h in (None, wintypes.HANDLE(-1).value):
            return
        try:
            now = wintypes.FILETIME()
            k32.GetSystemTimeAsFileTime(ctypes.byref(now))
            k32.SetFileTime(h, ctypes.byref(now), None, None)
        finally:
            k32.CloseHandle(h)
    except Exception:
        pass


class ImageConversionThread(ConversionThread):
    """Même pilotage que la conversion audio (pool, annulation, signaux), via Pillow."""

    def __init__(
        self,
        files:          List[FileInfo],
        out_fmt:        Dict[str, Any],
        quality:        int,
        max_side:       int,
        keep_if_larger: bool,
        parallel:       int,
        conflict:       str,  # "overwrite" | "rename"
        suffix:         str  = "_v2",
        subdir:         str  = "",
        recycle_replaced: bool = False,
    ):
        super().__init__(files, "", out_fmt, proc_pool.worker_count(parallel), conflict)
        self._quality          = quality
        self._max_side         = max_side
        self._keep_if_larger   = keep_if_larger
        self._suffix           = suffix
        self._subdir           = subdir
        self._recycle_replaced = recycle_replaced

    def run(self):
        # Encodages dans des processus séparés (voir core/proc_pool.py) :
        # les threads du pool ne font qu'attendre et écrire les fichiers
        proc_pool.acquire(self._parallel)
        try:
            super().run()
        finally:
            proc_pool.release()

    def _convert_one(self, fi: FileInfo) -> Tuple[str, str]:
        if self._cancelled:
            raise RuntimeError("Annulé")

        data = proc_pool.encode(fi.path, self._out_fmt, self._quality, self._max_side)

        if self._keep_if_larger and len(data) >= fi.size:
            # Rien à gagner : l'original reste en place, intact
            return fi.path, SKIPPED

        dst = get_output_path(fi.path, self._out_fmt["ext"], self._conflict,
                              self._suffix, self._subdir)
        os.makedirs(os.path.dirname(dst), exist_ok=True)

        # Écriture via un fichier temporaire : un écrasement interrompu ne
        # laisse jamais une image tronquée à la place de l'original
        st = os.stat(fi.path)
        tmp = dst + ".part"
        with open(tmp, "wb") as f:
            f.write(data)

        msg = ""
        same_file = os.path.normcase(os.path.abspath(dst)) == os.path.normcase(os.path.abspath(fi.path))
        if same_file and self._recycle_replaced:
            # L'original va être remplacé par sa sortie : il passe d'abord par la
            # Corbeille pour rester récupérable
            with _recycle_lock:
                ok = send_to_recycle_bin([fi.path]) and not os.path.exists(fi.path)
            if not ok:
                os.remove(tmp)
                raise RuntimeError("impossible d'envoyer l'original à la corbeille")
            msg = REPLACED

        os.replace(tmp, dst)
        # Conserver la date de modification (tri chronologique des photos)
        os.utime(dst, (st.st_atime, st.st_mtime))
        _set_created_now(dst)
        return dst, msg
