"""Carte des tickets : ce qu'on montre, ce qui relie quoi, où chaque carte se pose, et par où
passent les flèches.

Aucun appel à AppKit ici : la scène se calcule et se vérifie sans écran, comme les règles du
menu dans `engine`. La fenêtre ne fait que dessiner ce qui est décidé ici.

Deux idées portent le reste.

La **grille** : toute carte occupe une case (colonne, ligne) d'un quadrillage commun à toute la
carte. Les gouttières verticales et les bandes horizontales sont donc libres partout, et pas
seulement à l'intérieur d'un couloir.

Le **routage** qui en découle : une flèche ne circule que dans ces gouttières et ces bandes, donc
elle ne peut pas passer sous une carte. Chaque famille de flèche part toujours du même bord et
arrive toujours sur le même bord, avec plusieurs ancrages par bord pour que deux flèches ne se
superposent pas.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from .models import Issue, Pull

CARD_WIDTH = 320.0
CARD_HEIGHT = 150.0
# Une carte de projet ou de parent absent n'a ni titre sur trois lignes ni pied de page.
SMALL_HEIGHT = 76.0
# Gouttière et bande : la place où les flèches circulent. Large, parce qu'on n'est pas à
# l'étroit et qu'une flèche lisible vaut mieux qu'un plan compact.
GUTTER = 76.0
BAND = 96.0
COLUMN = CARD_WIDTH + GUTTER
ROW = CARD_HEIGHT + BAND
LANE_GAP = 130.0
LANE_TITLE = 36.0
MARGIN = 80.0
# Au-delà, un couloir revient à la ligne : cent tickets sur une seule rangée ne se parcourent pas.
MAX_COLUMNS = 6
# Écart entre deux voies d'une même réserve : de quoi distinguer deux tracés parallèles sans
# qu'aucun ne sorte de la gouttière ou de la bande.
TRACK_GAP = 11.0
# Créneaux d'ancrage par bord, et écart entre deux, en fraction du bord.
ANCHOR_SLOTS = 4
ANCHOR_STEP = 0.2

# Ordre d'urgence de Linear : 1 urgent, 2 haute, 3 moyenne, 4 basse, 0 aucune.
PRIORITY_ORDER = {1: 0, 2: 1, 3: 2, 4: 3, 0: 4}
PRIORITY_LABEL = {1: "Urgent", 2: "Haute", 3: "Moyenne", 4: "Basse", 0: ""}

# Nature d'un ticket : libellé, couleur, glyphe de repli. Seul ce que Linear déclare compte —
# l'étiquette du groupe « Type ». On n'invente pas de catégorie maison : un ticket qui porte des
# sous-tickets se voit déjà à ses flèches et à sa gélule de sous-tickets.
KIND_GROUP = "Type"
KINDS = {
    "bug": ("Bug", "#eb5757", "ladybug.fill"),
    "évolution": ("Évolution", "#4cb782", "lightbulb.fill"),
}
# Étiquettes Linear qui disent un type, et ce qu'on en fait. Le reste ne type rien.
KIND_OF_LABEL = {
    "bug": "bug",
    "feature request": "évolution",
    "feature": "évolution",
    "improvement": "évolution",
    "évolution": "évolution",
}

LOOSE_LANE = "Sans projet"


@dataclass
class Card:
    """Une carte de la scène, avec sa case une fois le plan calculé."""

    key: str
    kind: str  # "ticket", "projet" ou "fantôme"
    number: str = ""
    title: str = ""
    state: str = ""
    state_type: str = ""
    colour: str = ""
    priority: int = 0
    assignee: str = ""
    assignee_face: str = ""
    creator: str = ""
    creator_face: str = ""
    team: str = ""
    estimate: float | None = None
    milestone: str = ""
    created_at: datetime | None = None
    moved_at: datetime | None = None
    due: datetime | None = None
    url: str = ""
    branch: str = ""
    pulls: tuple[Pull, ...] = ()
    # Nature du ticket : chantier, bug, évolution, ou rien. Libellé et couleur viennent de Linear.
    type_key: str = ""
    type_label: str = ""
    type_colour: str = ""
    type_symbol: str = ""
    # Ce qui se lit d'un coup d'œil : peut démarrer, attend quelqu'un, porte des sous-tickets —
    # `children` les compte tous, `shown` ceux qui sont sur la carte.
    free: bool = False
    blocked: int = 0
    arbitrations: int = 0
    children: int = 0
    shown: int = 0
    col: int = 0
    row: int = 0
    x: float = 0.0
    y: float = 0.0
    width: float = CARD_WIDTH
    height: float = CARD_HEIGHT

    @property
    def middle(self) -> tuple[float, float]:
        return (self.x + self.width / 2, self.y + self.height / 2)

    @property
    def band(self) -> float:
        """Milieu de la bande libre sous la case de la carte."""
        return self.y + CARD_HEIGHT + BAND / 2

    @property
    def gutter_left(self) -> float:
        return self.col * COLUMN - GUTTER / 2

    @property
    def gutter_right(self) -> float:
        return (self.col + 1) * COLUMN - GUTTER / 2


@dataclass
class Link:
    """Un lien typé entre deux cartes, avant qu'on lui trouve un chemin."""

    source: str
    target: str
    kind: str  # "parent", "projet" ou "bloque"


@dataclass
class Route:
    """Le chemin dessiné d'un lien : une ligne brisée qui ne traverse aucune carte."""

    kind: str
    points: tuple
    source: str = ""
    target: str = ""
    label: str = ""
    colour: str = ""
    # Rectangle qui contient le chemin : le dessin s'en sert pour écarter d'un test ce qui est
    # hors du cadre, sans reparcourir les points à chaque image.
    box: tuple = (0.0, 0.0, 0.0, 0.0)


@dataclass
class Lane:
    """Un couloir : un projet, ou les tickets qui n'en ont pas."""

    key: str
    label: str
    colour: str = ""
    y: float = 0.0
    height: float = 0.0
    x: float = 0.0
    width: float = 0.0
    keys: tuple = ()
    rows: tuple = (0, 0)


@dataclass
class Scene:
    cards: list = field(default_factory=list)
    links: list = field(default_factory=list)
    lanes: list = field(default_factory=list)
    routes: list = field(default_factory=list)
    index: dict = field(default_factory=dict, repr=False)

    def card(self, key: str):
        """Carte par sa clé. L'index se refait dès qu'une carte s'ajoute : le dessin appelle
        cette méthode deux fois par flèche, et une recherche linéaire s'y verrait."""
        if len(self.index) != len(self.cards):
            self.index = {found.key: found for found in self.cards}
        return self.index.get(key)

    @property
    def bounds(self) -> tuple:
        """Rectangle qui contient tout, marge comprise : de quoi cadrer à l'ouverture."""
        if not self.cards:
            return (0.0, 0.0, 1.0, 1.0)
        left = min(card.x for card in self.cards) - MARGIN
        top = min(card.y for card in self.cards) - MARGIN - LANE_TITLE
        right = max(card.x + card.width for card in self.cards) + MARGIN
        bottom = max(card.y + card.height for card in self.cards) + MARGIN
        return (left, top, right - left, bottom - top)


def _feasible(keys: list, issues: dict) -> list:
    """Ordre de faisabilité : ce qui débloque passe avant ce qui est bloqué, puis le numéro.

    Un tri topologique sur les seuls blocages internes au groupe. Si 7275 bloque 7636 et que
    7636 bloque 7641, on lit 7275, 7636, 7641 : de gauche à droite, l'ordre dans lequel le
    travail peut se faire. Sans blocage connu, le numéro tranche — c'est l'ordre de création,
    donc celui dans lequel le sujet a été découpé.

    Une boucle de blocages ne bloque pas le tri : on prend le plus petit numéro et on avance,
    quitte à contredire une flèche, plutôt que de tourner en rond.
    """
    inside = set(keys)
    waiting = {
        key: {link.other for link in issues[key].blockers if link.other in inside}
        for key in keys
        if key in issues
    }
    order, done = [], set()
    while len(order) < len(keys):
        ready = sorted(key for key in keys if key not in done and not (waiting.get(key, set()) - done))
        if not ready:
            ready = [min(key for key in keys if key not in done)]
        order += ready
        done.update(ready)
    return order


def _kind_of(issue: Issue) -> tuple:
    """Nature du ticket, telle que Linear l'étiquette : bug, évolution, ou rien.

    La couleur vient de l'étiquette Linear ; deux types peuvent partager la même — chez
    Spacefill, « Bug » et « Feature request » sont tous deux rouges — et c'est alors le glyphe
    et le mot qui les séparent.
    """
    for tag in issue.labels:
        key = KIND_OF_LABEL.get(tag.name.strip().lower())
        if key and (tag.group == KIND_GROUP or not tag.group):
            return (key, tag.name, tag.colour or KINDS[key][1], KINDS[key][2])
    return ("", "", "", "")


def _card_of(issue: Issue, blocked: int, shown: int, offspring: int, free: bool) -> Card:
    key, label, colour, symbol = _kind_of(issue)
    return Card(
        key=issue.identifier,
        kind="ticket",
        number=issue.identifier,
        title=issue.title,
        state=issue.state,
        state_type=issue.state_type,
        colour=issue.colour,
        priority=issue.priority,
        assignee=issue.assignee,
        assignee_face=issue.assignee_face,
        creator=issue.creator,
        creator_face=issue.creator_face,
        team=issue.team,
        estimate=issue.estimate,
        milestone=issue.milestone,
        created_at=issue.created_at,
        moved_at=issue.moved_at,
        due=issue.due,
        url=issue.url,
        branch=issue.branch,
        pulls=issue.pulls,
        type_key=key,
        type_label=label,
        type_colour=colour,
        type_symbol=symbol,
        free=free,
        blocked=blocked,
        arbitrations=issue.arbitrations,
        children=offspring,
        shown=shown,
    )


def _ghost(issue: Issue) -> Card:
    """Carte d'un parent qui n'est pas dans la liste lue : il manque, mais il existe.

    Il porte sa couleur d'état et son adresse : c'est souvent le ticket qu'on veut ouvrir pour
    comprendre ce que ses enfants servent, et rien d'autre ne le décrira jamais.
    """
    return Card(
        key=issue.parent,
        kind="fantôme",
        number=issue.parent,
        title=issue.parent_title,
        state_type=issue.parent_state,
        colour=issue.parent_colour,
        url=issue.parent_url,
        height=SMALL_HEIGHT,
    )


def _project_card(key: str, name: str, colour: str) -> Card:
    return Card(key=key, kind="projet", title=name, colour=colour, height=SMALL_HEIGHT)


def _paper_card(paper) -> Card:
    """Carte d'un document : ce qui explique le travail, à côté du travail."""
    return Card(
        key=f"doc:{paper.id}",
        kind="document",
        title=paper.title,
        creator=paper.author,
        creator_face=paper.author_face,
        moved_at=paper.updated_at,
        url=paper.url,
        height=SMALL_HEIGHT,
    )


def build(issues: list, papers: list | None = None) -> Scene:
    """Scène complète : les cartes et les liens typés, sans coordonnées."""
    known = {issue.identifier: issue for issue in issues if issue.identifier}
    scene = Scene()
    blockers = {
        identifier: sum(1 for link in issue.blockers if link.other) for identifier, issue in known.items()
    }
    shown: dict = {}
    for issue in known.values():
        if issue.parent:
            shown[issue.parent] = shown.get(issue.parent, 0) + 1
    hidden = {
        identifier: max(0, len(issue.children) - shown.get(identifier, 0))
        for identifier, issue in known.items()
    }
    # Sous-tickets encore ouverts, ceux de la carte comme ceux qu'on ne voit pas : un parent
    # les attend pour se clore, même si aucune relation de blocage ne le dit.
    open_children: dict = {}
    for identifier, issue in known.items():
        inside = sum(1 for other in known.values() if other.parent == identifier and other.open)
        outside = sum(1 for link in issue.children if link.other not in known and link.open)
        open_children[identifier] = inside + outside

    for identifier, issue in known.items():
        offspring = shown.get(identifier, 0) + hidden.get(identifier, 0)
        # Autonome : aucun ticket ne le retient. Ni blocage, ni sous-ticket ouvert — un parent
        # ne se clôt pas avant ses enfants. Un arbitrage en attente ne l'enlève pas : il dit
        # justement que le ticket partira dès que la réponse tombe. L'état n'entre pas dans le
        # calcul : à faire, en cours ou en revue, la question reste la même.
        free = not blockers.get(identifier) and not open_children.get(identifier)
        scene.cards.append(
            _card_of(issue, blockers.get(identifier, 0), shown.get(identifier, 0), offspring, free)
        )
        if issue.parent:
            if issue.parent not in known and not scene.card(issue.parent):
                scene.cards.append(_ghost(issue))
            scene.links.append(Link(issue.parent, identifier, "parent"))
        elif issue.project_id:
            scene.links.append(Link(f"projet:{issue.project_id}", identifier, "projet"))
        for link in issue.blockers:
            if link.other in known:
                scene.links.append(Link(link.other, identifier, "bloque"))
    for issue in known.values():
        if issue.project_id and not scene.card(f"projet:{issue.project_id}"):
            scene.cards.append(_project_card(f"projet:{issue.project_id}", issue.project, issue.project_colour))
    for paper in papers or []:
        # Un document ne se dessine que s'il documente quelque chose qui est là : sur une carte
        # de tickets, une note orpheline n'apprendrait rien.
        target = paper.issue if scene.card(paper.issue) else f"projet:{paper.project_id}"
        if not scene.card(target):
            continue
        scene.cards.append(_paper_card(paper))
        scene.links.append(Link(f"doc:{paper.id}", target, "document"))
    return scene


def _lanes_of(issues: list, scene: Scene) -> list:
    """Répartit les cartes en couloirs : un par projet, plus celui des tickets sans projet.

    Un ticket suit le projet de la racine de son arbre, pas le sien : un sous-ticket reste sous
    son parent. Les couloirs de projet passent en tête quand ils portent le plus de travail — à
    l'ouverture, on tombe sur ce qui occupe.
    """
    known = {issue.identifier: issue for issue in issues if issue.identifier}
    roots: dict = {}
    for identifier, issue in known.items():
        root, seen = issue, {identifier}
        while root.parent in known and root.parent not in seen:
            seen.add(root.parent)
            root = known[root.parent]
        roots[identifier] = root.identifier
    homes_of_root = {
        key: (f"projet:{known[key].project_id}" if known[key].project_id else LOOSE_LANE)
        for key in set(roots.values())
    }
    # Un ticket sans projet qui bloque un ticket de projet, ou qu'un tel ticket bloque, rejoint
    # son couloir : le lien se lit alors sur place, au lieu de traverser tout le plan.
    partners: dict = {}
    for identifier, issue in known.items():
        for link in issue.blockers:
            if link.other in known:
                partners.setdefault(identifier, []).append(link.other)
                partners.setdefault(link.other, []).append(identifier)
    for key, home in list(homes_of_root.items()):
        if home != LOOSE_LANE:
            continue
        for other in partners.get(key, []):
            adopted = homes_of_root.get(roots.get(other, ""), LOOSE_LANE)
            if adopted.startswith("projet:"):
                homes_of_root[key] = adopted
                break
    homes = {identifier: homes_of_root[root] for identifier, root in roots.items()}
    for card in scene.cards:
        if card.kind == "fantôme":
            child = next((key for key in homes if known[key].parent == card.key), "")
            homes[card.key] = homes.get(child, LOOSE_LANE)
    for link in scene.links:
        if link.kind == "document":
            # Une note pendue à un projet rejoint le couloir de ce projet, dont la clé est celle
            # de sa carte ; pendue à un ticket, elle suit le couloir de ce ticket.
            homes[link.source] = (
                link.target if link.target.startswith("projet:") else homes.get(link.target, LOOSE_LANE)
            )

    lanes: dict = {}
    members: dict = {}
    for key, home in homes.items():
        if home not in lanes:
            project = scene.card(home) if home.startswith("projet:") else None
            lanes[home] = Lane(home, project.title if project else home, project.colour if project else "")
        members.setdefault(home, []).append(key)
    for key in lanes:
        if key.startswith("projet:"):
            members[key].insert(0, key)

    order = sorted(
        (key for key in lanes if key.startswith("projet:")),
        key=lambda key: (-len(members[key]), lanes[key].label),
    )
    if LOOSE_LANE in lanes:
        order.append(LOOSE_LANE)
    return [(lanes[key], members[key]) for key in order]


def _forest(keys: list, issues: dict, scene: Scene) -> tuple:
    """Racines du couloir et, sous chacune, ses descendants — les arbres à poser côte à côte.

    Les documents en sont exclus : ils ne descendent de rien et ne portent rien, ils se rangent
    ensuite à côté de ce qu'ils documentent.
    """
    keys = [key for key in keys if not key.startswith("doc:")]
    inside = set(keys)
    children: dict = {}
    roots: list = []
    for key in keys:
        issue = issues.get(key)
        parent = issue.parent if issue else ""
        if not key.startswith("projet:") and parent and parent in inside:
            children.setdefault(parent, []).append(key)
        else:
            roots.append(key)
    project = next((key for key in keys if key.startswith("projet:")), "")
    if project:
        children.setdefault(project, []).extend(key for key in roots if key != project)
        roots = [project]
    for parent, brood in children.items():
        children[parent] = _feasible(brood, issues)
    return _feasible(roots, issues), children


def _tuck(scene: Scene, members: list, links: list) -> None:
    """Glisse chaque document dans la case à gauche de ce qu'il documente.

    Si cette case est prise, tout ce qui est à droite dans le couloir recule d'une colonne : la
    grille reste sans trou ni doublon, et la flèche du document reste courte.
    """
    inside = set(members)
    for link in links:
        paper, target = scene.card(link.source), scene.card(link.target)
        if paper is None or target is None or link.source not in inside:
            continue
        taken = {
            (scene.card(key).col, scene.card(key).row)
            for key in members
            if scene.card(key) is not None and key != link.source
        }
        if target.col == 0 or (target.col - 1, target.row) in taken:
            for key in members:
                card = scene.card(key)
                if card is not None and key != link.source and card.col >= target.col:
                    card.col += 1
        paper.col, paper.row = target.col - 1, target.row


def _rows_of(keys, scene: Scene, floor: int) -> int:
    return max((scene.card(key).row for key in keys if scene.card(key)), default=floor)


def _spread(key: str, children: dict, scene: Scene, col: int, row: int, placed: set) -> int:
    """Pose un arbre en cases de la grille et rend le nombre de colonnes qu'il occupe.

    Une carte déjà posée n'est jamais reposée : Linear interdit qu'un ticket soit son propre
    ancêtre, mais une boucle reçue de l'API doit donner un plan bancal, pas une récursion sans
    fin ni deux cartes dans la même case.
    """
    if key in placed:
        return 0
    placed.add(key)
    card = scene.card(key)
    brood = [child for child in children.get(key, []) if child not in placed]
    if not brood:
        if card:
            card.col, card.row = col, row
        return 1
    cursor, line, widest = col, row + 1, 0
    for child in brood:
        before = set(placed)
        span = _spread(child, children, scene, cursor, line, placed)
        if not span:
            continue
        if cursor > col and cursor - col + span > MAX_COLUMNS:
            # Trop de frères pour une seule rangée : celui qu'on vient de poser redescend sous
            # tout ce qui est déjà posé. Poser puis décaler évite de le mesurer deux fois ; se
            # caler sous les seuls frères laisserait la place à une autre branche déjà là.
            floor = _rows_of(before, scene, line) + 1
            for key in placed - before:
                moved = scene.card(key)
                moved.col -= cursor - col
                moved.row += floor - line
            line, cursor = floor, col
        cursor += span
        widest = max(widest, cursor - col)
    span = max(1, widest)
    if card:
        card.col, card.row = col + (span - 1) // 2, row
    return span


def place(issues: list, scene: Scene) -> Scene:
    """Donne à chaque carte sa case, puis ses coordonnées : couloirs empilés, grille commune."""
    known = {issue.identifier: issue for issue in issues if issue.identifier}
    row = 0
    for lane, members in _lanes_of(issues, scene):
        roots, children = _forest(members, known, scene)
        placed: set = set()
        col, line, first = 0, row, row
        for root in [*roots, *sorted(key for key in members if key not in set(roots))]:
            before = set(placed)
            span = _spread(root, children, scene, col, line, placed)
            if not span:
                continue
            fresh = placed - before
            if col and col + span > MAX_COLUMNS:
                # Trop large pour la ligne en cours : le bloc qu'on vient de poser redescend
                # sous le précédent, en colonne zéro. Poser puis décaler évite de le mesurer une
                # seconde fois, donc d'avoir deux calculs qui pourraient se contredire.
                floor = _rows_of(before, scene, line) + 1
                for key in fresh:
                    card = scene.card(key)
                    card.col -= col
                    card.row += floor - line
                line, col = floor, 0
            col += span
        _tuck(scene, members, [link for link in scene.links if link.kind == "document"])
        lane.keys = tuple(members)
        lane.rows = (first, _rows_of(members, scene, first))
        scene.lanes.append(lane)
        row = lane.rows[1] + 1

    height = 0.0
    for lane in scene.lanes:
        first, last = lane.rows
        lane.y = height - LANE_TITLE
        lane.height = (last - first + 1) * ROW - BAND + LANE_TITLE
        for key in lane.keys:
            card = scene.card(key)
            if card is not None:
                card.x = card.col * COLUMN
                card.y = height + (card.row - first) * ROW
        cards = [scene.card(key) for key in lane.keys if scene.card(key)]
        if cards:
            lane.x = min(card.x for card in cards) - 28.0
            lane.width = max(card.x + card.width for card in cards) + 28.0 - lane.x
        height += (last - first + 1) * ROW + LANE_GAP
    return scene


def _side_of(source: Card, target: Card, kind: str) -> tuple:
    """Par quel bord une flèche sort, par lequel elle entre. Une famille, deux bords.

    Les liens de filiation descendent : ils quittent le bas du parent et arrivent sur le haut de
    l'enfant. Les blocages traversent : ils quittent un flanc et arrivent sur le flanc opposé.
    """
    if kind in ("parent", "projet"):
        return ("bas", "haut")
    # Toujours les mêmes bords, même quand la cible est à gauche : une famille de flèche se
    # reconnaît à l'endroit d'où elle part. Le miroir raccourcissait le trait mais faisait
    # arriver deux blocages d'un même ticket sur deux bords différents.
    return ("droite", "gauche")


def _anchor(card: Card, side: str, index: int, total: int) -> tuple:
    """Point d'ancrage sur un bord : les flèches d'un même bord s'y répartissent.

    Quatre créneaux au plus, écartés d'un cinquième du bord et centrés dessus. Le plafond
    compte : au-delà, les flèches se serreraient à quelques points l'une de l'autre et on ne
    verrait plus qu'un pinceau. Quand elles sont plus nombreuses que les créneaux, elles s'y
    répartissent dans l'ordre de leur cible, donc sans se croiser entre elles.
    """
    slots = max(1, min(total, ANCHOR_SLOTS))
    slot = min(index * slots // total, slots - 1) if total else 0
    span = 0.5 + (slot - (slots - 1) / 2) * ANCHOR_STEP
    if side == "bas":
        return (card.x + card.width * span, card.y + card.height)
    if side == "haut":
        return (card.x + card.width * span, card.y)
    if side == "droite":
        return (card.x + card.width, card.y + card.height * span)
    return (card.x, card.y + card.height * span)


def _order(scene: Scene) -> tuple:
    """Range les liens par carte et par bord, dans l'ordre où leurs cibles se présentent.

    C'est ce classement qui évite les croisements : deux flèches qui partent du même bord vers
    des cartes voisines gardent leur ordre, donc leurs chemins ne se coupent pas.
    """
    sides: dict = {}
    for link in scene.links:
        source, target = scene.card(link.source), scene.card(link.target)
        if source is None or target is None:
            continue
        out_side, in_side = _side_of(source, target, link.kind)
        sides.setdefault((source.key, out_side), []).append((target.middle, link))
        sides.setdefault((target.key, in_side), []).append((source.middle, link))
    places, counts = {}, {}
    for (key, side), entries in sides.items():
        entries.sort(key=lambda entry: entry[0][1] if side in ("gauche", "droite") else entry[0][0])
        counts[(key, side)] = len(entries)
        for index, (_, link) in enumerate(entries):
            places[(key, side, id(link))] = index
    return places, counts


def wire(scene: Scene) -> Scene:
    """Trace le chemin de chaque lien : gouttières verticales, bandes horizontales, rien d'autre.

    Aucun segment ne peut donc traverser une carte — c'est la grille qui le garantit, pas une
    correction après coup.
    """
    places, counts = _order(scene)
    for link in scene.links:
        source, target = scene.card(link.source), scene.card(link.target)
        if source is None or target is None:
            continue
        out_side, in_side = _side_of(source, target, link.kind)
        start = _anchor(source, out_side, places[(source.key, out_side, id(link))], counts[(source.key, out_side)])
        end = _anchor(target, in_side, places[(target.key, in_side, id(link))], counts[(target.key, in_side)])
        if link.kind in ("parent", "projet") and target.row > source.row:
            channel = source.band
            if target.row - source.row > 1:
                # L'enfant est plus d'une ligne plus bas — des frères sont revenus à la ligne.
                # On ne peut plus descendre tout droit : on passe par la gouttière de l'enfant,
                # puis par la bande juste au-dessus de lui, toutes deux libres par construction.
                above = target.y - BAND / 2
                points = (
                    start,
                    (start[0], channel),
                    (target.gutter_left, channel),
                    (target.gutter_left, above),
                    (end[0], above),
                    end,
                )
            else:
                points = (start, (start[0], channel), (end[0], channel), end)
        else:
            # Le blocage passe sous les deux cartes : il sort d'un flanc, gagne la gouttière,
            # longe la plus basse des deux bandes, remonte, et entre par le flanc opposé. Un
            # lien de filiation qui ne descend pas — Linear l'interdit, une boucle reçue de
            # l'API le produit quand même — emprunte le même chemin plutôt que de traverser.
            if link.kind in ("parent", "projet"):
                out_side, in_side = _side_of(source, target, "bloque")
                start = _anchor(source, out_side, 0, 1)
                end = _anchor(target, in_side, 0, 1)
            out_x, in_x = source.gutter_right, target.gutter_left
            if abs(out_x - in_x) < 1.0:
                # Colonnes voisines : les deux gouttières n'en font qu'une, la flèche y monte
                # ou y descend tout droit. Le détour par la bande n'apprendrait rien.
                points = (start, (out_x, start[1]), (out_x, end[1]), end)
            else:
                channel = max(source.band, target.band)
                points = (start, (out_x, start[1]), (out_x, channel), (in_x, channel), (in_x, end[1]), end)
        xs = [point[0] for point in points]
        ys = [point[1] for point in points]
        scene.routes.append(
            Route(
                kind=link.kind,
                points=points,
                source=link.source,
                target=link.target,
                label={"bloque": "bloque", "document": "documente"}.get(link.kind, ""),
                colour=source.colour if link.kind == "projet" else "",
                box=(min(xs), min(ys), max(xs), max(ys)),
            )
        )
    return scene


def _tracks(scene: Scene) -> None:
    """Écarte les tracés qui partageraient la même réserve, chacun sur sa voie.

    Deux blocages qui longent la même bande se superposeraient trait pour trait : on ne saurait
    plus lequel va où. On les colorie donc comme des intervalles — deux tracés qui se recouvrent
    ne prennent jamais la même voie — et on décale chacun de sa voie, sans sortir de la réserve.
    """
    for axis, gap, reserve in ((1, TRACK_GAP, BAND), (0, TRACK_GAP, GUTTER)):
        runs: dict = {}
        for route in scene.routes:
            if route.kind != "bloque":
                continue
            for index, (first, second) in enumerate(zip(route.points, route.points[1:])):
                if first[axis] != second[axis] or first == second:
                    continue
                if index == 0 or index == len(route.points) - 2:
                    # Le premier et le dernier tronçon touchent une carte : les déplacer
                    # décollerait la flèche de son bord. Deux cartes de colonnes voisines
                    # donnent en plus un tronçon de longueur nulle, qui déchirait le tracé.
                    continue
                other = 1 - axis
                runs.setdefault(round(first[axis], 1), []).append(
                    (min(first[other], second[other]), max(first[other], second[other]), route, index)
                )
        for position, entries in runs.items():
            entries.sort(key=lambda entry: entry[0])
            taken: list = []
            for start, end, route, index in entries:
                # Première voie libre : celle qu'aucun tracé recouvrant n'occupe déjà.
                lane = next((slot for slot, busy in enumerate(taken) if busy <= start), len(taken))
                if lane == len(taken):
                    taken.append(end)
                else:
                    taken[lane] = end
                step = ((lane + 1) // 2) * (1 if lane % 2 else -1) * gap
                if abs(step) > reserve / 2 - gap:
                    continue
                points = list(route.points)
                for corner in (index, index + 1):
                    moved = list(points[corner])
                    moved[axis] = position + step
                    points[corner] = tuple(moved)
                route.points = tuple(points)
    for route in scene.routes:
        xs = [point[0] for point in route.points]
        ys = [point[1] for point in route.points]
        route.box = (min(xs), min(ys), max(xs), max(ys))


def draw_map(issues: list, papers: list | None = None) -> Scene:
    """La scène prête à dessiner : cartes sur la grille, flèches routées, couloirs mesurés."""
    scene = wire(place(issues, build(issues, papers)))
    _tracks(scene)
    return scene
