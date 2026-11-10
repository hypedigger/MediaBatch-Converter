import os
import sys

# !! IMPORTANT : incrémenter APP_VERSION à chaque modification du code !!
APP_VERSION = 27
APP_DATE = "10/11/2026"
APP_TITLE = f"MediaBatch Converter  —  v{APP_VERSION}  —  {APP_DATE}"

if getattr(sys, "frozen", False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

FFMPEG_DIR = os.path.join(BASE_DIR, "ffmpeg_bin")
LOGS_DIR   = os.path.join(BASE_DIR, "logs")
CONFIG_FILE = os.path.join(BASE_DIR, "config.json")

FFMPEG_DOWNLOAD_URL = (
    "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/"
    "ffmpeg-master-latest-win64-gpl.zip"
)

SUPPORTED_INPUT_FORMATS = {
    "FLAC":  "flac",
    "MP3":   "mp3",
    "OGG":   "ogg",
    "WAV":   "wav",
    "WMA":   "wma",
    "MPC":   "mpc",
    "AAC":   "aac",
    "OPUS":  "opus",
    "M4A":   "m4a",
    "APE":   "ape",
    "AIFF":  "aiff",
    "WV":    "wv",
}

# "cover": True → la pochette embarquée est recopiée dans le fichier de sortie.
# False pour OGG/Opus : FFmpeg ne sait pas écrire de pochette dans ces conteneurs.
OUTPUT_FORMATS = [
    {
        "id": "mp3_320",
        "label": "MP3 — 320 kbps (CBR)",
        "description": "Qualité maximale CBR. Compatible avec tous les lecteurs.",
        "ext": "mp3",
        "ffmpeg_args": ["-codec:a", "libmp3lame", "-b:a", "320k"],
        "cover": True,
    },
    {
        "id": "mp3_vbr_v0",
        "label": "MP3 VBR — V0  (~245 kbps)",
        "description": "Qualité maximale variable. Pratiquement indiscernable du lossless.",
        "ext": "mp3",
        "ffmpeg_args": ["-codec:a", "libmp3lame", "-q:a", "0"],
        "cover": True,
    },
    {
        "id": "mp3_vbr_v2",
        "label": "MP3 VBR — V2  (~190 kbps)",
        "description": "Excellent rapport qualité/taille. Recommandé pour usage général.",
        "ext": "mp3",
        "ffmpeg_args": ["-codec:a", "libmp3lame", "-q:a", "2"],
        "cover": True,
    },
    {
        "id": "mp3_vbr_v4",
        "label": "MP3 VBR — V4  (~165 kbps)",
        "description": "Bon compromis pour les appareils à stockage limité.",
        "ext": "mp3",
        "ffmpeg_args": ["-codec:a", "libmp3lame", "-q:a", "4"],
        "cover": True,
    },
    {
        "id": "mp3_vbr_v6",
        "label": "MP3 VBR — V6  (~115 kbps)",
        "description": "Compression agressive, qualité audible mais dégradée.",
        "ext": "mp3",
        "ffmpeg_args": ["-codec:a", "libmp3lame", "-q:a", "6"],
        "cover": True,
    },
    {
        "id": "ogg",
        "label": "OGG Vorbis — Q6  (~192 kbps)",
        "description": "Format libre. Légèrement meilleur que MP3 à bitrate équivalent.",
        "ext": "ogg",
        "ffmpeg_args": ["-codec:a", "libvorbis", "-q:a", "6"],
        "cover": False,
    },
    {
        "id": "opus",
        "label": "OPUS — 192 kbps",
        "description": "Format moderne et efficace. Idéal pour streaming/mobile.",
        "ext": "opus",
        "ffmpeg_args": ["-codec:a", "libopus", "-b:a", "192k"],
        "cover": False,
    },
    {
        "id": "flac",
        "label": "FLAC — Lossless",
        "description": "Sans perte de qualité. Fichiers volumineux. Idéal pour archivage.",
        "ext": "flac",
        "ffmpeg_args": ["-codec:a", "flac"],
        "cover": True,
    },
    {
        "id": "aac",
        "label": "AAC — 256 kbps",
        "description": "Meilleur que MP3 à bitrate équivalent. Utilisé par Apple/streaming.",
        "ext": "m4a",
        "ffmpeg_args": ["-codec:a", "aac", "-b:a", "256k"],
        "cover": True,
    },
]

PARALLEL_OPTIONS = [
    {"label": "4 conversions simultanées",        "value": 4},
    {"label": "8 conversions simultanées",        "value": 8},
    {"label": "Automatique (selon charge CPU)",   "value": 0},
]

# ── Mode Images ──────────────────────────────────────────────────────────────

# Nom affiché → extensions (minuscules, sans point)
IMAGE_INPUT_FORMATS = {
    "JPEG":     ["jpg", "jpeg", "jfif"],
    "PNG":      ["png"],
    "WEBP":     ["webp"],
    "TIFF":     ["tif", "tiff"],
    "BMP":      ["bmp"],
    "JPEG2000": ["jp2", "j2k"],
}

# "pil" = nom du format pour Pillow ; "quality" = curseur de qualité utilisable
IMAGE_OUTPUT_FORMATS = [
    {
        "id": "jpeg",
        "label": "JPEG",
        "description": "Universel. 85 = très bon compromis, 75 = compression forte.",
        "ext": "jpg",
        "pil": "JPEG",
        "quality": True,
        "default_quality": 85,
    },
    {
        "id": "jp2",
        "label": "JPEG 2000",
        "description": "Dégradation plus douce que JPEG (flou plutôt que blocs). Peu de logiciels le lisent. Lent. 100 = sans perte.",
        "ext": "jp2",
        "pil": "JPEG2000",
        "quality": True,
        "default_quality": 80,
    },
    {
        "id": "webp",
        "label": "WebP",
        "description": "Format web moderne, ~30 % plus léger que JPEG. 100 = sans perte.",
        "ext": "webp",
        "pil": "WEBP",
        "quality": True,
        "default_quality": 85,
    },
    {
        "id": "png",
        "label": "PNG — sans perte",
        "description": "Aucune perte de qualité. Idéal pour captures d'écran et dessins, lourd pour les photos.",
        "ext": "png",
        "pil": "PNG",
        "quality": False,
        "default_quality": 100,
    },
]

# Côté le plus long en pixels (0 = taille d'origine)
IMAGE_RESIZE_OPTIONS = [0, 4096, 3840, 2560, 2048, 1920, 1600, 1280, 1024]

DEFAULT_SETTINGS = {
    "theme":             "dark",
    "parallel":          8,
    "last_directory":    "",
    "selected_formats":  list(SUPPORTED_INPUT_FORMATS.keys()),
    "default_output_format": "mp3_320",
    "mode":                  "audio",   # "audio" | "image"
    "image_selected_formats": ["JPEG", "PNG"],
    "image_output_format":   "jpeg",
    "image_quality":         {},        # id de format → qualité choisie
    "image_max_side":        0,
    "image_keep_if_larger":  True,
    "image_rename_conflicts": True,     # sinon : écraser
    "image_rename_suffix":   "_v2",
    "image_use_subdir":      False,
    "image_subdir":          "Reduced",
    "recent_directories":    [],        # 5 derniers dossiers utilisés
}
