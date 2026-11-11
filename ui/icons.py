"""
Icônes de l'interface : un seul style (trait de 2 px, coins arrondis, grille
24×24), recolorées selon le thème. Tracés d'après Lucide (https://lucide.dev,
licence ISC — voir README).
"""

from PyQt6.QtCore  import QByteArray, QRectF, Qt
from PyQt6.QtGui   import QIcon, QPixmap, QPainter
from PyQt6.QtSvg   import QSvgRenderer

_PATHS = {
    "search":   '<circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/>',
    "refresh":  '<path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8"/><path d="M21 3v5h-5"/>'
                '<path d="M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16"/><path d="M8 16H3v5"/>',
    "folder":   '<path d="m6 14 1.5-2.9A2 2 0 0 1 9.24 10H20a2 2 0 0 1 1.94 2.5l-1.54 6a2 2 0 0 1-1.95 1.5H4'
                'a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h3.9a2 2 0 0 1 1.69.9l.81 1.2a2 2 0 0 0 1.67.9H18a2 2 0 0 1 2 2v2"/>',
    "logs":     '<path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z"/>'
                '<path d="M14 2v4a2 2 0 0 0 2 2h4"/><path d="M16 13H8"/><path d="M16 17H8"/><path d="M10 9H8"/>',
    "settings": '<path d="M20 7h-9"/><path d="M14 17H5"/><circle cx="17" cy="17" r="3"/><circle cx="7" cy="7" r="3"/>',
    "estimate": '<polyline points="22 17 13.5 8.5 8.5 13.5 2 7"/><polyline points="16 17 22 17 22 11"/>',
    "music":    '<path d="M9 18V5l12-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="18" cy="16" r="3"/>',
    "image":    '<rect width="18" height="18" x="3" y="3" rx="2" ry="2"/><circle cx="9" cy="9" r="2"/>'
                '<path d="m21 15-3.086-3.086a2 2 0 0 0-2.828 0L6 21"/>',
    "play":     '<polygon points="6 3 20 12 6 21 6 3"/>',
    "stop":     '<rect width="14" height="14" x="5" y="5" rx="2"/>',
    "pause":    '<rect x="14" y="4" width="4" height="16" rx="1"/><rect x="6" y="4" width="4" height="16" rx="1"/>',
    "check":    '<path d="M20 6 9 17l-5-5"/>',
    "close":    '<path d="M18 6 6 18"/><path d="m6 6 12 12"/>',
    "minimize": '<path d="M5 12h14"/>',
    "maximize": '<rect width="14" height="14" x="5" y="5" rx="2"/>',
    "tag":      '<path d="M12.586 2.586A2 2 0 0 0 11.172 2H4a2 2 0 0 0-2 2v7.172a2 2 0 0 0 .586 1.414l8.704 8.704'
                'a2.426 2.426 0 0 0 3.42 0l6.58-6.58a2.426 2.426 0 0 0 0-3.42z"/><circle cx="7.5" cy="7.5" r="1"/>',
    "trash":    '<path d="M3 6h18"/><path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6"/>'
                '<path d="M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2"/>',
    "open":     '<path d="M15 3h6v6"/><path d="M10 14 21 3"/>'
                '<path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/>',
    "select":   '<path d="m3 17 2 2 4-4"/><path d="m3 7 2 2 4-4"/><path d="M13 6h8"/><path d="M13 12h8"/>'
                '<path d="M13 18h8"/>',
    "expand":   '<path d="m7 15 5 5 5-5"/><path d="m7 9 5-5 5 5"/>',
    "select_all":   '<rect width="18" height="18" x="3" y="3" rx="2"/><path d="m9 12 2 2 4-4"/>',
    "select_none":  '<rect width="18" height="18" x="3" y="3" rx="2"/>',
    "select_some":  '<rect width="18" height="18" x="3" y="3" rx="2"/><path d="M8 12h8"/>',
    "history":  '<path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/><path d="M3 3v5h5"/>'
                '<path d="M12 7v5l4 2"/>',
    "back":     '<path d="m12 19-7-7 7-7"/><path d="M19 12H5"/>',
    "collapse": '<path d="m7 20 5-5 5 5"/><path d="m7 4 5 5 5-5"/>',
}

_cache: dict = {}


def icon(name: str, color: str, px: int = 18) -> QIcon:
    """Icône *name* dessinée dans la couleur *color* (nette jusqu'en 3×)."""
    key = (name, color, px)
    if key in _cache:
        return _cache[key]
    svg = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
           f'stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
           f'{_PATHS[name]}</svg>')
    renderer = QSvgRenderer(QByteArray(svg.encode()))
    ic = QIcon()
    for scale in (1, 2, 3):
        pix = QPixmap(px * scale, px * scale)
        pix.fill(Qt.GlobalColor.transparent)
        p = QPainter(pix)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        renderer.render(p, QRectF(0, 0, px * scale, px * scale))
        p.end()
        pix.setDevicePixelRatio(scale)
        ic.addPixmap(pix)
    _cache[key] = ic
    return ic


# Couleur des icônes selon le rôle du bouton et le thème
PALETTE = {
    "dark":  {"text": "#d6d0ee", "muted": "#a59fc4", "on_accent": "#ffffff"},
    "light": {"text": "#3a2e6e", "muted": "#6a5f94", "on_accent": "#ffffff"},
}
