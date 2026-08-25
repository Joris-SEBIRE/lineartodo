"""Règles d'affichage : de la boîte de réception et de mes tickets aux lignes du menu.

Quatre sections, dans l'ordre où on les lit : ce que la boîte contient encore, ce qu'on y a
rangé, les tickets qui me sont assignés, ceux qui sont clos. Rien d'autre — l'app montre l'état
de Linear, elle n'en déduit pas une seconde liste de travail à côté.

**Un sujet, une ligne.** Linear regroupe dans sa boîte tous les événements d'un même ticket :
l'app fait pareil, sinon deux comptes voisins racontent deux histoires différentes. La pastille
d'une ligne vaut donc un, quel que soit le nombre d'événements qu'elle porte, et le badge de la
barre compte des sujets, comme la boîte de Linear. Le nombre d'événements se lit sur la ligne.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone

from .config import Config
from .formatting import excerpt, join, since, until
from .models import GROUPS, ORDER, Issue, Item, Kind, Note, Work, event_label

MAX_CHIPS = 5
TRASHED = "ticket supprimé"
# Préfixe des pastilles d'état dessinées, et gris que Linear donne à ce qui est clos.
STATE_MARK = "state:"
TRASH_COLOUR = "#95a2b3"


def now() -> datetime:
    return datetime.now(timezone.utc)


def _chips(issue: Issue | None, events: int = 0) -> tuple[tuple[str, str], ...]:
    """Pastilles grises d'une ligne : le nombre d'événements, puis l'état du ticket.

    Elles ne comptent rien dans la barre — c'est la pastille colorée qui compte, et elle vaut un
    sujet. Celle-ci dit seulement combien de choses sont arrivées sur ce sujet.
    """
    flags: list[tuple[str, str]] = []
    if events > 1:
        flags.append(("bell", str(events)))
    if issue is None:
        return tuple(flags)
    if issue.priority == 1:
        flags.append(("exclamationmark.octagon", ""))
    if issue.due is not None and issue.due < now():
        flags.append(("calendar.badge.exclamationmark", ""))
    if issue.blockers:
        flags.append(("hand.raised", ""))
    if issue.sla_at is not None and issue.sla_at < now():
        flags.append(("timer", ""))
    if issue.trashed:
        flags.append((f"{STATE_MARK}trashed:{TRASH_COLOUR}", ""))
    elif issue.state_type:
        flags.append((f"state:{issue.state_type}:{issue.colour}", issue.state))
    return tuple(flags)


def _tag(issue: Issue | None) -> str:
    """L'unique état qui doit sauter aux yeux, quand il y en a un.

    C'est ce qui remplace les sections déduites d'autrefois : l'échéance et le blocage se lisent
    sur la ligne du ticket, là où ils servent, plutôt que dans une section à eux.
    """
    if issue is None:
        return ""
    if issue.due is not None and issue.due < now():
        return "en retard"
    if issue.sla_at is not None and issue.sla_at < now():
        return "SLA"
    if issue.blockers:
        return "bloqué"
    if issue.priority == 1:
        return "urgent"
    return ""


def _route(issue: Issue | None) -> str:
    if issue is None:
        return ""
    return join(issue.team_name or issue.team, issue.project, issue.cycle)


def _item(
    kind: Kind, key: str, title: str, at: datetime, url: str, *, issue=None, detail="", events=0, **extra
) -> Item:
    """Une ligne : titre en haut, métadonnées uniformes en dessous.

    Le poids vaut un dès que la ligne porte une pastille, jamais plus : une ligne, un sujet, une
    unité dans le badge. Le nombre d'événements passe en pastille grise.
    """
    counted = GROUPS[kind].is_action
    return Item(
        id=f"{kind.value}:{key}",
        kind=kind,
        title=title or "(sans titre)",
        detail=detail,
        url=url,
        at=at,
        fingerprint=f"{key}:{at.isoformat()}:{events}",
        team=issue.team if issue else "",
        ident=issue.identifier if issue else "",
        weight=1 if counted else 0,
        chips=_chips(issue, events)[:MAX_CHIPS],
        route=_route(issue),
        tag=_tag(issue),
        **extra,
    )


def _subject(note: Note) -> str:
    if note.issue:
        return note.issue.title
    return note.title or note.entity or event_label(note.type)


def _where(note: Note) -> str:
    """D'où vient l'événement : le ticket, ou l'entité visée à défaut."""
    if note.issue:
        return note.issue.identifier
    return note.entity or note.subtitle


def _people(batch: list[Note]) -> dict[str, str]:
    """Un visage par personne, la première à s'être manifestée en tête."""
    faces: dict[str, str] = {}
    for note in sorted(batch, key=lambda entry: entry.updated_at):
        if note.actor_face:
            faces.setdefault(note.actor, note.actor_face)
    return faces


def _natures(batch: list[Note]) -> str:
    """Ce qui est arrivé sur ce sujet, du plus récent au plus ancien, sans redite."""
    seen: list[str] = []
    for note in sorted(batch, key=lambda entry: entry.updated_at, reverse=True):
        label = event_label(note.type)
        if label not in seen:
            seen.append(label)
    return ", ".join(seen)


def _group(notes: list[Note]) -> dict[str, list[Note]]:
    """Les notifications rassemblées par sujet, comme la boîte de Linear les affiche."""
    groups: dict[str, list[Note]] = {}
    for note in notes:
        groups.setdefault(note.key, []).append(note)
    return groups


def _excerpt_of(batch: list[Note]) -> str:
    """Le dernier message écrit sur ce sujet, s'il y en a un."""
    for note in sorted(batch, key=lambda entry: entry.updated_at, reverse=True):
        if note.comment and note.comment.body:
            return excerpt(note.comment.body)
    return ""


def inbox_items(notes: list[Note]) -> list[Item]:
    """Ce que la boîte contient encore : une ligne par sujet, la plus récente en tête.

    Rouge tant qu'un événement du sujet n'a pas été lu, violet quand tout l'a été sans être
    rangé. Un sujet dont tout est en sommeil attend son réveil sans compter dans aucun badge.
    """
    items: list[Item] = []
    for key, batch in _group([note for note in notes if not note.archived and not note.stale]).items():
        awake = [note for note in batch if not note.asleep]
        latest = max(batch, key=lambda note: note.updated_at)
        oldest = min(awake or batch, key=lambda note: note.updated_at)
        faces = _people(batch)
        who = ", ".join(f"@{name}" for name in faces) or "Linear"
        sleeping = [note.snoozed_until for note in batch if note.asleep and note.snoozed_until]
        rest = f"réveil {until(min(sleeping))}" if sleeping and not awake else ""
        hot = any(note.unread for note in awake)
        state = "non lue(s)" if hot else "lue(s), pas encore rangée(s)" if awake else "en sommeil"
        items.append(
            _item(
                Kind.INBOX,
                key,
                _subject(latest),
                latest.updated_at,
                oldest.url or latest.url,
                issue=latest.issue,
                detail=join(
                    _where(latest),
                    f"notifié par @{latest.actor}" if latest.actor else "",
                    since(latest.updated_at),
                    _natures(batch),
                    _excerpt_of(batch),
                    rest,
                ),
                events=len(batch),
                avatar=latest.actor_face,
                faces=tuple(faces.values()),
                warm=not hot,
                asleep=not awake,
                hint=f"{len(batch)} événement(s) de {who}, {state} : {_natures(batch)}",
            )
        )
    return items


def filed_items(notes: list[Note], cfg: Config) -> list[Item]:
    """L'histoire de la boîte : ce qui en est sorti, par sujet, du plus récent au plus ancien.

    Un ticket parti à la corbeille y tombe aussi : Linear laisse parfois sa notification non
    lue, mais son lien n'ouvre plus rien et rien ne pourrait l'éteindre.
    """
    if not cfg.show_filed:
        return []
    floor = now() - timedelta(days=max(1, cfg.filed_days))

    def when(note: Note) -> datetime:
        return note.archived_at or note.read_at or note.updated_at

    kept = [note for note in notes if (note.archived or note.stale) and when(note) > floor]
    items = []
    for key, batch in _group(kept).items():
        latest = max(batch, key=when)
        natures = _natures(batch)
        # « ticket supprimé » est déjà le nom d'un événement : ne le dire qu'une fois.
        gone = any(note.stale for note in batch) and TRASHED not in natures
        faces = _people(batch)
        items.append(
            _item(
                Kind.FILED,
                key,
                _subject(latest),
                when(latest),
                latest.url,
                issue=latest.issue,
                detail=join(
                    _where(latest),
                    f"notifié par @{latest.actor}" if latest.actor else "",
                    since(when(latest)),
                    natures,
                    TRASHED if gone else "",
                ),
                events=len(batch),
                avatar=latest.actor_face,
                faces=tuple(faces.values()),
                hint=(f"{TRASHED} — " if any(note.stale for note in batch) else "")
                + f"{len(batch)} événement(s) rangé(s) : {natures}",
            )
        )
    return items


def _issue_item(kind: Kind, issue: Issue, at: datetime, hint: str, extra: str = "") -> Item:
    """Une ligne de ticket. Le visage est celui du créateur : l'assigné, c'est la personne
    observée, elle n'apprend rien à sa propre liste."""
    who = f"créé par @{issue.creator}" if issue.creator else "sans créateur connu"
    return _item(
        kind,
        issue.id,
        issue.title,
        at,
        issue.url,
        issue=issue,
        detail=join(issue.identifier, who, since(at), extra),
        avatar=issue.creator_face or issue.assignee_face,
        hint=hint,
    )


def mine_items(work: Work) -> list[Item]:
    """Mes tickets ouverts, du plus récemment bougé au plus dormant.

    Le tri fait le travail des anciennes sections déduites : ce qui n'a pas bougé depuis des
    semaines tombe de lui-même en bas de la liste, et ce qui coince porte son étiquette.
    """
    items = []
    for issue in sorted(work.mine, key=lambda entry: entry.at, reverse=True):
        if not issue.open:
            continue
        blockers = ", ".join(link.other for link in issue.blockers)
        items.append(
            _issue_item(
                Kind.MINE,
                issue,
                issue.at,
                f"{issue.state} — bloqué par {blockers}" if blockers else f"{issue.state}, bougé {since(issue.at)}",
                extra=f"bloqué par {blockers}" if blockers else "",
            )
        )
    return items


def closed_items(work: Work, cfg: Config, notes: list[Note] | None = None) -> list[Item]:
    """Mes tickets sortis de la liste, du plus récent au plus ancien, et par la main de qui.

    L'historique d'états dit qui a clôturé, mais une suppression n'est pas une transition : son
    auteur ne se trouve que dans la notification `issueDeleted`, quand elle est encore là.
    """
    if not cfg.show_closed:
        return []
    floor = now() - timedelta(days=max(1, cfg.closed_days))
    deleted_by = {
        note.issue.id: (note.actor, note.actor_face)
        for note in (notes or [])
        if note.type == "issueDeleted" and note.issue and note.actor
    }
    items = []
    for issue in sorted(work.done, key=lambda entry: entry.closed_at or entry.at, reverse=True):
        when = issue.closed_at or issue.at
        if (issue.open and not issue.trashed) or when < floor:
            continue
        verb = (
            "supprimé"
            if issue.trashed
            else "annulé"
            if issue.canceled
            else "marqué en doublon"
            if issue.state_type == "duplicate"
            else "terminé"
        )
        actor, face = deleted_by.get(issue.id, ("", "")) if issue.trashed else ("", "")
        actor = actor or issue.closed_by
        by = f"{verb} par @{actor}" if actor else verb
        items.append(
            _item(
                Kind.CLOSED,
                issue.id,
                issue.title,
                when,
                issue.url,
                issue=issue,
                detail=join(issue.identifier, by, since(when)),
                avatar=face or issue.closed_by_face or issue.creator_face or issue.assignee_face,
                hint=f"{by} le {when:%d/%m à %H:%M}",
            )
        )
    return items


def build_items(
    notes: list[Note],
    work: Work,
    me: str,
    cfg: Config,
    impersonating: bool = False,
) -> list[Item]:
    items: list[Item] = []
    if not impersonating:
        items += inbox_items(notes)
        items += filed_items(notes, cfg)
    items += mine_items(work)
    items += closed_items(work, cfg, notes)
    # Un invariant par badge : le rouge compte les sujets qui portent du non-lu, le violet ceux
    # qui sont lus sans être rangés. Le reste informe et ne compte nulle part.
    items = [
        replace(item, weight=0) if (not item.group.is_action or item.asleep) else item for item in items
    ]
    rank = {kind: index for index, kind in enumerate(ORDER)}
    items.sort(key=lambda item: (rank[item.kind], -item.at.timestamp()))
    return _dedupe(items)


def _dedupe(items: list[Item]) -> list[Item]:
    seen: set[str] = set()
    unique: list[Item] = []
    for item in items:
        if item.id in seen:
            continue
        seen.add(item.id)
        unique.append(item)
    return unique


def count_stale(notes: list[Note]) -> int:
    """Non-lues que Linear compte encore alors que leur ticket est à la corbeille.

    Son compteur les additionne, sa boîte ne les montre plus : les connaître est ce qui permet
    de ne pas afficher un « + » qui ne mènerait à rien.
    """
    return sum(1 for note in notes if note.unread and note.stale and not note.archived and not note.asleep)


def count_unread(notes: list[Note]) -> int:
    """Non-lues réellement dans la boîte, à l'unité près.

    Le badge, lui, compte des sujets : un ticket qui reçoit trois commentaires vaut un dans la
    barre et trois ici. C'est ce nombre-là qui se compare au compteur de Linear.
    """
    return sum(1 for note in notes if note.unread and not note.archived and not note.stale and not note.asleep)


def summarize(items: list[Item]) -> tuple[int, bool]:
    """Sujets de la boîte qui portent du non-lu, et présence d'une urgence : le badge rouge."""
    actions = [item for item in items if item.group.is_action and not item.warm]
    return sum(item.weight for item in actions), any(item.is_urgent for item in actions)


def summarize_warm(items: list[Item]) -> int:
    """Sujets lus mais toujours dans la boîte : le badge violet."""
    return sum(item.weight for item in items if item.warm)
