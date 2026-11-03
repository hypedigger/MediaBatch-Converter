import os
from typing import List, Dict, Any, Tuple

from core.scanner      import FileInfo
from core.converter    import ConversionThread, get_output_path
from core.image_codec  import encode_image
from core.logger       import get_app_logger

# Message renvoyé quand l'original est conservé (résultat plus lourd)
SKIPPED = "skipped"


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
        delete_source:  bool,
        conflict:       str,  # "overwrite" | "rename"
    ):
        super().__init__(files, "", out_fmt, parallel, delete_source, conflict)
        self._quality        = quality
        self._max_side       = max_side
        self._keep_if_larger = keep_if_larger

    def _convert_one(self, fi: FileInfo) -> Tuple[str, str]:
        if self._cancelled:
            raise RuntimeError("Annulé")

        data = encode_image(fi.path, self._out_fmt, self._quality, self._max_side)

        if self._keep_if_larger and len(data) >= fi.size:
            # Rien à gagner : l'original reste en place, intact
            return fi.path, SKIPPED

        dst = get_output_path(fi.path, self._out_fmt["ext"], self._conflict)
        same_file = os.path.normcase(os.path.abspath(dst)) == \
                    os.path.normcase(os.path.abspath(fi.path))

        # Écriture via un fichier temporaire : un écrasement interrompu ne
        # laisse jamais une image tronquée à la place de l'original
        st = os.stat(fi.path)
        tmp = dst + ".part"
        with open(tmp, "wb") as f:
            f.write(data)
        os.replace(tmp, dst)
        # Conserver la date de modification (tri chronologique des photos)
        os.utime(dst, (st.st_atime, st.st_mtime))

        if self._delete_source and not same_file:
            try:
                os.remove(fi.path)
            except OSError as e:
                get_app_logger().warning(
                    "Impossible de supprimer source %s : %s", fi.path, e
                )
        return dst, ""
