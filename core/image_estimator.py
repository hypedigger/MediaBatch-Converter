"""
Estimation du poids d'un lot d'images après conversion, sans tout convertir.

Principe (calibré sur des dossiers réels) :
  1. Lecture des en-têtes de TOUS les fichiers (instantané) : dimensions et,
     pour les JPEG, tables de quantification = qualité d'origine.
  2. Conversion en mémoire d'un échantillon, choisi de façon régulière parmi
     les fichiers triés par qualité d'origine.
  3. Régression  log(sortie / source) = a + b·x  sur l'échantillon, appliquée
     à chaque fichier (x = qualité d'origine du JPEG, ou bits/pixel sinon).
     Un JPEG déjà très compressé ne gagne presque rien, un JPEG « qualité
     maximale » fond : ce critère explique ~90 % de l'écart entre fichiers.
  4. Tant que la marge d'erreur reste large, on ajoute des échantillons.

Gros dossiers (> HEADER_CAP images) : lire chaque en-tête coûte un accès
disque (~10–50 ms sur un disque dur externe). On ne lit alors que HEADER_CAP
en-têtes, choisis régulièrement par type et par taille, on estime ce
sous-ensemble comme ci-dessus, puis on extrapole aux autres fichiers selon
leur taille ; la marge tient compte de cet échantillonnage supplémentaire.
"""

import math
import os
import threading
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Tuple

from concurrent.futures import ThreadPoolExecutor, as_completed

from PIL import Image
from PyQt6.QtCore import QThread, pyqtSignal

from core.image_codec import encode_image, target_size
from core.scanner     import FileInfo
from core.logger      import get_app_logger

INITIAL_SAMPLES = 12        # en dessous, la dispersion mesurée est trop optimiste
SAMPLE_STEP     = 6
MAX_SAMPLES     = 48
TARGET_MARGIN   = 0.08      # marge visée (±8 %) avant d'arrêter l'échantillonnage
# Le modèle n'est pas parfait : marge statistique × 1.5, et jamais sous ±5 %
MARGIN_SAFETY   = 1.5
MARGIN_FLOOR    = 0.05
HEADER_CAP      = 300       # au-delà, en-têtes lus d'abord sur un échantillon
HEADER_TARGET   = 0.03      # erreur d'extrapolation tolérée avant de lire plus d'en-têtes
# Extrapolation réservée aux dossiers homogènes (photos d'un même appareil :
# 1 à 12 niveaux de qualité JPEG ; images téléchargées : 30 à 60)
HOMOGENEOUS_MAX_LEVELS = 8
HOMOGENEOUS_MIN_JPEG   = 0.95

_lock         = threading.Lock()
_header_cache: Dict[Tuple[str, float, int], Optional["_Header"]] = {}
_encode_cache: Dict[tuple, Optional[int]] = {}


@dataclass
class _Header:
    w:     int
    h:     int
    q_avg: Optional[float]   # moyenne de la table de quantification luma (JPEG)


@dataclass
class Estimate:
    n_files:   int
    src_bytes: int
    est_bytes: int
    n_samples: int
    margin:    float          # demi-largeur relative d'un intervalle à ~90 %
    # Par fichier, dans l'ordre de la liste fournie : (octets estimés, mesuré)
    # mesuré : True = conversion d'essai, False = prédit d'après l'en-tête,
    # None = extrapolé d'après la taille (en-tête non lu, gros dossier)
    per_file:  Optional[List[Tuple[int, Optional[bool]]]] = None
    headers_read: int = 0

    @property
    def exact(self) -> bool:
        return self.n_samples >= self.n_files

    @property
    def gain_bytes(self) -> int:
        return self.src_bytes - self.est_bytes

    @property
    def gain_pct(self) -> float:
        return (1 - self.est_bytes / self.src_bytes) * 100 if self.src_bytes else 0.0


# ── En-têtes ─────────────────────────────────────────────────────────────────

def _header(fi: FileInfo) -> Optional[_Header]:
    key = (fi.path, fi.date_created, fi.size)
    with _lock:
        if key in _header_cache:
            return _header_cache[key]
    hdr = None
    try:
        with Image.open(fi.path) as im:
            q = getattr(im, "quantization", None)
            q_avg = None
            if q:
                table = q.get(0) or next(iter(q.values()))
                q_avg = sum(table) / len(table)
            hdr = _Header(im.width, im.height, q_avg)
    except Exception:
        pass
    with _lock:
        _header_cache[key] = hdr
    return hdr


def _encoded_size(fi: FileInfo, out_fmt: Dict[str, Any], quality: int,
                  max_side: int) -> Optional[int]:
    key = (fi.path, fi.date_created, fi.size, out_fmt["id"], quality, max_side)
    with _lock:
        if key in _encode_cache:
            return _encode_cache[key]
    try:
        n = len(encode_image(fi.path, out_fmt, quality, max_side))
    except Exception:
        n = None
    with _lock:
        _encode_cache[key] = n
    return n


# ── Échantillonnage ──────────────────────────────────────────────────────────

def _systematic(items: List[int], key: Callable[[int], float], k: int) -> List[int]:
    """k éléments régulièrement espacés dans *items* trié selon *key*."""
    items = sorted(items, key=key)
    n = len(items)
    if k >= n:
        return items
    step = n / k
    return [items[int((i + 0.5) * step)] for i in range(k)]


class _Stratum:
    """Groupe de fichiers homogène (JPEG / autres) avec son propre modèle."""

    def __init__(self, idx: List[int], base: List[float], x: List[float]):
        self.idx     = idx
        self.base    = base
        self.x       = x
        self.sampled: Dict[int, int] = {}      # index → octets produits

    def pick(self, k: int) -> List[int]:
        rest = [i for i in self.idx if i not in self.sampled]
        return _systematic(rest, lambda i: self.x[i], min(k, len(rest)))

    def fit(self) -> Callable[[int], float]:
        """Retourne une fonction index → octets prédits (calée sur l'échantillon)."""
        s = list(self.sampled)
        ys = [math.log(max(self.sampled[i], 1) / self.base[i]) for i in s]
        xs = [self.x[i] for i in s]
        mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
        b = 0.0
        if len(s) >= 4:
            vx = sum((v - mx) ** 2 for v in xs)
            if vx > 1e-9:
                b = sum((u - mx) * (v - my) for u, v in zip(xs, ys)) / vx
                b = max(-3.0, min(3.0, b))
        raw = lambda i: self.base[i] * math.exp(my + b * (self.x[i] - mx))
        # Calage : la somme prédite sur l'échantillon = la somme réelle
        c = sum(self.sampled.values()) / max(sum(raw(i) for i in s), 1e-9)
        return lambda i: c * raw(i)

    def total(self, keep_if_larger: bool, src: List[int]) -> Tuple[float, float]:
        """(octets estimés pour le groupe, variance estimée de ce total)."""
        pred = self.fit()
        n, N = len(self.sampled), len(self.idx)
        est = 0.0
        for i in self.idx:
            v = self.sampled.get(i)
            if v is None:
                v = pred(i)
            if keep_if_larger:
                v = min(v, src[i])
            est += v
        if n >= N:
            return est, 0.0
        if n < 2:
            return est, (0.5 * est) ** 2
        r = [self.sampled[i] / max(pred(i), 1e-9) for i in self.sampled]
        mean = sum(r) / n
        var_r = sum((v - mean) ** 2 for v in r) / (n - 1)
        rest = est - sum(self.sampled.values())
        # Erreur sur la partie extrapolée, avec correction de population finie
        return est, (rest ** 2) * var_r / n * (1 - n / N)


def _family(fi: FileInfo) -> str:
    return "jpeg" if fi.extension in ("jpg", "jpeg", "jfif") else fi.extension


def _header_cached(fi: FileInfo) -> bool:
    with _lock:
        return (fi.path, fi.date_created, fi.size) in _header_cache


def _spread_order(n: int) -> List[int]:
    """
    Permutation de 0..n-1 dont chaque préfixe est réparti uniformément
    (suite de van der Corput) : lire les k premiers = un échantillon régulier,
    et en lire plus ne fait que le compléter.
    """
    m = max(1, (n - 1).bit_length())
    seen, out = set(), []
    for k in range(1 << m):
        rev = int(format(k, f"0{m}b")[::-1], 2)
        pos = rev * n >> m
        if pos not in seen:
            seen.add(pos)
            out.append(pos)
    return out


def estimate_files(
    files:          List[FileInfo],
    out_fmt:        Dict[str, Any],
    quality:        int,
    max_side:       int,
    keep_if_larger: bool,
    executor=None,
    cancelled:      Callable[[], bool] = lambda: False,
    max_samples:    int = MAX_SAMPLES,
    on_progress:    Optional[Callable[[str, int], None]] = None,
    header_cap:     Optional[int] = HEADER_CAP,
) -> Optional[Estimate]:
    """
    Estimation du poids total après conversion. None si annulé ou vide.
    *on_progress(kind, n)* : "plan" = n en-têtes de plus à lire, "header" =
    un en-tête lu, "sample" = une conversion d'essai (affichage de l'activité).
    *header_cap* : en-têtes lus d'abord sur un échantillon de cette taille,
    complété tant que le dossier s'avère hétérogène (None = tous).
    """
    tick = on_progress or (lambda _kind, _n=1: None)
    args = (out_fmt, quality, max_side, keep_if_larger, executor, cancelled,
            max_samples, tick)
    n_all = len(files)
    if not header_cap or n_all <= header_cap:
        tick("plan", sum(not _header_cached(f) for f in files))
        return _estimate_all(files, *args)

    # Ordre de lecture : fichiers triés par (type, taille), parcourus de façon
    # à ce que chaque tranche couvre tout l'éventail des tailles et des types
    by_size = sorted(range(n_all), key=lambda i: (_family(files[i]), files[i].size))
    order = [by_size[p] for p in _spread_order(n_all)]

    planned = 0
    h = header_cap

    # Premier lot d'en-têtes : le dossier est-il assez homogène pour extrapoler ?
    first = [files[i] for i in order[:h]]
    planned = sum(not _header_cached(f) for f in first)
    tick("plan", planned)
    hdrs = [_header(f) for f in first] if not executor else list(executor.map(_header, first))
    tick("header", planned)
    if cancelled():
        return None
    q_levels = {round(math.log(x.q_avg), 3) for x in hdrs if x and x.q_avg}
    jpeg_share = sum(1 for x in hdrs if x and x.q_avg) / len(first)
    if len(q_levels) > HOMOGENEOUS_MAX_LEVELS or jpeg_share < HOMOGENEOUS_MIN_JPEG:
        tick("plan", n_all - h)
        return _estimate_all(files, *args)

    while True:
        sub_idx = order[:h]
        sub = [files[i] for i in sub_idx]
        new = sum(not _header_cached(f) for f in sub) - planned
        if new > 0:
            tick("plan", new)
            planned += new
        if h >= n_all:
            # Dossier trop hétérogène pour extrapoler : tout est lu
            return _estimate_all(files, *args)
        est = _estimate_all(sub, *args)
        if est is None:
            return None

        # Erreur due à l'échantillonnage des en-têtes (estimateur par ratio)
        ratios = [v / fi.size for fi, (v, _m) in zip(sub, est.per_file) if fi.size]
        se = 0.0
        if len(ratios) > 1:
            mean = sum(ratios) / len(ratios)
            sd = math.sqrt(sum((r - mean) ** 2 for r in ratios) / (len(ratios) - 1))
            if mean > 0:
                se = sd / mean / math.sqrt(len(ratios)) * math.sqrt(1 - h / n_all)
        header_err = MARGIN_SAFETY * 1.645 * se
        if header_err <= HEADER_TARGET:
            break
        h = min(n_all, h * 2)           # hétérogène : on lit plus d'en-têtes

    # Taux de compression par type, mesuré sur le sous-ensemble
    fam_src: Dict[str, float] = defaultdict(float)
    fam_est: Dict[str, float] = defaultdict(float)
    for fi, (v, _m) in zip(sub, est.per_file):
        fam_src[_family(fi)] += fi.size
        fam_est[_family(fi)] += v
    overall = est.est_bytes / est.src_bytes if est.src_bytes else 1.0

    per_file: List[Optional[Tuple[int, Optional[bool]]]] = [None] * n_all
    for i, pf in zip(sub_idx, est.per_file):
        per_file[i] = pf
    for i, fi in enumerate(files):
        if per_file[i] is None:
            f = _family(fi)
            r = fam_est[f] / fam_src[f] if fam_src[f] else overall
            per_file[i] = (int(fi.size * r), None)

    return Estimate(
        n_files   = n_all,
        src_bytes = sum(f.size for f in files),
        est_bytes = int(sum(v for v, _m in per_file)),
        n_samples = est.n_samples,
        margin    = max(MARGIN_FLOOR, math.sqrt(est.margin ** 2 + header_err ** 2)),
        per_file  = per_file,
        headers_read = len(sub),
    )


def _estimate_all(
    files:          List[FileInfo],
    out_fmt:        Dict[str, Any],
    quality:        int,
    max_side:       int,
    keep_if_larger: bool,
    executor,
    cancelled:      Callable[[], bool],
    max_samples:    int,
    tick:           Callable[..., None],
) -> Optional[Estimate]:
    """Estimation en lisant l'en-tête de chaque fichier de *files*."""
    if not files:
        return None
    run = (lambda fn, items: list(executor.map(fn, items))) if executor \
        else (lambda fn, items: [fn(it) for it in items])

    def read_header(fi):
        if cancelled():
            return None
        cached = _header_cached(fi)
        h = _header(fi)
        if not cached:
            tick("header")
        return h

    headers = run(read_header, files)
    if cancelled():
        return None

    src = [f.size for f in files]
    base: List[float] = []
    x: List[float] = []
    groups: Dict[str, List[int]] = defaultdict(list)
    unreadable = 0
    for i, (fi, hdr) in enumerate(zip(files, headers)):
        if hdr is None or fi.size == 0:
            base.append(0.0); x.append(0.0)
            unreadable += fi.size           # illisible → compté inchangé
            continue
        tw, th = target_size(hdr.w, hdr.h, max_side)
        # Base = poids source ramené à la surface de sortie
        base.append(fi.size * (tw * th) / (hdr.w * hdr.h))
        if hdr.q_avg:
            x.append(math.log(hdr.q_avg))
            groups["jpeg"].append(i)
        else:
            x.append(math.log(fi.size * 8 / (hdr.w * hdr.h)))
            groups[fi.extension].append(i)

    readable = sum(len(g) for g in groups.values())
    if not readable:
        return Estimate(len(files), sum(src), sum(src), 0, 0.0,
                        [(n, False) for n in src])

    strata = [_Stratum(g, base, x) for g in groups.values()]
    budget = min(max_samples, readable)

    def sample(stratum_picks: List[Tuple[_Stratum, List[int]]]):
        jobs = [(st, i) for st, picks in stratum_picks for i in picks]
        def encode(j):
            n = _encoded_size(files[j[1]], out_fmt, quality, max_side)
            tick("sample")
            return n

        sizes = run(encode, jobs)
        for (st, i), n in zip(jobs, sizes):
            if n is None:                       # échec d'encodage → inchangé
                n = src[i]
            st.sampled[i] = n

    # Premier tour : répartition proportionnelle, au moins 3 par groupe
    k0 = min(INITIAL_SAMPLES, budget)
    sample([(st, st.pick(max(min(3, len(st.idx)), round(k0 * len(st.idx) / readable))))
            for st in strata])

    while True:
        if cancelled():
            return None
        totals = [st.total(keep_if_larger, src) for st in strata]
        est = sum(t for t, _ in totals) + unreadable
        sd  = math.sqrt(sum(v for _, v in totals))
        n_done = sum(len(st.sampled) for st in strata)
        if n_done >= readable:
            margin = 0.0
        else:
            margin = max(MARGIN_FLOOR, MARGIN_SAFETY * 1.645 * sd / est) if est else 0.0
        if n_done >= budget or margin <= TARGET_MARGIN:
            break
        # Ajouter des échantillons là où l'incertitude est la plus forte
        open_k = [k for k, st in enumerate(strata) if len(st.sampled) < len(st.idx)]
        if not open_k:
            break
        st = strata[max(open_k, key=lambda k: totals[k][1])]
        sample([(st, st.pick(min(SAMPLE_STEP, budget - n_done)))])

    # Détail par image (illisibles : comptées inchangées)
    per_file: List[Tuple[int, bool]] = [(n, False) for n in src]
    for st in strata:
        pred = st.fit()
        for i in st.idx:
            measured = i in st.sampled
            v = st.sampled[i] if measured else pred(i)
            if keep_if_larger:
                v = min(v, src[i])
            per_file[i] = (int(v), measured)

    return Estimate(
        n_files   = len(files),
        src_bytes = sum(src),
        est_bytes = int(est),
        n_samples = n_done,
        margin    = margin,
        per_file  = per_file,
        headers_read = len(files),
    )


# ── Threads Qt ───────────────────────────────────────────────────────────────

class EstimateThread(QThread):
    """Estimation de la sélection courante (vue principale)."""

    finished_estimate = pyqtSignal(object)      # Estimate | None

    def __init__(self, files, out_fmt, quality, max_side, keep_if_larger, parallel):
        super().__init__()
        self._args      = (files, out_fmt, quality, max_side, keep_if_larger)
        self._parallel  = parallel
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        with ThreadPoolExecutor(max_workers=self._parallel) as ex:
            est = estimate_files(*self._args, executor=ex,
                                 cancelled=lambda: self._cancelled)
        if not self._cancelled:
            self.finished_estimate.emit(est)


class GroupEstimateThread(QThread):
    """
    Estime le gain de la conversion pour chaque groupe d'images (un groupe =
    les images d'un même dossier, telles qu'affichées dans la liste).
    """

    group_done = pyqtSignal(str, object)        # clé du groupe, Estimate
    all_done   = pyqtSignal()

    def __init__(self, groups: Dict[str, List[FileInfo]], out_fmt, quality, max_side,
                 keep_if_larger, parallel):
        super().__init__()
        self._groups    = groups
        self._opts      = (out_fmt, quality, max_side, keep_if_larger)
        self._parallel  = parallel
        self._cancelled = False
        # Activité, lue par l'interface via snapshot() (simples compteurs)
        self._lock      = threading.Lock()
        self._phase     = "estimate"        # "estimate" → "done"
        self._total     = 0                 # en-têtes à lire (annoncés au fil de l'eau)
        self._headers   = 0                 # en-têtes lus
        self._samples   = 0                 # conversions d'essai faites
        self._current: Dict[str, int] = {}  # dossiers en cours → nb d'images

    def cancel(self):
        self._cancelled = True

    def snapshot(self) -> dict:
        with self._lock:
            return dict(phase=self._phase, total=self._total, headers=self._headers,
                        samples=self._samples, current=list(self._current))

    def _on_progress(self, kind: str, n: int = 1):
        with self._lock:
            if kind == "plan":
                self._total += n
            elif kind == "header":
                self._headers += n
            else:
                self._samples += n

    def _estimate_folder(self, directory: str, files: List[FileInfo]):
        with self._lock:
            self._current[directory] = len(files)
        try:
            return estimate_files(files, *self._opts, None, lambda: self._cancelled,
                                  32, self._on_progress)
        finally:
            with self._lock:
                self._current.pop(directory, None)

    def run(self):
        by_dir = self._groups

        # Un dossier par tâche : les encodages d'un même dossier restent
        # séquentiels, les dossiers avancent en parallèle
        with ThreadPoolExecutor(max_workers=self._parallel) as pool:
            futures = {
                pool.submit(self._estimate_folder, d, files): d
                for d, files in sorted(by_dir.items())
            }
            for fut in as_completed(futures):
                if self._cancelled:
                    pool.shutdown(wait=False, cancel_futures=True)
                    break
                try:
                    est = fut.result()
                except Exception as e:
                    get_app_logger().warning("Estimation impossible pour %s : %r", futures[fut], e)
                    est = None
                if est is not None:
                    self.group_done.emit(futures[fut], est)
        with self._lock:
            self._phase = "done"
        self.all_done.emit()
