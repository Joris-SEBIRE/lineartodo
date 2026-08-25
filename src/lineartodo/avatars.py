"""Visages : téléchargement en tâche de fond, cache disque, rendu circulaire.

Deux espèces de visage, la même plomberie : une URL d'image, ou une pastille d'initiales
dessinée localement quand le compte Linear n'a pas de photo — ce qui est le cas le plus
fréquent. Les initiales et la couleur viennent de Linear : `initials:JS:#5e6ad2`.
"""

from __future__ import annotations

import hashlib
import time
import urllib.error
import urllib.request
from pathlib import Path

from Cocoa import (
    NSAttributedString,
    NSBezierPath,
    NSColor,
    NSCompositingOperationSourceOver,
    NSFont,
    NSFontAttributeName,
    NSFontWeightSemibold,
    NSForegroundColorAttributeName,
    NSImage,
    NSMakeRect,
    NSMakeSize,
    NSZeroRect,
)

CACHE_DIR = Path.home() / "Library" / "Caches" / "LinearTodo" / "avatars"
MAX_AGE = 14 * 86400
SIZE = 22.0
# Barre des menus : 22 pt de haut, une icône de 18 pt y est centrée confortablement.
BAR_SIZE = 18.0
INITIALS = "initials:"
# Les initiales occupent un peu moins de la moitié du disque : au-delà elles touchent le bord.
INITIALS_RATIO = 0.42


def _colour(hexa: str):
    """Couleur Linear (`#5e6ad2`) en NSColor, gris moyen si la chaîne n'est pas lisible."""
    raw = (hexa or "").lstrip("#")
    if len(raw) != 6:
        return NSColor.systemGrayColor()
    try:
        red, green, blue = (int(raw[index : index + 2], 16) / 255.0 for index in (0, 2, 4))
    except ValueError:
        return NSColor.systemGrayColor()
    return NSColor.colorWithSRGBRed_green_blue_alpha_(red, green, blue, 1.0)


class Avatars:
    """Le téléchargement se fait depuis le thread de fetch, le rendu depuis le thread UI."""

    def __init__(self) -> None:
        self.rendered: dict[tuple[str, float], object] = {}

    def path_for(self, url: str) -> Path:
        return CACHE_DIR / (hashlib.sha1(url.encode()).hexdigest()[:16] + ".img")

    def prefetch(self, urls: set[str]) -> None:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        for url in urls:
            if not url.startswith("http"):
                continue  # une pastille d'initiales se dessine, elle ne se télécharge pas
            target = self.path_for(url)
            if target.exists() and (time.time() - target.stat().st_mtime) < MAX_AGE:
                continue
            try:
                request = urllib.request.Request(url, headers={"User-Agent": "LinearTodo"})
                with urllib.request.urlopen(request, timeout=10) as response:
                    data = response.read()
            except (urllib.error.URLError, OSError, ValueError):
                continue
            if not data:
                continue
            temporary = target.with_suffix(".part")
            temporary.write_bytes(data)
            temporary.replace(target)
            for key in [k for k in self.rendered if k[0] == url]:
                del self.rendered[key]

    def image(self, face: str, size: float = SIZE):
        """Visage rond, ou None si une photo n'est pas encore en cache."""
        if not face:
            return None
        if (face, size) in self.rendered:
            return self.rendered[(face, size)]
        drawn = self._initials(face, size) if face.startswith(INITIALS) else self._photo(face, size)
        if drawn is None:
            return None
        self.rendered[(face, size)] = drawn
        return drawn

    def _photo(self, url: str, size: float):
        source = NSImage.alloc().initWithContentsOfFile_(str(self.path_for(url)))
        if source is None:
            return None
        box = NSMakeRect(0, 0, size, size)
        circle = NSImage.alloc().initWithSize_(NSMakeSize(size, size))
        circle.lockFocus()
        NSBezierPath.bezierPathWithOvalInRect_(box).addClip()
        source.drawInRect_fromRect_operation_fraction_(box, NSZeroRect, NSCompositingOperationSourceOver, 1.0)
        circle.unlockFocus()
        return circle

    def _initials(self, face: str, size: float):
        _, _, rest = face.partition(INITIALS)
        letters, _, tint = rest.partition(":")
        glyph = NSAttributedString.alloc().initWithString_attributes_(
            letters or "?",
            {
                NSFontAttributeName: NSFont.systemFontOfSize_weight_(size * INITIALS_RATIO, NSFontWeightSemibold),
                NSForegroundColorAttributeName: NSColor.whiteColor(),
            },
        )
        span = glyph.size()
        canvas = NSImage.alloc().initWithSize_(NSMakeSize(size, size))
        canvas.lockFocus()
        _colour(tint).setFill()
        NSBezierPath.bezierPathWithOvalInRect_(NSMakeRect(0, 0, size, size)).fill()
        glyph.drawAtPoint_(((size - span.width) / 2, (size - span.height) / 2))
        canvas.unlockFocus()
        return canvas
