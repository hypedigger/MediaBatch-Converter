"""
Envoi de fichiers vers la Corbeille Windows (récupérables), sans dépendance.
"""

import ctypes
import ctypes.wintypes
import os
from typing import Iterable


class _SHFILEOPSTRUCT(ctypes.Structure):
    _fields_ = [
        ("hwnd",                  ctypes.wintypes.HWND),
        ("wFunc",                 ctypes.wintypes.UINT),
        ("pFrom",                 ctypes.c_wchar_p),
        ("pTo",                   ctypes.c_wchar_p),
        ("fFlags",                ctypes.c_ushort),
        ("fAnyOperationsAborted", ctypes.wintypes.BOOL),
        ("hNameMappings",         ctypes.c_void_p),
        ("lpszProgressTitle",     ctypes.c_wchar_p),
    ]


_FO_DELETE           = 0x0003
_FOF_SILENT          = 0x0004
_FOF_NOCONFIRMATION  = 0x0010
_FOF_ALLOWUNDO       = 0x0040           # → Corbeille plutôt que suppression
_FOF_NOERRORUI       = 0x0400
_FOF_WANTNUKEWARNING = 0x4000           # prévient si un fichier serait supprimé
                                        # définitivement (lecteur sans Corbeille)


def send_to_recycle_bin(paths: Iterable[str]) -> bool:
    """
    Envoie *paths* à la Corbeille en une seule opération. Retourne False si
    l'opération a échoué ou a été annulée par l'utilisateur.
    """
    paths = [os.path.normpath(p) for p in paths if p]
    if not paths:
        return True
    # Liste séparée par des NUL et terminée par deux NUL : un tampon garde les
    # NUL intermédiaires, qu'une simple chaîne Python ne transmettrait pas
    buf = ctypes.create_unicode_buffer("\0".join(paths) + "\0\0")
    op = _SHFILEOPSTRUCT()
    op.wFunc  = _FO_DELETE
    op.pFrom  = ctypes.cast(buf, ctypes.c_wchar_p)
    op.fFlags = (_FOF_ALLOWUNDO | _FOF_NOCONFIRMATION | _FOF_SILENT
                 | _FOF_NOERRORUI | _FOF_WANTNUKEWARNING)
    rc = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(op))
    return rc == 0 and not op.fAnyOperationsAborted
