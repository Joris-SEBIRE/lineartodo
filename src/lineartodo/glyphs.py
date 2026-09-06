"""Glyphes partagés : ceux de Linear, redessinés à ses cotes.

Le menu et la carte affichent les mêmes objets — un état de ticket, une priorité — et doivent
les montrer de la même façon. Ils vivent donc ici, et non dans l'un des deux, qui ne peut pas
importer l'autre sans boucle.

Les formes ne sont pas approchées de mémoire : elles reprennent les tracés que Linear sert dans
son application (grille de 16 pour la priorité, de 14 pour l'état), et sa couleur d'urgence,
convertie depuis la base LCH de sa palette.
"""

from __future__ import annotations

import math

from Cocoa import (
    NSBezierPath,
    NSColor,
    NSImage,
    NSImageSymbolConfiguration,
    NSMakeRect,
    NSMakeSize,
    NSWindingRuleEvenOdd,
)

from .avatars import colour as hex_colour

CHIP = 10.0
# Linear dessine l'état sur une grille de 14 et la priorité sur une grille de 16 : toutes les
# cotes ci-dessous sont exprimées dans ces grilles, puis mises à l'échelle demandée.
STATE_GRID = 14.0
PRIORITY_GRID = 16.0

# Couleurs de priorité. L'orange de l'urgence est celui de Linear (base LCH 66/80/48 → #FF7235) ;
# les trois autres reçoivent une couleur ici, alors que Linear les laisse dans le gris du texte :
# sur une carte, une priorité qui ne se distingue que par le nombre de barres se rate.
PRIORITY_TINTS = {1: "#ff7235", 2: "#f2994a", 3: "#f2c94c", 4: "#8a8f98", 0: "#8a8f98"}
# Barres de Linear : abscisse, ordonnée et hauteur. Linear les décrit dans un repère qui
# descend, AppKit dessine dans un repère qui monte — d'où la conversion, faite ici une fois
# pour toutes : les trois barres reposent sur la même ligne et grandissent vers la droite.
PRIORITY_BARS = ((1.5, 2.0, 6.0), (6.5, 2.0, 9.0), (11.5, 2.0, 12.0))
PRIORITY_DASH = 7.25
PRIORITY_FILLED = {2: 3, 3: 2, 4: 1}
# Une barre non atteinte n'est pas grise : c'est la même couleur, en transparence.
FADED = 0.4

# Couleurs GitHub d'aujourd'hui (Primer), et le glyphe qui va avec chaque état de PR.
PULL_TINTS = {"merged": "#8250df", "open": "#1a7f37", "inreview": "#1a7f37", "draft": "#656d76", "closed": "#d1242f"}
PULL_SYMBOLS = {"merged": "arrow.triangle.merge", "draft": "arrow.triangle.branch", "closed": "xmark"}
PULL_DEFAULT = "arrow.triangle.pull"

# Les glyphes ne changent pas d'une image à l'autre : les refabriquer à chaque geste coûterait
# la moitié du temps de dessin de la carte. Le cache est petit et borné par le vocabulaire.
_CACHE: dict = {}


def symbol(name: str, size: float):
    image = NSImage.imageWithSystemSymbolName_accessibilityDescription_(name, None)
    if image is None:
        return None
    image.setTemplate_(True)
    image.setSize_(NSMakeSize(size, size))
    return image


def tinted(name: str, size: float, tint):
    """Symbole aplati dans une couleur : un gabarit ressortirait noir sur fond sombre.

    Par couleur hiérarchique et non par palette d'une seule couleur : la palette remplit les
    évidements des symboles pleins — mesuré, `checkmark.circle.fill` y perd son crochet et
    devient une pastille muette.
    """
    key = ("tinted", name, size, str(tint))
    if key not in _CACHE:
        glyph = symbol(name, size)
        _CACHE[key] = (
            None
            if glyph is None
            else glyph.imageWithSymbolConfiguration_(
                NSImageSymbolConfiguration.configurationWithHierarchicalColor_(tint)
            )
        )
    return _CACHE[key]


def state(kind: str, colour: str, size: float = CHIP):
    """Le rond d'état de Linear : pointillé, vide, à moitié plein, plein et coché, ou barré.

    La corbeille fait exception : un ticket supprimé n'a pas d'état d'avancement, seulement une
    fin. Elle garde donc sa forme propre, dans le gris que Linear donne à ce qui est clos.
    """
    key = ("state", kind, colour, size)
    if key in _CACHE:
        return _CACHE[key]
    tint = hex_colour(colour) or NSColor.secondaryLabelColor()
    if kind == "trashed":
        return tinted("trash", size, tint)
    unit = size / STATE_GRID
    canvas = NSImage.alloc().initWithSize_(NSMakeSize(size, size))
    middle = size / 2
    canvas.lockFocus()
    tint.setStroke()
    tint.setFill()
    if kind in ("completed", "canceled", "duplicate"):
        NSBezierPath.bezierPathWithOvalInRect_(NSMakeRect(0, 0, size, size)).fill()
        NSColor.whiteColor().setStroke()
        mark = NSBezierPath.bezierPath()
        mark.setLineCapStyle_(1)  # NSLineCapStyleRound, comme Linear
        if kind == "completed":
            mark.setLineWidth_(1.7 * unit)
            mark.moveToPoint_((3.5 * unit, 6.5 * unit))
            mark.lineToPoint_((5.5 * unit, 4.5 * unit))
            mark.lineToPoint_((10.5 * unit, 9.5 * unit))
        else:
            mark.setLineWidth_(1.5 * unit)
            mark.moveToPoint_((5.25 * unit, 5.25 * unit))
            mark.lineToPoint_((8.75 * unit, 8.75 * unit))
            mark.moveToPoint_((8.75 * unit, 5.25 * unit))
            mark.lineToPoint_((5.25 * unit, 8.75 * unit))
        mark.stroke()
    else:
        ring = NSBezierPath.bezierPathWithOvalInRect_(
            NSMakeRect(unit, unit, size - 2 * unit, size - 2 * unit)
        )
        ring.setLineWidth_(1.5 * unit)
        if kind == "backlog":
            # Douze tirets de quinze degrés, séparés d'autant : le pointillé de Linear, qui se
            # lit comme un cercle en attente et non comme un trait haché.
            step = math.pi * 6.0 * unit / 12.0
            ring.setLineWidth_(2.0 * unit)
            ring.setLineDash_count_phase_([step, step], 2, 0.0)
        ring.stroke()
        if kind == "started":
            # Part remplie : Linear la fait croître avec l'avancement, un demi dit « en cours ».
            pie = NSBezierPath.bezierPath()
            pie.moveToPoint_((middle, middle))
            pie.appendBezierPathWithArcWithCenter_radius_startAngle_endAngle_(
                (middle, middle), 3.5 * unit, 90.0, -90.0
            )
            pie.closePath()
            pie.fill()
        elif kind == "triage":
            NSBezierPath.bezierPathWithOvalInRect_(
                NSMakeRect(middle - 1.75 * unit, middle - 1.75 * unit, 3.5 * unit, 3.5 * unit)
            ).fill()
    canvas.unlockFocus()
    _CACHE[key] = canvas
    return canvas


def priority_tint(level: int):
    return hex_colour(PRIORITY_TINTS.get(level, "#8a8f98")) or NSColor.secondaryLabelColor()


def priority(level: int, size: float = 12.0):
    """Les barres de priorité de Linear : trois barres, une à trois pleines, ou le carré urgent.

    Rien dans SF Symbols ne sait dire « deux barres sur trois » — les jeux de barres qui s'en
    approchent en ont quatre, ou d'autres proportions — donc on les trace, aux cotes de Linear.
    """
    key = ("priority", level, size)
    if key in _CACHE:
        return _CACHE[key]
    unit = size / PRIORITY_GRID
    tint = priority_tint(level)
    canvas = NSImage.alloc().initWithSize_(NSMakeSize(size, size))
    canvas.lockFocus()
    if level == 1:
        # Le point d'exclamation est creusé, pas peint : c'est ainsi que Linear le dessine, et
        # le glyphe reste lisible sur n'importe quel fond. Un seul chemin, règle pair-impair :
        # les formes intérieures deviennent des trous.
        square = NSBezierPath.bezierPath()
        square.appendBezierPathWithRoundedRect_xRadius_yRadius_(
            NSMakeRect(unit, unit, 14 * unit, 14 * unit), 2 * unit, 2 * unit
        )
        square.appendBezierPathWithRect_(NSMakeRect(7 * unit, 7 * unit, 2 * unit, 5 * unit))
        square.appendBezierPathWithOvalInRect_(NSMakeRect(7 * unit, 4 * unit, 2 * unit, 2 * unit))
        square.setWindingRule_(NSWindingRuleEvenOdd)
        tint.setFill()
        square.fill()
    elif level == 0:
        # Trois tirets : sans priorité, la colonne garde sa place au lieu de disparaître.
        tint.colorWithAlphaComponent_(0.9).setFill()
        for x, _, _ in PRIORITY_BARS:
            NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
                NSMakeRect(x * unit, PRIORITY_DASH * unit, 3 * unit, 1.5 * unit), 0.5 * unit, 0.5 * unit
            ).fill()
    else:
        filled = PRIORITY_FILLED.get(level, 0)
        for index, (x, y, height) in enumerate(PRIORITY_BARS):
            (tint if index < filled else tint.colorWithAlphaComponent_(FADED)).setFill()
            NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
                NSMakeRect(x * unit, y * unit, 3 * unit, height * unit), unit, unit
            ).fill()
    canvas.unlockFocus()
    _CACHE[key] = canvas
    return canvas


def pull_tint(status: str):
    return hex_colour(PULL_TINTS.get((status or "").lower(), "#656d76")) or NSColor.secondaryLabelColor()


def pull(status: str, size: float, tint=None):
    """Le glyphe d'une PR, distinct par état : fusionnée, brouillon, fermée, ou ouverte."""
    return tinted(PULL_SYMBOLS.get((status or "").lower(), PULL_DEFAULT), size, tint or pull_tint(status))
