"""
Pool de processus pour l'encodage des images.

Pillow garde le verrou global de Python (GIL) pendant une bonne partie de
l'encodage : avec des threads, la conversion plafonnait à ~1,5 cœur quel que
soit le nombre de threads. Chaque encodage part donc dans un processus séparé ;
les threads des ConversionThread / estimations ne font plus qu'attendre.

Le pool est partagé, créé à la première utilisation et fermé une minute après
la dernière tâche (pour ne pas garder des dizaines de processus en mémoire).
Les processus tournent en priorité « inférieure à la normale » : le PC reste
fluide même quand tous les cœurs sont occupés.
"""

import os
import threading
from concurrent.futures import ProcessPoolExecutor
from concurrent.futures.process import BrokenProcessPool

from core.image_codec import encode_image, encoded_size

IDLE_SHUTDOWN_S = 60

_lock    = threading.Lock()
_pool: ProcessPoolExecutor = None
_size    = 0
_users   = 0
_timer: threading.Timer = None


def worker_count(parallel: int = 0) -> int:
    """*parallel* > 0 : valeur imposée ; 0 = automatique (tous les cœurs sauf un)."""
    if parallel and parallel > 0:
        return parallel
    return max(1, (os.cpu_count() or 4) - 1)


def _init_worker():
    try:
        import ctypes
        BELOW_NORMAL_PRIORITY_CLASS = 0x4000
        SYNCHRONIZE = 0x00100000
        k32 = ctypes.windll.kernel32
        k32.SetPriorityClass(k32.GetCurrentProcess(), BELOW_NORMAL_PRIORITY_CLASS)
        # Si l'application plante ou est tuée, ses processus d'encodage ne
        # sont pas prévenus et resteraient en mémoire : chacun surveille
        # l'application et s'arrête dès qu'elle disparaît
        parent = k32.OpenProcess(SYNCHRONIZE, False, os.getppid())
        if parent:
            def watch():
                k32.WaitForSingleObject(parent, 0xFFFFFFFF)
                os._exit(0)
            threading.Thread(target=watch, daemon=True).start()
    except Exception:
        pass


def _shutdown_locked():
    global _pool, _size
    if _pool is not None:
        _pool.shutdown(wait=False, cancel_futures=True)
    _pool, _size = None, 0


def _idle_shutdown():
    with _lock:
        if _users == 0:
            _shutdown_locked()


def acquire(n: int):
    """Réserve le pool (taille *n*) pour une tâche ; à libérer avec release()."""
    global _pool, _size, _users, _timer
    with _lock:
        _users += 1
        if _timer is not None:
            _timer.cancel()
            _timer = None
        if _pool is None or (_size < n and _users == 1):
            _shutdown_locked()
            _pool = ProcessPoolExecutor(max_workers=n, initializer=_init_worker)
            _size = n


def release():
    global _users, _timer
    with _lock:
        _users = max(0, _users - 1)
        if _users == 0:
            _timer = threading.Timer(IDLE_SHUTDOWN_S, _idle_shutdown)
            _timer.daemon = True
            _timer.start()


def shutdown():
    """Fermeture de l'application."""
    global _timer
    with _lock:
        if _timer is not None:
            _timer.cancel()
            _timer = None
        _shutdown_locked()


def _run(fn, *args):
    for attempt in (0, 1):
        with _lock:
            pool = _pool
            if pool is None:            # utilisation hors acquire() : pool à la demande
                _init_pool_locked()
                pool = _pool
        try:
            return pool.submit(fn, *args).result()
        except BrokenProcessPool:
            # Un processus a été tué (mémoire saturée…) : nouveau pool, un essai de plus
            with _lock:
                if _pool is pool:
                    n = _size
                    _shutdown_locked()
                    _init_pool_locked(n)
            if attempt:
                raise RuntimeError("le processus d'encodage s'est arrêté brutalement")


def _init_pool_locked(n: int = 0):
    global _pool, _size
    _size = n or worker_count()
    _pool = ProcessPoolExecutor(max_workers=_size, initializer=_init_worker)


def encode(path, out_fmt, quality, max_side=0) -> bytes:
    return _run(encode_image, path, out_fmt, quality, max_side)


def size(path, out_fmt, quality, max_side=0) -> int:
    return _run(encoded_size, path, out_fmt, quality, max_side)
