"""Carte des tickets : la fenêtre, son canevas, et les gestes pour s'y déplacer.

Le canevas ne fabrique aucune sous-vue : deux cents cartes seraient deux cents vues à poser et
à bouger à chaque geste. Il dessine la scène calculée par `graph` dans son propre repère et
convertit lui-même les points — et c'est ce même calcul qui dit ce qui est sorti du cadre, donc
où poser les pastilles de comptage sur les bords.

Tout ce qui se voit vient de Linear quand Linear le donne : la couleur et le glyphe d'un état,
la couleur et le glyphe d'une priorité, le nom et la couleur d'une étiquette. La carte n'invente
un signe que là où Linear n'en a pas.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone

import objc
from Cocoa import (
    NSAffineTransform,
    NSAppearanceNameAqua,
    NSAppearanceNameDarkAqua,
    NSAttributedString,
    NSBackingStoreBuffered,
    NSBezierPath,
    NSBox,
    NSBoxCustom,
    NSColor,
    NSCompositingOperationSourceOver,
    NSCursor,
    NSEventModifierFlagCommand,
    NSFont,
    NSFontAttributeName,
    NSFontWeightBold,
    NSFontWeightMedium,
    NSFontWeightRegular,
    NSFontWeightSemibold,
    NSForegroundColorAttributeName,
    NSGraphicsContext,
    NSLineBreakByTruncatingTail,
    NSMakePoint,
    NSMakeRect,
    NSMakeSize,
    NSMutableParagraphStyle,
    NSObject,
    NSParagraphStyleAttributeName,
    NSTextAlignmentCenter,
    NSTextField,
    NSTrackingActiveInKeyWindow,
    NSTrackingArea,
    NSTrackingInVisibleRect,
    NSTrackingMouseEnteredAndExited,
    NSTrackingMouseMoved,
    NSView,
    NSViewHeightSizable,
    NSViewMaxYMargin,
    NSViewMinYMargin,
    NSViewWidthSizable,
    NSWindow,
    NSWindowStyleMaskClosable,
    NSWindowStyleMaskMiniaturizable,
    NSWindowStyleMaskResizable,
    NSWindowStyleMaskTitled,
    NSWorkspace,
    NSZeroRect,
)
from Foundation import NSURL

from . import IDENTITY_TINT
from .avatars import colour as hex_colour
from .formatting import since
from .glyphs import (
    priority as priority_glyph,
    priority_tint,
    pull as pull_glyph,
    pull_tint,
    state as state_glyph,
    tinted as tinted_symbol,
)
from .graph import PRIORITY_LABEL, draw_map

BAR_HEIGHT = 34.0
BAR_INSET = 16.0
# Bornes du zoom : en dessous rien n'est lisible, au-dessus on ne voit qu'une carte.
ZOOM_MIN, ZOOM_MAX = 0.2, 2.0
ZOOM_STEP = 1.18
# Pastilles de bord : leur marge au bord, et la distance en deçà de laquelle deux sorties de
# cartes voisines n'en font qu'une.
EDGE_INSET = 18.0
CLUSTER_GAP = 74.0
BUBBLE_HEIGHT = 24.0
BUBBLE_PAD = 8.0
BUBBLE_GLYPH = 9.0
# Le chevron pointe vers l'extérieur, du côté où la pastille touche le bord.
BUBBLE_ARROWS = {"gauche": "chevron.left", "droite": "chevron.right", "haut": "chevron.up", "bas": "chevron.down"}
CORNER = 12.0
# Marge de sécurité autour du cadre : ce qui la touche est dessiné, le reste est laissé de côté.
CULL = 320.0
# En deçà de cette échelle, le titre d'une carte tombe sous quatre points : illisible, et payé
# quand même. On ne garde alors que la forme, le filet de type et le numéro. Le seuil est sous le
# cadrage d'ouverture d'une carte ordinaire, pour qu'on ne tombe jamais dessus en arrivant.
DETAIL = 0.24
# En deçà, une carte n'est plus lisible : on ouvre alors sur le haut du plan plutôt que de tout
# faire tenir dans la fenêtre.
READABLE = 0.45
# Déplacement à la souris : en deçà de ce mouvement, un clic reste un clic.
DRAG_SLOP = 3.0
# Distance à laquelle une flèche se laisse désigner : un trait d'un point et demi ne se vise pas.
ROUTE_REACH = 6.0
# Touches fléchées, telles que macOS les envoie, et le sens du déplacement qu'elles commandent.
ARROWS = {"": (0.0, -1.0), "": (0.0, 1.0), "": (-1.0, 0.0), "": (1.0, 0.0)}

# Gélules : hauteur, marge intérieure, écart entre deux, et taille du glyphe qu'elles portent.
CHIP_HEIGHT = 18.0
CHIP_PAD = 7.0
CHIP_GAP = 6.0
CHIP_GLYPH = 11.0
TYPE_BAND = 5.0
AVATAR_HEAD = 17.0
AVATAR_FOOT = 19.0

# Âge d'un ticket : trois paliers, et une couleur qui glisse de l'un à l'autre. Une semaine,
# c'est un ticket de la semaine ; un mois, il traîne ; trois mois, il est en train de mourir.
# Paliers du temps depuis le dernier mouvement, et la teinte de chacun, en clair puis en sombre.
AGE_STOPS = (
    (1.0, ("#717171", "#9e9e9e")),
    (3.0, ("#7a6a4e", "#b0a184")),
    (7.0, ("#8a6234", "#c79463")),
    (30.0, ("#a83c2c", "#e07a63")),
    (90.0, ("#d40924", "#ff635f")),
)
_DYNAMIC: dict = {}

# Ce que dit le bandeau du bas, dans l'ordre de lecture : les trois familles de flèche, puis ce
# que porte le filet de gauche d'une carte. Les couleurs se résolvent au dessin, pour suivre le
# thème.
_LEGEND = (
    ("trait", "parent → enfant", NSColor.tertiaryLabelColor, None),
    ("trait", "projet → ticket", NSColor.secondaryLabelColor, [7.0, 5.0]),
    ("trait", "bloque", NSColor.systemRedColor, [4.0, 4.0]),
    ("filet", "bug", NSColor.systemRedColor, None),
    ("gélule", "autonome : rien ne l'attend", NSColor.systemGreenColor, None),
    ("gélule", "bloqué : il attend un autre ticket", NSColor.systemRedColor, None),
    ("trait", "documente", lambda: hex_colour(PAPER_TINT), [2.0, 3.0]),
)

# Couleur des documents : l'indigo de Linear, celui de sa marque.
PAPER_TINT = "#5e6ad2"

ROUTE_STYLE = {
    # famille : (épaisseur, pointillés, teinte, tête de flèche)
    "parent": (1.7, None, "tertiaryLabelColor", True),
    "projet": (1.5, [7.0, 5.0], "", True),
    "bloque": (1.5, [4.0, 4.0], "systemRedColor", True),
    "document": (1.4, [2.0, 3.0], "", True),
}


def _font(size: float, weight=NSFontWeightRegular):
    return NSFont.systemFontOfSize_weight_(size, weight)


def _mono(size: float, weight=NSFontWeightSemibold):
    return NSFont.monospacedSystemFontOfSize_weight_(size, weight)


def _style(centre: bool = False):
    style = NSMutableParagraphStyle.alloc().init()
    style.setLineBreakMode_(NSLineBreakByTruncatingTail)
    if centre:
        style.setAlignment_(NSTextAlignmentCenter)
    return style


def _write(text: str, font, tint, box, centre: bool = False) -> None:
    """Écrit une ligne, centrée dans la hauteur de son rectangle.

    Une chaîne dessinée dans un rectangle part du haut de ce rectangle : pour la centrer, on
    lui donne un rectangle de la hauteur exacte d'une ligne, posé au milieu. Le décalage
    approximatif d'avant se voyait sur toutes les gélules.
    """
    # Centrage sur la hauteur des capitales, pas sur celle de la ligne : la ligne réserve la
    # place des jambages, si bien qu'un texte qui n'en a pas — « +7 », « Haute » — se poserait
    # visiblement trop haut. L'ascendante est le bon repère ici : mesurée contre la ligne de
    # base du gestionnaire de mise en page, elle place l'encre à un demi-point près, l'autre à
    # deux points.
    cap = font.capHeight()
    height = font.ascender() - font.descender()
    top = box.origin.y + (box.size.height - cap) / 2 - (font.ascender() - cap)
    middle = NSMakeRect(box.origin.x, top, box.size.width, height + 1.0)
    NSAttributedString.alloc().initWithString_attributes_(
        text,
        {
            NSFontAttributeName: font,
            NSForegroundColorAttributeName: tint,
            NSParagraphStyleAttributeName: _style(centre),
        },
    ).drawInRect_(middle)


def _width(text: str, font) -> float:
    return NSAttributedString.alloc().initWithString_attributes_(text, {NSFontAttributeName: font}).size().width


def _lines(text: str, font, width: float, count: int) -> list:
    """Découpe un titre en au plus `count` lignes à la largeur donnée.

    Ce qui déborde n'est pas coupé ici : la dernière ligne reçoit le reste, et c'est le style de
    paragraphe qui pose les points de suspension, à la largeur réelle du rendu.
    """
    words, lines, current = (text or "").split(), [], ""
    for index, word in enumerate(words):
        candidate = f"{current} {word}".strip()
        if current and _width(candidate, font) > width:
            if len(lines) + 1 == count:
                return [*lines, " ".join(words[index - len(current.split()):])]
            lines.append(current)
            current = word
        else:
            current = candidate
    return [*lines, current] if current else lines


def _image(glyph, box) -> None:
    glyph.drawInRect_fromRect_operation_fraction_respectFlipped_hints_(
        box, NSZeroRect, NSCompositingOperationSourceOver, 1.0, True, None
    )


def _chip_width(text: str, font, glyph: bool) -> float:
    return _width(text, font) + 2 * CHIP_PAD + (CHIP_GLYPH + 4.0 if glyph else 0.0)


def _chip(x: float, y: float, text: str, tint, glyph=None, font=None, filled: bool = True,
          strong: bool = False) -> float:
    """Une gélule : fond teinté, glyphe optionnel, texte centré. Rend sa largeur.

    `strong` la désigne sous le pointeur : le fond s'affirme et un liseré paraît, pour dire
    qu'elle se clique — c'est le cas des PR, qui mènent à GitHub et non au ticket.
    """
    font = font or _font(10.5, NSFontWeightSemibold)
    width = _chip_width(text, font, glyph is not None)
    box = NSMakeRect(x, y, width, CHIP_HEIGHT)
    if filled:
        shape = NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(box, CHIP_HEIGHT / 2, CHIP_HEIGHT / 2)
        tint.colorWithAlphaComponent_(0.3 if strong else 0.15).setFill()
        shape.fill()
        if strong:
            tint.setStroke()
            shape.setLineWidth_(1.0)
            shape.stroke()
    cursor = x + CHIP_PAD
    if glyph is not None:
        _image(glyph, NSMakeRect(cursor, y + (CHIP_HEIGHT - CHIP_GLYPH) / 2, CHIP_GLYPH, CHIP_GLYPH))
        cursor += CHIP_GLYPH + 4.0
    _write(text, font, tint, NSMakeRect(cursor, y, width - (cursor - x) - CHIP_PAD, CHIP_HEIGHT))
    return width


def _dynamic(light: str, dark: str):
    """Couleur qui suit le thème : deux teintes, résolues au dessin par AppKit."""
    key = (light, dark)
    if key not in _DYNAMIC:
        def resolve(appearance):
            sombre = appearance.bestMatchFromAppearancesWithNames_(
                [NSAppearanceNameAqua, NSAppearanceNameDarkAqua]
            ) == NSAppearanceNameDarkAqua
            return hex_colour(dark if sombre else light) or NSColor.secondaryLabelColor()

        _DYNAMIC[key] = NSColor.colorWithName_dynamicProvider_(f"age{light}{dark}", resolve)
    return _DYNAMIC[key]


def _age_tint(moment):
    """Couleur du temps passé depuis le dernier mouvement du ticket.

    Cinq paliers : le jour, trois jours, la semaine, le mois, le trimestre. C'est l'échelle à
    laquelle un ticket change de nature — celui d'aujourd'hui, celui de la semaine, celui qui
    traîne, celui qu'on ne fera peut-être jamais. Entre deux paliers la couleur glisse, et les
    teintes gardent un contraste voisin de 5 sur le fond d'une carte, dans les deux thèmes.
    """
    if moment is None:
        return NSColor.tertiaryLabelColor()
    days = max(0.0, (datetime.now(timezone.utc) - moment).total_seconds() / 86400.0)
    stops = AGE_STOPS
    if days <= stops[0][0]:
        return _dynamic(*stops[0][1])
    if days >= stops[-1][0]:
        return _dynamic(*stops[-1][1])
    for (low, start), (high, end) in zip(stops, stops[1:]):
        if days <= high:
            part = (days - low) / (high - low)
            return _dynamic(_blend(start[0], end[0], part), _blend(start[1], end[1], part))
    return _dynamic(*stops[-1][1])


def _blend(first: str, second: str, part: float) -> str:
    """Mélange de deux couleurs en hexadécimal, composante par composante."""
    a = [int(first.lstrip("#")[index: index + 2], 16) for index in (0, 2, 4)]
    b = [int(second.lstrip("#")[index: index + 2], 16) for index in (0, 2, 4)]
    return "#" + "".join(f"{round(x + (y - x) * part):02x}" for x, y in zip(a, b))


def _slate():
    """Le gris des pastilles neutres : lisible sur le fond du plan, dans les deux thèmes."""
    return _dynamic("#6b7280", "#9aa2ad")


def _polyline(points, radius: float = 12.0):
    """Ligne brisée aux angles arrondis : les coudes se suivent sans casser l'œil."""
    path = NSBezierPath.bezierPath()
    path.moveToPoint_(NSMakePoint(*points[0]))
    for corner, after in zip(points[1:-1], points[2:]):
        path.appendBezierPathWithArcFromPoint_toPoint_radius_(
            NSMakePoint(*corner), NSMakePoint(*after), radius
        )
    path.lineToPoint_(NSMakePoint(*points[-1]))
    return path


def _arrow_head(point, direction, tint, size: float = 8.0) -> None:
    """Pointe de flèche à l'arrivée, orientée par le dernier segment parcouru."""
    length = math.hypot(*direction) or 1.0
    ux, uy = direction[0] / length, direction[1] / length
    back = (point[0] - ux * size, point[1] - uy * size)
    path = NSBezierPath.bezierPath()
    path.moveToPoint_(NSMakePoint(*point))
    path.lineToPoint_(NSMakePoint(back[0] - uy * size * 0.45, back[1] + ux * size * 0.45))
    path.lineToPoint_(NSMakePoint(back[0] + uy * size * 0.45, back[1] - ux * size * 0.45))
    path.closePath()
    tint.setFill()
    path.fill()


class Canvas(NSView):
    """La carte elle-même : elle dessine la scène et porte le déplacement et le zoom."""

    def initWithFrame_(self, frame):
        self = objc.super(Canvas, self).initWithFrame_(frame)
        if self is None:
            return None
        self.scene = None
        self.avatars = None
        self.origin = (0.0, 0.0)
        self.scale = 1.0
        self.dragging = None
        self.moved = 0.0
        self.bubbles = []
        self.framed = False
        # Ce que le pointeur désigne : la carte sous lui, les cartes qu'elle touche, et sa
        # position, pour l'infobulle.
        self.hovered = ""
        self.related = set()
        self.pointer = None
        # Zones cliquables posées à l'intérieur des cartes (les PR), et la flèche désignée.
        self.zones = []
        self.route = None
        return self

    def isFlipped(self):
        return True

    def acceptsFirstResponder(self):
        return True

    @objc.python_method
    def show(self, scene, avatars) -> None:
        """Nouvelle scène. Le cadrage n'est refait qu'à la première : on ne bouge pas la vue
        sous les yeux de quelqu'un qui la parcourt."""
        self.scene, self.avatars = scene, avatars
        if not self.framed:
            self.frame_all()
            self.framed = True
        self.setNeedsDisplay_(True)

    @objc.python_method
    def frame_all(self) -> None:
        """Cadre toute la scène, sans grossir au-delà de la taille naturelle."""
        if self.scene is None:
            return
        left, top, width, height = self.scene.bounds
        view = self.bounds().size
        if width <= 0 or height <= 0 or view.width <= 0:
            return
        fit = min(view.width / width, view.height / height)
        if fit < READABLE:
            # Tout faire tenir donnerait des cartes illisibles : on ouvre à une taille où le
            # titre se lit, en haut du plan, et ce qui dépasse se compte sur les bords.
            self.scale = READABLE
            self.origin = (left + max(0.0, (width - view.width / self.scale) / 2), top)
            return
        self.scale = max(ZOOM_MIN, min(1.0, fit))
        self.origin = (
            left - (view.width / self.scale - width) / 2,
            top - (view.height / self.scale - height) / 2,
        )

    @objc.python_method
    def to_view(self, x: float, y: float) -> tuple:
        return ((x - self.origin[0]) * self.scale, (y - self.origin[1]) * self.scale)

    @objc.python_method
    def to_scene(self, x: float, y: float) -> tuple:
        return (self.origin[0] + x / self.scale, self.origin[1] + y / self.scale)

    @objc.python_method
    def window_in_scene(self) -> tuple:
        size = self.bounds().size
        return (self.origin[0], self.origin[1], size.width / self.scale, size.height / self.scale)

    @objc.python_method
    def zoom(self, factor: float, around=None) -> None:
        """Zoom autour d'un point de la vue : ce qui est sous le curseur y reste."""
        size = self.bounds().size
        pivot = around or (size.width / 2, size.height / 2)
        before = self.to_scene(*pivot)
        self.scale = max(ZOOM_MIN, min(ZOOM_MAX, self.scale * factor))
        after = self.to_scene(*pivot)
        self.origin = (self.origin[0] + before[0] - after[0], self.origin[1] + before[1] - after[1])
        self.setNeedsDisplay_(True)

    @objc.python_method
    def card_at(self, x: float, y: float):
        px, py = self.to_scene(x, y)
        for card in reversed(self.scene.cards if self.scene else []):
            if card.x <= px <= card.x + card.width and card.y <= py <= card.y + card.height:
                return card
        return None

    def updateTrackingAreas(self):
        """Zone de suivi du pointeur, refaite à chaque redimensionnement."""
        for area in self.trackingAreas():
            self.removeTrackingArea_(area)
        self.addTrackingArea_(
            NSTrackingArea.alloc().initWithRect_options_owner_userInfo_(
                self.bounds(),
                NSTrackingMouseEnteredAndExited | NSTrackingMouseMoved | NSTrackingActiveInKeyWindow
                | NSTrackingInVisibleRect,
                self,
                None,
            )
        )
        objc.super(Canvas, self).updateTrackingAreas()

    def mouseMoved_(self, event):
        point = self.convertPoint_fromView_(event.locationInWindow(), None)
        self.pointer = (point.x, point.y)
        card = self.card_at(point.x, point.y)
        over = self.bubble_at(point.x, point.y) is not None or self.zone_at(point.x, point.y) is not None
        key = card.key if card is not None else ""
        if key != self.hovered:
            self.hovered = key
            self.related = self.neighbours(key)
        self.route = None if card is not None else self.route_at(point.x, point.y)
        if self.route is not None:
            self.related = {self.route.source, self.route.target}
        (NSCursor.pointingHandCursor() if (card is not None or over) else NSCursor.openHandCursor()).set()
        self.setNeedsDisplay_(True)

    @objc.python_method
    def route_at(self, x: float, y: float):
        """La flèche sous le pointeur, s'il en frôle une : on cherche à la distance d'un doigt."""
        if self.scene is None:
            return None
        px, py = self.to_scene(x, y)
        reach = ROUTE_REACH / self.scale
        for route in self.scene.routes:
            box = route.box
            if not (box[0] - reach <= px <= box[2] + reach and box[1] - reach <= py <= box[3] + reach):
                continue
            for first, second in zip(route.points, route.points[1:]):
                if first[0] == second[0]:
                    near = abs(px - first[0]) <= reach and min(first[1], second[1]) - reach <= py <= max(first[1], second[1]) + reach
                else:
                    near = abs(py - first[1]) <= reach and min(first[0], second[0]) - reach <= px <= max(first[0], second[0]) + reach
                if near:
                    return route
        return None

    @objc.python_method
    def zone_at(self, x: float, y: float):
        px, py = self.to_scene(x, y)
        for box, url, _ in self.zones:
            if (box.origin.x <= px <= box.origin.x + box.size.width
                    and box.origin.y <= py <= box.origin.y + box.size.height):
                return url
        return None

    @objc.python_method
    def zone_under(self, box) -> bool:
        """Le pointeur est-il sur cette gélule ? Les zones sont en coordonnées de la scène."""
        if self.pointer is None:
            return False
        px, py = self.to_scene(*self.pointer)
        return (box.origin.x <= px <= box.origin.x + box.size.width
                and box.origin.y <= py <= box.origin.y + box.size.height)

    def mouseExited_(self, event):
        self.hovered, self.related, self.pointer, self.route = "", set(), None, None
        NSCursor.arrowCursor().set()
        self.setNeedsDisplay_(True)

    @objc.python_method
    def neighbours(self, key: str) -> set:
        """Cartes reliées à celle-ci, quel que soit le sens du lien."""
        if not key or self.scene is None:
            return set()
        return {
            other
            for link in self.scene.links
            for other in ((link.target,) if link.source == key else (link.source,) if link.target == key else ())
        }

    @objc.python_method
    def bubble_at(self, x: float, y: float):
        for box, keys in self.bubbles:
            if (box.origin.x <= x <= box.origin.x + box.size.width
                    and box.origin.y <= y <= box.origin.y + box.size.height):
                return keys
        return None

    def mouseDown_(self, event):
        point = self.convertPoint_fromView_(event.locationInWindow(), None)
        self.dragging = (point.x, point.y)
        self.moved = 0.0
        NSCursor.closedHandCursor().set()

    def mouseDragged_(self, event):
        if self.dragging is None:
            return
        point = self.convertPoint_fromView_(event.locationInWindow(), None)
        dx, dy = point.x - self.dragging[0], point.y - self.dragging[1]
        self.moved += abs(dx) + abs(dy)
        self.origin = (self.origin[0] - dx / self.scale, self.origin[1] - dy / self.scale)
        self.dragging = (point.x, point.y)
        self.setNeedsDisplay_(True)

    def mouseUp_(self, event):
        point = self.convertPoint_fromView_(event.locationInWindow(), None)
        held = self.moved
        self.dragging = None
        card = self.card_at(point.x, point.y)
        (NSCursor.pointingHandCursor() if card is not None else NSCursor.openHandCursor()).set()
        if held > DRAG_SLOP:
            return
        keys = self.bubble_at(point.x, point.y)
        if keys is not None:
            self.reach(keys)
            return
        url = self.zone_at(point.x, point.y)
        if url:
            NSWorkspace.sharedWorkspace().openURL_(NSURL.URLWithString_(url))
            return
        if card is not None and card.url:
            NSWorkspace.sharedWorkspace().openURL_(NSURL.URLWithString_(card.url))

    @objc.python_method
    def reach(self, keys) -> None:
        """Amène au centre le groupe de cartes que la pastille annonce."""
        cards = [card for card in self.scene.cards if card.key in keys]
        if not cards:
            return
        middle = (
            sum(card.middle[0] for card in cards) / len(cards),
            sum(card.middle[1] for card in cards) / len(cards),
        )
        size = self.bounds().size
        self.origin = (middle[0] - size.width / self.scale / 2, middle[1] - size.height / self.scale / 2)
        self.setNeedsDisplay_(True)

    def scrollWheel_(self, event):
        if event.modifierFlags() & NSEventModifierFlagCommand:
            point = self.convertPoint_fromView_(event.locationInWindow(), None)
            self.zoom(ZOOM_STEP if event.scrollingDeltaY() > 0 else 1 / ZOOM_STEP, (point.x, point.y))
            return
        self.origin = (
            self.origin[0] - event.scrollingDeltaX() / self.scale,
            self.origin[1] - event.scrollingDeltaY() / self.scale,
        )
        self.setNeedsDisplay_(True)

    def magnifyWithEvent_(self, event):
        point = self.convertPoint_fromView_(event.locationInWindow(), None)
        self.zoom(1.0 + event.magnification(), (point.x, point.y))

    def keyDown_(self, event):
        key = (event.charactersIgnoringModifiers() or "").lower()
        step = 90.0 / self.scale
        if key in ("+", "="):
            self.zoom(ZOOM_STEP)
        elif key == "-":
            self.zoom(1 / ZOOM_STEP)
        elif key == "0":
            self.frame_all()
            self.setNeedsDisplay_(True)
        elif key in ARROWS:
            dx, dy = (value * step for value in ARROWS[key])
            self.origin = (self.origin[0] + dx, self.origin[1] + dy)
            self.setNeedsDisplay_(True)
        else:
            objc.super(Canvas, self).keyDown_(event)

    def drawRect_(self, rect):
        NSColor.windowBackgroundColor().setFill()
        NSBezierPath.fillRect_(self.bounds())
        if self.scene is None or not self.scene.cards:
            size = self.bounds().size
            _write(
                "aucun ticket assigné pour l'instant" if self.scene else "lecture en cours…",
                _font(13.0, NSFontWeightMedium),
                NSColor.tertiaryLabelColor(),
                NSMakeRect(0.0, size.height / 2 - 10.0, size.width, 20.0),
                centre=True,
            )
            return
        self.zones = []
        NSGraphicsContext.saveGraphicsState()
        transform = NSAffineTransform.transform()
        transform.scaleBy_(self.scale)
        transform.translateXBy_yBy_(-self.origin[0], -self.origin[1])
        transform.concat()
        # On ne dessine que ce qui touche le cadre, marge comprise : à deux cents cartes, tout
        # peindre à chaque geste coûte dix fois le prix de ce qu'on voit.
        left, top, width, height = self.window_in_scene()
        seen = (left - CULL, top - CULL, left + width + CULL, top + height + CULL)
        self.draw_lanes(seen)
        self.draw_routes(seen)
        for card in self.scene.cards:
            if card.x < seen[2] and card.x + card.width > seen[0] and card.y < seen[3] and card.y + card.height > seen[1]:
                self.draw_card(card)
        NSGraphicsContext.restoreGraphicsState()
        # Pastilles et légende vivent dans le repère de la vue : elles collent au cadre, pas à
        # la scène, et ne doivent ni bouger ni grossir avec le zoom.
        self.draw_bubbles()

    @objc.python_method
    def draw_lanes(self, seen) -> None:
        for lane in self.scene.lanes:
            left, right = lane.x, lane.x + lane.width
            if not lane.width or right < seen[0] or left > seen[2] or lane.y > seen[3] or lane.y + lane.height < seen[1]:
                continue
            box = NSMakeRect(left, lane.y, lane.width, lane.height + 20.0)
            # Le fond d'un couloir peut faire deux mille points de côté : on le peint à travers
            # une découpe au cadre, sinon on paie chaque image le remplissage de tout le plan.
            NSGraphicsContext.saveGraphicsState()
            NSBezierPath.clipRect_(NSMakeRect(seen[0], seen[1], seen[2] - seen[0], seen[3] - seen[1]))
            NSColor.quaternaryLabelColor().colorWithAlphaComponent_(0.06).setFill()
            NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(box, 18.0, 18.0).fill()
            NSGraphicsContext.restoreGraphicsState()
            tint = hex_colour(lane.colour) or NSColor.secondaryLabelColor()
            _write(lane.label.upper(), _font(12.0, NSFontWeightBold), tint,
                   NSMakeRect(left + 18.0, lane.y + 6.0, right - left - 36.0, 18.0))

    @objc.python_method
    def draw_routes(self, seen) -> None:
        for route in self.scene.routes:
            box = route.box
            if box[2] < seen[0] or box[0] > seen[2] or box[3] < seen[1] or box[1] > seen[3]:
                continue
            thick, dash, name, head = ROUTE_STYLE.get(route.kind, ROUTE_STYLE["parent"])
            tint = (hex_colour(route.colour) if route.colour else None) or (
                getattr(NSColor, name)()
                if name
                else (hex_colour(PAPER_TINT) if route.kind == "document" else NSColor.tertiaryLabelColor())
            )
            if self.route is not None:
                # Une flèche est désignée : elle s'épaissit, les autres s'effacent, et les deux
                # cartes qu'elle relie sont déjà mises en avant par `related`.
                shown = route is self.route
                tint = tint.colorWithAlphaComponent_(1.0 if shown else 0.15)
                thick += 1.2 if shown else 0.0
            elif self.hovered:
                # Une carte est désignée : ses liens ressortent, les autres s'effacent au lieu
                # de disparaître — on garde le plan lisible tout en isolant ce qui la concerne.
                touched = self.hovered in (route.source, route.target)
                tint = tint.colorWithAlphaComponent_(1.0 if touched else 0.18)
                thick += 1.0 if touched else 0.0
            path = _polyline(route.points)
            path.setLineWidth_(thick)
            if dash:
                path.setLineDash_count_phase_(dash, len(dash), 0.0)
            tint.setStroke()
            path.stroke()
            if head:
                last, end = route.points[-2], route.points[-1]
                _arrow_head(end, (end[0] - last[0], end[1] - last[1]), tint)
            if route.label and self.scale >= DETAIL:
                self.draw_route_label(route, tint)

    @objc.python_method
    def draw_route_label(self, route, tint) -> None:
        """Le mot posé sur le plus long segment horizontal : la flèche dit ce qu'elle veut dire."""
        runs = [
            (abs(b[0] - a[0]), ((a[0] + b[0]) / 2, a[1]))
            for a, b in zip(route.points, route.points[1:])
            if a[1] == b[1]
        ]
        if not runs:
            return
        span, middle = max(runs)
        font = _font(9.5, NSFontWeightBold)
        width = _width(route.label, font) + 10.0
        if span < width + 12.0:
            return
        box = NSMakeRect(middle[0] - width / 2, middle[1] - 8.0, width, 16.0)
        NSColor.windowBackgroundColor().setFill()
        NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(box, 8.0, 8.0).fill()
        _write(route.label, font, tint, box, centre=True)

    @objc.python_method
    def draw_card(self, card) -> None:
        box = NSMakeRect(card.x, card.y, card.width, card.height)
        path = NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(box, CORNER, CORNER)
        if card.kind == "projet":
            tint = hex_colour(card.colour) or NSColor.systemGrayColor()
            tint.colorWithAlphaComponent_(0.16).setFill()
            path.fill()
            tint.colorWithAlphaComponent_(0.55).setStroke()
            path.setLineWidth_(1.5)
            path.stroke()
            _write("PROJET", _font(10.0, NSFontWeightBold), tint,
                   NSMakeRect(card.x + 18.0, card.y + 14.0, card.width - 36.0, 14.0))
            _write(card.title, _font(14.0, NSFontWeightSemibold), NSColor.labelColor(),
                   NSMakeRect(card.x + 18.0, card.y + 34.0, card.width - 36.0, 22.0))
            return
        if card.kind == "document":
            self.draw_paper(card, path)
            return
        NSColor.controlBackgroundColor().setFill()
        path.fill()
        if card.kind == "fantôme":
            path.setLineWidth_(1.2)
            path.setLineDash_count_phase_([5.0, 4.0], 2, 0.0)
            NSColor.tertiaryLabelColor().setStroke()
            path.stroke()
            _write(card.number, _mono(11.5), NSColor.secondaryLabelColor(),
                   NSMakeRect(card.x + 18.0, card.y + 12.0, card.width - 36.0, 16.0))
            _write(card.title or "parent hors de la liste", _font(12.5), NSColor.tertiaryLabelColor(),
                   NSMakeRect(card.x + 18.0, card.y + 34.0, card.width - 36.0, 30.0))
            return
        if card.key == self.hovered:
            getattr(NSColor, IDENTITY_TINT)().setStroke()
            path.setLineWidth_(2.0)
        elif card.key in self.related:
            NSColor.secondaryLabelColor().setStroke()
            path.setLineWidth_(1.6)
        else:
            NSColor.separatorColor().setStroke()
            path.setLineWidth_(1.0)
        path.stroke()
        # Filet de gauche : un bug, ou rien. C'est la seule chose qu'on veut repérer de loin,
        # sans lire ; ce qui retient le ticket se lit sur ses gélules, de près.
        edge = (
            (hex_colour(card.type_colour) or NSColor.systemRedColor())
            if card.type_key == "bug"
            else NSColor.quaternaryLabelColor()
        )
        band = NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
            NSMakeRect(card.x + 1.0, card.y + 1.0, TYPE_BAND, card.height - 2.0), 2.5, 2.5
        )
        edge.setFill()
        band.fill()
        left = card.x + 18.0
        inner = card.width - 36.0
        if self.scale < DETAIL:
            _write(card.number, _mono(17.0), NSColor.labelColor(),
                   NSMakeRect(left, card.y + card.height / 2 - 12.0, inner, 24.0))
            return
        self.draw_head(card, left, inner)
        self.draw_chips(card, left, inner)
        title_font = _font(13.0, NSFontWeightSemibold)
        for index, line in enumerate(_lines(card.title, title_font, inner, 3)):
            _write(line, title_font, NSColor.labelColor(),
                   NSMakeRect(left, card.y + 62.0 + index * 17.0, inner, 17.0))
        self.draw_foot(card, left, inner)

    @objc.python_method
    def draw_paper(self, card, path) -> None:
        """Carte d'un document : ce qui explique le travail, dans l'indigo de Linear.

        Même largeur qu'un ticket pour rester dans la grille, mais une forme à elle : fond
        teinté, liseré plein, et pas de gélules — un document n'a ni état ni priorité.
        """
        tint = hex_colour(PAPER_TINT) or NSColor.systemIndigoColor()
        tint.colorWithAlphaComponent_(0.10).setFill()
        path.fill()
        tint.colorWithAlphaComponent_(0.45 if card.key != self.hovered else 0.9).setStroke()
        path.setLineWidth_(2.0 if card.key == self.hovered else 1.3)
        path.stroke()
        left, inner = card.x + 18.0, card.width - 36.0
        glyph = tinted_symbol("doc.text.fill", CHIP_GLYPH, tint)
        if glyph is not None:
            _image(glyph, NSMakeRect(left, card.y + 13.0, CHIP_GLYPH, CHIP_GLYPH))
        _write("DOCUMENT", _font(9.5, NSFontWeightBold), tint,
               NSMakeRect(left + CHIP_GLYPH + 6.0, card.y + 12.0, 120.0, 13.0))
        age = since(card.moved_at) if card.moved_at else ""
        if age:
            font = _font(10.0, NSFontWeightMedium)
            width = _width(age, font) + 4.0
            _write(age, font, NSColor.tertiaryLabelColor(),
                   NSMakeRect(card.x + card.width - 18.0 - width, card.y + 12.0, width, 13.0))
        if self.scale < DETAIL:
            return
        title_font = _font(12.5, NSFontWeightSemibold)
        for index, line in enumerate(_lines(card.title, title_font, inner, 2)):
            _write(line, title_font, NSColor.labelColor(),
                   NSMakeRect(left, card.y + 32.0 + index * 16.0, inner, 16.0))

    @objc.python_method
    def draw_head(self, card, left: float, inner: float) -> None:
        """En-tête : le créateur, le numéro, et la priorité telle que Linear la dessine."""
        cursor = left
        face = self.avatars.image(card.creator_face, AVATAR_HEAD) if (self.avatars and card.creator_face) else None
        if face is not None:
            _image(face, NSMakeRect(cursor, card.y + 13.0, AVATAR_HEAD, AVATAR_HEAD))
            cursor += AVATAR_HEAD + 7.0
        number_font = _mono(11.5)
        _write(card.number, number_font, NSColor.secondaryLabelColor(),
               NSMakeRect(cursor, card.y + 13.0, 90.0, AVATAR_HEAD))
        cursor += _width(card.number, number_font) + 8.0
        if card.state:
            tint = hex_colour(card.colour) or NSColor.secondaryLabelColor()
            _chip(cursor, card.y + 12.5, card.state, tint, state_glyph(card.state_type, card.colour, CHIP_GLYPH))
        label = PRIORITY_LABEL.get(card.priority, "")
        if label:
            font = _font(10.5, NSFontWeightSemibold)
            width = _chip_width(label, font, True)
            _chip(card.x + card.width - 18.0 - width, card.y + 12.0, label, priority_tint(card.priority),
                  priority_glyph(card.priority, CHIP_GLYPH), font)

    @objc.python_method
    def draw_chips(self, card, left: float, inner: float) -> None:
        """Deuxième ligne : ce qui retient le ticket, et sa nature s'il en a une.

        L'état est monté en tête, contre le numéro : c'est la première chose qu'on lit. Restent
        ici « bloqué » et « démarrable », déduits des liens, et l'étiquette de Linear.
        """
        cursor, top = left, card.y + 36.0
        if card.blocked:
            text = f"bloqué ×{card.blocked}" if card.blocked > 1 else "bloqué"
            tint = NSColor.systemRedColor()
            cursor += _chip(cursor, top, text, tint, tinted_symbol("hand.raised.fill", CHIP_GLYPH, tint)) + CHIP_GAP
        elif card.free:
            tint = NSColor.systemGreenColor()
            cursor += _chip(cursor, top, "autonome", tint,
                            tinted_symbol("play.fill", CHIP_GLYPH, tint)) + CHIP_GAP
        if card.type_label:
            tint = hex_colour(card.type_colour) or NSColor.secondaryLabelColor()
            width = _chip_width(card.type_label, _font(10.5, NSFontWeightSemibold), True)
            if cursor + width <= card.x + card.width - 18.0:
                _chip(cursor, top, card.type_label, tint, tinted_symbol(card.type_symbol, CHIP_GLYPH, tint))

    @objc.python_method
    def draw_foot(self, card, left: float, inner: float) -> None:
        """Pied : l'assigné, ses PR, ses sous-tickets, et son âge coloré.

        L'âge a la priorité sur les gélules : c'est ce qu'on vient chercher, et il est toujours
        écrit en bout de ligne. Une gélule qui n'entre plus n'est pas dessinée plutôt que posée
        par-dessus le texte.
        """
        bottom = card.y + card.height - 30.0
        age = since(card.moved_at) if card.moved_at else ""
        age_font = _font(10.5, NSFontWeightSemibold)
        age_width = _width(age, age_font) + 4.0 if age else 0.0
        limit = card.x + card.width - 20.0 - age_width
        cursor = left
        face = self.avatars.image(card.assignee_face, AVATAR_FOOT) if (self.avatars and card.assignee_face) else None
        if face is not None:
            _image(face, NSMakeRect(cursor, bottom, AVATAR_FOOT, AVATAR_FOOT))
            cursor += AVATAR_FOOT + 7.0
        for pull in card.pulls[:3]:
            tint = pull_tint(pull.status)
            glyph = pull_glyph(pull.status, CHIP_GLYPH)
            width = _chip_width(pull.label, _font(10.5, NSFontWeightSemibold), glyph is not None)
            if cursor + width > limit:
                break
            box = NSMakeRect(cursor, bottom + 0.5, width, CHIP_HEIGHT)
            warm = self.zone_under(box)
            _chip(cursor, bottom + 0.5, pull.label, tint, glyph, filled=True, strong=warm)
            # Une gélule de PR mène ailleurs que la carte : elle a sa propre zone de clic.
            self.zones.append((box, pull.url, card.key))
            cursor += width + CHIP_GAP
        if age:
            _write(age, age_font, _age_tint(card.moved_at),
                   NSMakeRect(card.x + card.width - 18.0 - age_width, bottom, age_width, AVATAR_FOOT))

    @objc.python_method
    def hidden_cards(self) -> list:
        left, top, width, height = self.window_in_scene()
        return [
            card
            for card in self.scene.cards
            if card.x + card.width < left or card.x > left + width or card.y + card.height < top or card.y > top + height
        ]

    @objc.python_method
    def exit_point(self, card, box) -> tuple:
        """Où la droite qui va du centre du cadre vers la carte coupe le bord du cadre."""
        cx, cy = box[2] / 2, box[3] / 2
        px, py = self.to_view(*card.middle)
        dx, dy = px - cx, py - cy
        if not dx and not dy:
            return (cx, cy)
        spans = []
        if dx:
            spans.append(((box[2] - EDGE_INSET - cx) / dx) if dx > 0 else ((EDGE_INSET - cx) / dx))
        if dy:
            spans.append(((box[3] - EDGE_INSET - cy) / dy) if dy > 0 else ((EDGE_INSET - cy) / dy))
        step = min(span for span in spans if span > 0) if any(span > 0 for span in spans) else 0.0
        return (cx + dx * step, cy + dy * step)

    @objc.python_method
    def draw_bubbles(self) -> None:
        """Une pastille par groupe de cartes sorties du cadre, sur le bord, dans leur direction.

        Le chevron dit vers où elles sont parties : la pastille se lit alors sans réfléchir,
        « cinq de plus par là », et le clic y emmène.
        """
        self.bubbles = []
        size = self.bounds().size
        box = (0.0, 0.0, size.width, size.height)
        groups = []
        for card in sorted(self.hidden_cards(), key=lambda card: (card.y, card.x)):
            point = self.exit_point(card, box)
            for points, keys in groups:
                if math.dist(points[0], point) < CLUSTER_GAP:
                    points.append(point)
                    keys.append(card.key)
                    break
            else:
                groups.append(([point], [card.key]))
        font = _font(11.5, NSFontWeightBold)
        bugs = {card.key for card in self.scene.cards if card.type_key == "bug"}
        for points, keys in groups:
            # Rouge quand le groupe n'annonce que des bugs, neutre dès qu'il mélange : la
            # couleur ne doit pas laisser croire à un bug là où il y a autre chose.
            tint = NSColor.systemRedColor() if keys and set(keys) <= bugs else _slate()
            middle = (
                sum(point[0] for point in points) / len(points),
                sum(point[1] for point in points) / len(points),
            )
            text = f"+{len(keys)}"
            # Le côté d'où la pastille est la plus proche donne la direction du chevron.
            gaps = ((middle[0], "gauche"), (size.width - middle[0], "droite"),
                    (middle[1], "haut"), (size.height - middle[1], "bas"))
            side = min(gaps)[1]
            width = _width(text, font) + 2 * BUBBLE_PAD + BUBBLE_GLYPH + 2.0
            rect = NSMakeRect(
                min(max(middle[0] - width / 2, 4.0), size.width - width - 4.0),
                min(max(middle[1] - BUBBLE_HEIGHT / 2, 4.0), size.height - BUBBLE_HEIGHT - 4.0),
                width,
                BUBBLE_HEIGHT,
            )
            warm = self.pointer is not None and (
                rect.origin.x <= self.pointer[0] <= rect.origin.x + rect.size.width
                and rect.origin.y <= self.pointer[1] <= rect.origin.y + rect.size.height
            )
            path = NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
                rect, BUBBLE_HEIGHT / 2, BUBBLE_HEIGHT / 2
            )
            tint.colorWithAlphaComponent_(1.0 if warm else 0.92).setFill()
            path.fill()
            if warm:
                NSColor.whiteColor().colorWithAlphaComponent_(0.9).setStroke()
                path.setLineWidth_(1.5)
                path.stroke()
            glyph = tinted_symbol(BUBBLE_ARROWS[side], BUBBLE_GLYPH, NSColor.whiteColor())
            head = side in ("gauche", "haut")
            text_x = rect.origin.x + BUBBLE_PAD + (BUBBLE_GLYPH + 2.0 if head else 0.0)
            if glyph is not None:
                _image(
                    glyph,
                    NSMakeRect(
                        rect.origin.x + (BUBBLE_PAD if head else width - BUBBLE_PAD - BUBBLE_GLYPH),
                        rect.origin.y + (BUBBLE_HEIGHT - BUBBLE_GLYPH) / 2,
                        BUBBLE_GLYPH,
                        BUBBLE_GLYPH,
                    ),
                )
            _write(text, font, NSColor.whiteColor(),
                   NSMakeRect(text_x, rect.origin.y, width - BUBBLE_PAD * 2 - BUBBLE_GLYPH - 2.0, BUBBLE_HEIGHT),
                   centre=True)
            self.bubbles.append((rect, keys))


class Legend(NSView):
    """Bandeau du bas : ce que veulent dire les flèches, les filets et la couleur du temps."""

    def isFlipped(self):
        return True

    def drawRect_(self, rect):
        font = _font(10.5, NSFontWeightMedium)
        cursor = BAR_INSET
        middle = self.bounds().size.height / 2
        for shape, label, tint, dash in _LEGEND:
            if shape == "gélule":
                (tint() if callable(tint) else tint).colorWithAlphaComponent_(0.28).setFill()
                NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
                    NSMakeRect(cursor, middle - 5.0, 14.0, 10.0), 5.0, 5.0
                ).fill()
                cursor += 19.0
            elif shape == "trait":
                line = NSBezierPath.bezierPath()
                line.moveToPoint_(NSMakePoint(cursor, middle))
                line.lineToPoint_(NSMakePoint(cursor + 22.0, middle))
                line.setLineWidth_(1.7)
                if dash:
                    line.setLineDash_count_phase_(dash, len(dash), 0.0)
                (tint() if callable(tint) else tint).setStroke()
                line.stroke()
                cursor += 27.0
            else:
                (tint() if callable(tint) else tint).setFill()
                NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
                    NSMakeRect(cursor, middle - 6.0, 4.0, 12.0), 2.0, 2.0
                ).fill()
                cursor += 9.0
            width = _width(label, font)
            _write(label, font, NSColor.secondaryLabelColor(),
                   NSMakeRect(cursor, middle - 9.0, width + 2.0, 18.0))
            cursor += width + 20.0


class Map(NSObject):
    """Fenêtre de la carte : un bandeau qui dit ce qu'on regarde, et le canevas dessous."""

    def initWithContext_(self, context):
        self = objc.super(Map, self).init()
        if self is None:
            return None
        self.avatars = context.get("avatars")
        self.canvas = None
        self.status = None
        self.window = self._window()
        self.refresh(context)
        return self

    @objc.python_method
    def refresh(self, context: dict) -> None:
        """Reprend les tickets du moment : à chaque ouverture, et à chaque lecture terminée."""
        issues = list(context.get("issues") or [])
        self.avatars = context.get("avatars") or self.avatars
        scene = draw_map(issues, context.get("papers") or [])
        self.canvas.show(scene, self.avatars)
        who = context.get("identity") or ""
        cards = sum(1 for card in scene.cards if card.kind == "ticket")
        lanes = sum(1 for lane in scene.lanes if lane.key.startswith("projet:"))
        self.status.setStringValue_(
            f"{cards} ticket(s) assigné(s) à @{who} · {lanes} projet(s)" if who else f"{cards} ticket(s)"
        )

    @objc.python_method
    def _window(self):
        frame = NSMakeRect(0, 0, 1280, 820)
        window = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            frame,
            NSWindowStyleMaskTitled | NSWindowStyleMaskClosable | NSWindowStyleMaskResizable
            | NSWindowStyleMaskMiniaturizable,
            NSBackingStoreBuffered,
            False,
        )
        window.setTitle_("LinearTodo, carte des tickets")
        window.setReleasedWhenClosed_(False)
        window.setMinSize_(NSMakeSize(640, 420))
        window.setDelegate_(self)

        content = NSView.alloc().initWithFrame_(frame)
        width, height = frame.size.width, frame.size.height
        bar = NSView.alloc().initWithFrame_(NSMakeRect(0, height - BAR_HEIGHT, width, BAR_HEIGHT))
        bar.setAutoresizingMask_(NSViewWidthSizable | NSViewMinYMargin)
        self.status = _label("", NSMakeRect(BAR_INSET, 9.0, 380.0, 16.0), 11.5, NSFontWeightSemibold,
                             getattr(NSColor, IDENTITY_TINT)())
        bar.addSubview_(self.status)
        legend = _label(
            "glisser pour se déplacer · ⌘molette ou pincer pour zoomer · ⌘0 recadre · clic : ouvrir le ticket "
            "· en haut le créateur, en bas l'assigné",
            NSMakeRect(BAR_INSET + 390.0, 9.0, width - BAR_INSET * 2 - 390.0, 16.0),
            10.5,
            NSFontWeightRegular,
            NSColor.tertiaryLabelColor(),
        )
        bar.addSubview_(legend)
        content.addSubview_(bar)

        legend_bar = Legend.alloc().initWithFrame_(NSMakeRect(0, 0, width, BAR_HEIGHT))
        legend_bar.setAutoresizingMask_(NSViewWidthSizable | NSViewMaxYMargin)
        content.addSubview_(legend_bar)
        # Une boîte plutôt qu'une couche : poser une CGColor sur un calque fait passer un
        # pointeur brut par PyObjC, qui s'en plaint à chaque ouverture.
        rule = NSBox.alloc().initWithFrame_(NSMakeRect(0, BAR_HEIGHT, width, 1.0))
        rule.setBoxType_(NSBoxCustom)
        rule.setBorderWidth_(0.0)
        rule.setFillColor_(NSColor.separatorColor())
        rule.setAutoresizingMask_(NSViewWidthSizable | NSViewMaxYMargin)
        content.addSubview_(rule)

        self.canvas = Canvas.alloc().initWithFrame_(
            NSMakeRect(0, BAR_HEIGHT, width, height - 2 * BAR_HEIGHT)
        )
        self.canvas.setAutoresizingMask_(NSViewWidthSizable | NSViewHeightSizable)
        content.addSubview_(self.canvas)
        window.setContentView_(content)
        window.makeFirstResponder_(self.canvas)
        window.center()
        return window

    def windowWillClose_(self, notification):
        _ALIVE.pop("map", None)


def _label(text: str, box, size: float, weight, tint):
    field = NSTextField.alloc().initWithFrame_(box)
    field.setStringValue_(text)
    field.setBezeled_(False)
    field.setDrawsBackground_(False)
    field.setEditable_(False)
    field.setSelectable_(False)
    field.setFont_(NSFont.systemFontOfSize_weight_(size, weight))
    field.setTextColor_(tint)
    field.setAutoresizingMask_(NSViewWidthSizable)
    return field


# Le contrôleur doit survivre à l'appel : sans cette référence, il serait ramassé et le canevas
# n'aurait plus personne pour lui donner ses tickets.
_ALIVE: dict = {}


def panel(context: dict):
    """Fenêtre de la carte, créée à la demande et remise à jour à chaque ouverture."""
    live = _ALIVE.get("map")
    if live is None:
        live = Map.alloc().initWithContext_(context)
        _ALIVE["map"] = live
    else:
        live.refresh(context)
    return live


def living():
    """La fenêtre si elle est ouverte : de quoi lui pousser une lecture fraîche."""
    return _ALIVE.get("map")
