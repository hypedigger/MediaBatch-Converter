"""
Encodage d'images avec Pillow — partagé par la conversion et l'estimation.
Tout se fait en mémoire : on obtient les octets du fichier de sortie, que
l'appelant écrit sur disque (conversion) ou se contente de mesurer (estimation).
"""

import io
from typing import Any, Dict, Optional, Tuple

from PIL import Image

# Photos de très grande taille (scans, panoramas) : ce sont les fichiers de
# l'utilisateur, pas une source hostile → pas de limite « decompression bomb »
Image.MAX_IMAGE_PIXELS = None

_SIXTEEN_BIT = ("I;16", "I;16B", "I;16L", "I")


def probe_size(path: str) -> Optional[Tuple[int, int]]:
    """Dimensions (largeur, hauteur) lues dans l'en-tête, sans décoder l'image."""
    try:
        with Image.open(path) as im:
            return im.size
    except Exception:
        return None


def target_size(w: int, h: int, max_side: int) -> Tuple[int, int]:
    """Taille après redimensionnement « côté le plus long ≤ max_side »."""
    if not max_side or max(w, h) <= max_side:
        return w, h
    scale = max_side / max(w, h)
    return max(1, round(w * scale)), max(1, round(h * scale))


def _has_alpha(img: Image.Image) -> bool:
    return img.mode in ("RGBA", "LA", "PA") or (
        img.mode == "P" and "transparency" in img.info
    )


def _flatten(img: Image.Image, bg=(255, 255, 255)) -> Image.Image:
    """Transparence → fond uni (le JPEG n'a pas de canal alpha)."""
    rgba = img.convert("RGBA")
    out = Image.new("RGB", rgba.size, bg)
    out.paste(rgba, mask=rgba.getchannel("A"))
    return out


def _to_8bit(img: Image.Image) -> Image.Image:
    if img.mode != "I":
        img = img.convert("I")
    return img.point(lambda v: v * (1 / 256)).convert("L")


def _prepare(img: Image.Image, pil_fmt: str, max_side: int) -> Tuple[Image.Image, bool]:
    """
    Adapte le mode couleur au format cible et redimensionne.
    Retourne (image, icc_valide) — le profil ICC n'est plus valable si on a
    converti une image CMJN en RVB.
    """
    icc_ok = True

    # Palettes et 1 bit : passer en RVB(A) pour un redimensionnement propre
    if img.mode in ("P", "1"):
        img = img.convert("RGBA" if _has_alpha(img) else ("L" if img.mode == "1" else "RGB"))

    if img.mode in _SIXTEEN_BIT and pil_fmt not in ("PNG", "JPEG2000"):
        img = _to_8bit(img)

    if img.mode == "CMYK" and pil_fmt != "JPEG":
        img = img.convert("RGB")
        icc_ok = False

    if pil_fmt == "JPEG":
        if _has_alpha(img):
            img = _flatten(img)
        elif img.mode not in ("L", "RGB", "CMYK"):
            img = img.convert("RGB")
    elif pil_fmt == "WEBP":
        if img.mode not in ("RGB", "RGBA"):
            img = img.convert("RGBA" if _has_alpha(img) else "RGB")
    elif pil_fmt == "JPEG2000":
        if img.mode not in ("L", "LA", "RGB", "RGBA", "I;16"):
            if img.mode in _SIXTEEN_BIT:
                img = img.convert("I;16")
            else:
                img = img.convert("RGBA" if _has_alpha(img) else "RGB")
    elif pil_fmt == "PNG":
        if img.mode not in ("L", "LA", "RGB", "RGBA", "I", "I;16"):
            img = img.convert("RGBA" if _has_alpha(img) else "RGB")

    tw, th = target_size(img.width, img.height, max_side)
    if (tw, th) != img.size:
        if img.mode in _SIXTEEN_BIT and img.mode != "I":
            img = img.convert("I")          # LANCZOS indisponible en I;16
        img = img.resize((tw, th), Image.Resampling.LANCZOS)
        if pil_fmt in ("JPEG2000", "PNG") and img.mode == "I":
            img = img.convert("I;16")
    return img, icc_ok


def _save_kwargs(pil_fmt: str, quality: int, meta: Dict[str, Any]) -> Dict[str, Any]:
    kw: Dict[str, Any] = {}
    if pil_fmt == "JPEG":
        kw.update(quality=quality, optimize=True, progressive=True,
                  # 4:4:4 en haute qualité (texte, aplats colorés nets)
                  subsampling=0 if quality >= 90 else 2)
    elif pil_fmt == "WEBP":
        if quality >= 100:
            kw.update(lossless=True, quality=80, method=4)
        else:
            kw.update(quality=quality, method=4)
    elif pil_fmt == "JPEG2000":
        if quality >= 100:
            kw.update(irreversible=False)      # ondelette 5/3 → sans perte
        else:
            # Qualité → PSNR cible, calé sur des photos réelles pour que
            # 85 donne en moyenne le poids d'un JPEG 85 (≈ 36 dB)
            kw.update(irreversible=True, quality_mode="dB",
                      quality_layers=[max(20.0, 36 + (quality - 85) * 0.2)])
    elif pil_fmt == "PNG":
        kw.update(optimize=True)

    # Métadonnées : EXIF (date, appareil, orientation), profil couleur, DPI
    if meta.get("exif") and pil_fmt in ("JPEG", "WEBP", "PNG"):
        kw["exif"] = meta["exif"]
    if meta.get("icc_profile") and pil_fmt in ("JPEG", "WEBP", "PNG"):
        kw["icc_profile"] = meta["icc_profile"]
    if meta.get("dpi") and pil_fmt in ("JPEG", "PNG"):
        kw["dpi"] = meta["dpi"]
    return kw


def encode_image(path: str, out_fmt: Dict[str, Any], quality: int,
                 max_side: int = 0) -> bytes:
    """Ouvre *path*, le convertit selon *out_fmt* et retourne les octets produits."""
    pil_fmt = out_fmt["pil"]
    with Image.open(path) as src:
        meta = {k: src.info.get(k) for k in ("exif", "icc_profile", "dpi")}
        if src.format == "JPEG" and max_side:
            # Décodage JPEG directement à 1/2, 1/4 ou 1/8 quand on réduit :
            # beaucoup plus rapide, et LANCZOS termine le travail
            src.draft(src.mode, target_size(src.width, src.height, max_side))
        src.load()
        img, icc_ok = _prepare(src, pil_fmt, max_side)
        if not icc_ok:
            meta["icc_profile"] = None
        buf = io.BytesIO()
        img.save(buf, format=pil_fmt, **_save_kwargs(pil_fmt, quality, meta))
    return buf.getvalue()
