"""
Recherche automatique de tags manquants.

1. Heuristique locale : "Artiste - Titre.mp3", numéro de piste, dossier parent
   comme album ("1999 - Album", "Album (1999)", "Artiste - Album").
2. Enrichissement en ligne via l'API MusicBrainz (gratuite, sans clé,
   limite : 1 requête/seconde — respectée par l'appelant).
"""
import json
import os
import re
import urllib.parse
import urllib.request
from typing import Dict, Tuple

_USER_AGENT = "MediaBatchConverter/14 (+https://github.com/hypedigger/MediaBatch-Converter)"

# Dossiers dont le nom ne doit PAS être pris pour un nom d'album
_GENERIC_DIRS = {
    "mp3", "mp3s", "flac", "music", "musique", "musiques", "audio", "son",
    "downloads", "téléchargements", "telechargements", "a trier", "à trier",
    "new", "nouveau", "temp", "tmp", "divers", "various",
}


def guess_from_filename(path: str) -> Dict[str, str]:
    """Déduit artiste/titre/album/année/piste du nom de fichier et du dossier."""
    tags: Dict[str, str] = {}

    stem = os.path.splitext(os.path.basename(path))[0].strip()
    if " " not in stem:
        stem = stem.replace("_", " ").strip()

    # Numéro de piste en tête : "07 - Titre", "07. Titre"
    m = re.match(r"^(\d{1,3})[\s.\-–—]+(?=\D)(.+)$", stem)
    if m and len(m.group(2).strip()) > 1:
        tags["tracknumber"] = str(int(m.group(1)))
        stem = m.group(2).strip()

    # "Artiste - Titre" ou "Artiste - Album - Titre"
    parts = [p.strip() for p in re.split(r"\s+[-–—]\s+", stem) if p.strip()]
    if len(parts) >= 2:
        tags["artist"] = parts[0]
        tags["title"]  = parts[-1]
        if len(parts) >= 3:
            tags["album"] = parts[1]
    elif stem:
        tags["title"] = stem

    # Dossier parent → album / année
    parent = os.path.basename(os.path.dirname(path)).strip()
    if (parent and "album" not in tags
            and parent.lower().lstrip("_ ") not in _GENERIC_DIRS):
        album = parent
        m = re.match(r"^(\d{4})\s*[-–—]\s*(.+)$", album)          # "1999 - Album"
        if m:
            tags["date"] = m.group(1)
            album = m.group(2).strip()
        else:
            m = re.search(r"\((\d{4})\)\s*$", album)              # "Album (1999)"
            if m:
                tags["date"] = m.group(1)
                album = album[:m.start()].strip()
        # "Artiste - Album" → ne garder que l'album
        sub = [p.strip() for p in re.split(r"\s+[-–—]\s+", album)]
        if len(sub) == 2 and tags.get("artist") \
                and sub[0].lower() == tags["artist"].lower():
            album = sub[1]
        if album:
            tags["album"] = album

    return tags


def musicbrainz_lookup(artist: str, title: str, timeout: float = 5.0) -> Dict[str, str]:
    """Recherche MusicBrainz. Return {} si aucun résultat. Raise sur erreur réseau."""
    query = f'recording:"{title}" AND artist:"{artist}"'
    url = ("https://musicbrainz.org/ws/2/recording?"
           + urllib.parse.urlencode({"query": query, "fmt": "json", "limit": "1"}))
    req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})

    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode("utf-8"))

    recordings = data.get("recordings") or []
    if not recordings:
        return {}
    rec = recordings[0]

    out = {"title": rec.get("title", "")}
    credits = rec.get("artist-credit") or []
    if credits:
        out["artist"] = credits[0].get("name", "")
    releases = rec.get("releases") or []
    if releases:
        out["album"] = releases[0].get("title", "")
        date = releases[0].get("date", "")
        if date[:4].isdigit():
            out["date"] = date[:4]

    return {k: v for k, v in out.items() if v}


def find_tags(path: str, existing: Dict[str, str],
              online: bool = True) -> Tuple[Dict[str, str], bool, bool]:
    """
    Détermine les tags à ajouter au fichier converti.

    Return (tags_manquants, réseau_utilisé, réseau_ok) :
    seuls les champs absents de *existing* sont retournés.
    """
    guess  = guess_from_filename(path)
    result = dict(guess)
    used_net, net_ok = False, True

    artist = existing.get("artist") or guess.get("artist", "")
    title  = existing.get("title")  or guess.get("title", "")
    if online and artist and title:
        used_net = True
        try:
            mb = musicbrainz_lookup(artist, title)
            result.update(mb)   # MusicBrainz prime sur l'heuristique
        except Exception:
            net_ok = False      # hors-ligne / erreur : l'heuristique suffit

    missing = {k: v for k, v in result.items() if v and not existing.get(k)}
    return missing, used_net, net_ok
