"""Règles de déduction : à partir de la boîte de réception et de mes tickets, ce qui m'attend.

Deux sources, deux rôles. La **boîte de réception** dit ce qui est arrivé et n'a pas été lu :
c'est elle, et elle seule, qui alimente la pastille rouge — une notification non lue vaut un.
Mes **tickets** disent l'état du travail : échéances, blocages, tickets en cours, et les
conversations que la boîte a déjà oubliées parce qu'on a lu le message sans y répondre.

Rien n'est jamais compté deux fois : un ticket dont une notification attend déjà ne réapparaît
pas dans les sections informatives.
"""

from __future__ import annotations

import re
from dataclasses import replace
from datetime import datetime, timedelta, timezone

from .config import Config
from .formatting import excerpt, join, since, until
from .models import (
    CLOSED_STATES,
    GROUPS,
    ORDER,
    Comment,
    Issue,
    Item,
    Kind,
    Note,
    Work,
)

MAX_CHIPS = 5
# Réactions qui valent accusé de réception : le point est acté, le message n'attend plus rien.
# Linear sert l'emoji brut ou son nom court selon l'origine du message, d'où les deux formes.
ACKNOWLEDGED = {"👍", "+1", "thumbsup", "👎", "-1", "thumbsdown", "✅", "white_check_mark", "heavy_check_mark"}
# Nature d'une notification en français, pour l'infobulle. Ce qui n'y est pas s'affiche sous
# son nom Linear : c'est moins beau, mais jamais faux.
TYPE_LABELS = {
    "issueNewComment": "commentaire",
    "issueCommentMention": "mention dans un message",
    "issueMention": "mention dans la description",
    "issueAssignedToYou": "assignation",
    "issueUnassignedFromYou": "désassignation",
    "issueStatusChanged": "changement de statut",
    "issueStatusChangedAll": "changement de statut",
    "issueReopened": "réouverture",
    "issueEmojiReaction": "réaction sur le ticket",
    "issueCommentReaction": "réaction sur un message",
    "issueAddedToTriage": "arrivée en triage",
    "issueThreadResolved": "fil clos",
    "issueDue": "échéance",
    "issueSlaBreached": "SLA dépassé",
    "issueSlaHighRisk": "SLA en danger",
    "issuePriorityUrgent": "passage en urgent",
    "issueBlocking": "ticket bloquant",
    "issueUnblocked": "déblocage",
    "issueReminder": "rappel",
    "projectUpdateCreated": "update de projet",
    "projectUpdatePrompt": "update de projet à écrire",
    "projectNewComment": "commentaire de projet",
    "projectUpdateNewComment": "commentaire sur un update",
    "projectDescriptionContentChange": "description de projet modifiée",
    "projectAddedAsLead": "projet confié",
    "projectAddedAsMember": "ajout à un projet",
    "documentMention": "mention dans un document",
    "documentNewComment": "commentaire de document",
    "documentContentChange": "document modifié",
    "issueSubscribed": "abonnement",
    "issueCreated": "création",
    "teamUpdateCreated": "update d'équipe",
    "pullRequestReviewRequested": "review demandée",
    "pullRequestApproved": "PR approuvée",
    "pullRequestChangesRequested": "changements demandés",
    "pullRequestChecksFailed": "CI en échec",
    "pullRequestCommented": "commentaire de PR",
}


def now() -> datetime:
    return datetime.now(timezone.utc)


def _acked(comment: Comment, me: str) -> bool:
    """Ai-je acté ce message d'une réaction ? Un point acté n'attend plus rien."""
    return any(
        (emoji or "").strip().lower() in ACKNOWLEDGED and (not me or author == me)
        for emoji, author in comment.reactions
    )


def _spoken_by(comment: Comment, me: str) -> bool:
    """Est-ce moi qui parle ? Le nom d'affichage sert dans les deux modes.

    `isMe` ne vaut que pour le propriétaire de la clé : en « voir en tant que », il désignerait
    la mauvaise personne. Le nom, lui, est le même partout.
    """
    return comment.author == me or (comment.is_mine and not me)


def _humans(comments: tuple[Comment, ...], ignored: set[str]) -> list[Comment]:
    return [
        comment
        for comment in comments
        if not comment.is_bot and comment.author.lower() not in ignored
    ]


def _threads(comments: list[Comment]) -> tuple[list[list[Comment]], list[Comment]]:
    """Les fils de discussion, et la liste plate des messages de premier niveau.

    Linear pose les messages racine à plat et les réponses dessous : répondre dans un fil
    répond au fil, alors que reprendre la parole en bas du ticket ne répond à personne en
    particulier. Les deux ne se jugent donc pas de la même façon.
    """
    roots = [comment for comment in comments if not comment.parent_id]
    children: dict[str, list[Comment]] = {}
    for comment in comments:
        if comment.parent_id:
            children.setdefault(comment.parent_id, []).append(comment)
    threads = []
    for root in roots:
        if kids := children.get(root.id):
            threads.append([root, *sorted(kids, key=lambda entry: entry.created_at)])
    orphans = [
        comment
        for comment in comments
        if comment.parent_id and comment.parent_id not in {root.id for root in roots}
    ]
    return threads, roots + orphans


def _pending(thread: list[Comment], me: str) -> list[Comment]:
    """Messages des autres depuis ma dernière prise de parole dans ce fil.

    Une réaction posée dessus vaut réponse : le point est acté, il n'y a plus à y revenir.
    """
    spoke = [index for index, comment in enumerate(thread) if _spoken_by(comment, me)]
    after = thread[spoke[-1] + 1 :] if spoke else thread
    return [comment for comment in after if not _spoken_by(comment, me) and not _acked(comment, me)]


def _names(body: str, me: str) -> bool:
    """`@moi` dans un message, sous les deux écritures de Linear.

    Linear enregistre une mention en `@[Nom](/profiles/…)` dans le corps, et le nom court
    passe tel quel : les deux doivent être reconnus.
    """
    if not me:
        return False
    return re.search(rf"@\[?[^\]\s]*{re.escape(me)}", body or "", re.IGNORECASE) is not None


def _flat_pending(flat: list[Comment], me: str) -> list[Comment]:
    """Messages du bas du ticket qui attendent encore quelque chose de moi.

    Reprendre la parole en bas d'un ticket répond à ce qui précède : la liste est
    chronologique, et personne n'y attend une réponse à un message que j'ai enjambé — sauf
    s'il me nomme. Être nommé est une sollicitation qui ne se dissout pas parce que j'ai parlé
    d'autre chose ensuite ; seule une réponse citée ou une réaction l'éteint.
    """
    spoke = [index for index, comment in enumerate(flat) if _spoken_by(comment, me)]
    last = spoke[-1] if spoke else -1
    quoted = [
        " ".join(comment.quoted.split()).lower()
        for comment in flat
        if _spoken_by(comment, me) and comment.quoted
    ]

    def answered(comment: Comment) -> bool:
        gist = " ".join(comment.body.split()).lower()[:80]
        return bool(gist) and any(gist[:40] in quote for quote in quoted)

    return [
        comment
        for index, comment in enumerate(flat)
        if not _spoken_by(comment, me)
        and (index > last or _names(comment.body, me))
        and not answered(comment)
        and not _acked(comment, me)
    ]


def _chips(issue: Issue | None, moment: datetime | None = None) -> tuple[tuple[str, str], ...]:
    """Drapeaux d'état du ticket, sans nombre : ils ne comptent aucune notification."""
    if issue is None:
        return ()
    flags: list[tuple[str, str]] = []
    if issue.priority == 1:
        flags.append(("exclamationmark.octagon", ""))
    if issue.due is not None and issue.due < (moment or now()):
        flags.append(("calendar.badge.exclamationmark", ""))
    if issue.blockers:
        flags.append(("hand.raised", ""))
    if issue.sla_at is not None and issue.sla_at < (moment or now()):
        flags.append(("timer", ""))
    if issue.state_type == "started":
        flags.append(("play.circle", ""))
    elif issue.state_type == "triage":
        flags.append(("tray", ""))
    elif issue.state_type in CLOSED_STATES:
        flags.append(("checkmark.circle" if issue.completed else "xmark.circle", ""))
    return tuple(flags)


def _tag(issue: Issue | None) -> str:
    """L'unique état qui doit sauter aux yeux, quand il y en a un."""
    if issue is None:
        return ""
    if issue.due is not None and issue.due < now():
        return "en retard"
    if issue.sla_at is not None and issue.sla_at < now():
        return "SLA"
    if issue.priority == 1:
        return "urgent"
    if issue.blockers:
        return "bloqué"
    return ""


def _route(issue: Issue | None) -> str:
    if issue is None:
        return ""
    return join(issue.team_name or issue.team, issue.project, issue.cycle)


def _item(
    kind: Kind,
    key: str,
    title: str,
    at: datetime,
    url: str,
    *,
    issue: Issue | None = None,
    detail: str = "",
    counted: tuple[tuple[str, int], ...] = (),
    weight: int | None = None,
    **extra,
) -> Item:
    """Une ligne : titre en haut, métadonnées uniformes en dessous.

    `counted` porte les pastilles chiffrées, celles qui décomposent la pastille de la barre. Le
    poids en est déduit, ce qui garantit par construction que les nombres d'une ligne
    s'additionnent jusqu'au badge. Les drapeaux d'état viennent après, sans nombre.
    """
    countable = GROUPS[kind].is_action or bool(extra.get("warm"))
    if countable and not counted and weight is None:
        counted = ((GROUPS[kind].symbol, 1),)
    numbered = tuple((symbol, str(number)) for symbol, number in counted if number)
    taken = {symbol for symbol, _ in numbered}
    flags = tuple(flag for flag in _chips(issue) if flag[0] not in taken)
    total = sum(number for _, number in counted) if countable else 0
    return Item(
        id=f"{kind.value}:{key}",
        kind=kind,
        title=title or "(sans titre)",
        detail=detail,
        url=url,
        at=at,
        fingerprint=f"{key}:{at.isoformat()}",
        team=issue.team if issue else "",
        ident=issue.identifier if issue else "",
        weight=total if weight is None else weight,
        chips=(numbered + flags)[:MAX_CHIPS],
        route=_route(issue),
        tag=_tag(issue),
        **extra,
    )


def _subject(note: Note) -> str:
    if note.issue:
        return note.issue.title
    if note.title:
        return note.title
    return note.entity or TYPE_LABELS.get(note.type, note.type)


def _meta(note: Note) -> str:
    """Métadonnées d'une notification : où, de qui, depuis quand, dans quel état.

    Hors ticket, Linear titre souvent la notification du nom de l'entité : répéter ce nom en
    dessous ne dirait rien. On y met alors la nature de l'événement.
    """
    who = f"@{note.actor}" if note.actor else ""
    if note.issue:
        return join(note.issue.identifier, who, since(note.updated_at), note.issue.state)
    nature = TYPE_LABELS.get(note.type, note.type)
    entity = note.entity if note.entity and note.entity.split(" ", 1)[-1] not in note.title else ""
    return join(entity or nature, who, since(note.updated_at))


# Natures de notification qui portent une conversation : elles seules rendent inutile la
# relecture des messages du ticket.
TALKING = (Kind.ANSWER, Kind.REPLIES, Kind.MENTION)


def inbox_items(notes: list[Note], cfg: Config) -> tuple[list[Item], set[str], set[str]]:
    """Les notifications, regroupées par sujet : une ligne par ticket, par nature et par chaleur.

    La boîte de réception *est* la liste de ce qu'il reste à faire, et Linear le dit en trois
    états : non lue, c'est chaud ; lue mais toujours dans la boîte, c'est à faire sans urgence ;
    rangée, c'est fait. Les deux premiers comptent, chacun dans sa pastille, et leur somme est
    exactement ce que la boîte contient.

    Une ligne ne mélange jamais les deux chaleurs : un ticket qui a du neuf et du déjà-lu donne
    deux lignes, une rouge et une bleue, parce qu'elles ne demandent pas la même chose.
    """
    items: list[Item] = []
    covered: set[str] = set()
    talked: set[str] = set()
    # Clé de regroupement : la nature, le sujet, et la chaleur.
    groups: dict[tuple[Kind, str, bool], list[Note]] = {}
    asleep: list[Note] = []
    filed: list[Note] = []
    for note in notes:
        if note.archived:
            filed.append(note)  # rangée dans l'inbox : c'est fait, il en reste l'histoire
        elif note.asleep:
            asleep.append(note)  # remise à plus tard par Linear : elle ne compte pas d'ici là
        else:
            groups.setdefault((note.kind, note.key, note.unread), []).append(note)
    for (kind, key, hot), batch in groups.items():
        batch.sort(key=lambda entry: entry.updated_at)
        latest = max(entry.updated_at for entry in batch)
        first = batch[0]
        # Un visage par personne, dans l'ordre où elle s'est manifestée.
        faces: dict[str, str] = {}
        for note in batch:
            if note.actor_face:
                faces.setdefault(note.actor, note.actor_face)
        natures: dict[str, int] = {}
        for note in batch:
            nature = TYPE_LABELS.get(note.type, note.type)
            natures[nature] = natures.get(nature, 0) + 1
        issue = next((note.issue for note in batch if note.issue), None)
        if issue is not None:
            # Chaude ou tiède, la notification est là : inutile de relire les messages du
            # ticket pour retrouver ce qu'elle porte déjà.
            covered.add(issue.id)
            if kind in TALKING:
                talked.add(issue.id)
        body = next((excerpt(note.comment.body) for note in batch if note.comment and note.comment.body), "")
        who = ", ".join(f"@{name}" for name in faces) or "Linear"
        state = "non lue(s)" if hot else "lue(s), pas encore rangée(s)"
        items.append(
            _item(
                kind,
                f"{key}:{'hot' if hot else 'warm'}",
                _subject(first),
                latest,
                first.url,
                issue=issue,
                detail=join(_meta(first), body),
                counted=((GROUPS[kind].symbol, len(batch)),),
                avatar=first.actor_face,
                faces=tuple(faces.values()),
                warm=not hot,
                hint=f"{len(batch)} notification(s) {state} de {who} : "
                + ", ".join(f"{count} × {nature}" for nature, count in natures.items()),
            )
        )
    items += _asleep_items(asleep)
    items += _read_items(filed, cfg)
    return items, covered, talked


def _asleep_items(notes: list[Note]) -> list[Item]:
    """Notifications mises en sommeil : Linear les cache, l'app dit quand elles reviennent."""
    items = []
    for note in sorted(notes, key=lambda entry: entry.snoozed_until or entry.updated_at):
        wake = note.snoozed_until
        items.append(
            _item(
                Kind.SNOOZED,
                note.id,
                _subject(note),
                note.updated_at,
                note.url,
                issue=note.issue,
                detail=join(_meta(note), f"réveil {until(wake)}" if wake else ""),
                avatar=note.actor_face,
                weight=0,
                hint="en sommeil : elle ne compte pas tant qu'elle n'est pas revenue",
            )
        )
    return items


def _read_items(notes: list[Note], cfg: Config) -> list[Item]:
    """L'histoire de la boîte : ce qui a été rangé dans Linear, du plus récent au plus ancien."""
    if not cfg.show_read:
        return []
    floor = now() - timedelta(days=max(1, cfg.read_days))

    def when(note: Note) -> datetime:
        return note.read_at or note.archived_at or note.updated_at

    kept = [note for note in notes if when(note) > floor]
    # Groupées par sujet : vingt notifications sur le même ticket sont une ligne, pas vingt.
    # Sans cela l'historique d'un ticket bavard chasse tous les autres de la liste.
    groups: dict[str, list[Note]] = {}
    for note in sorted(kept, key=when, reverse=True):
        groups.setdefault(note.key, []).append(note)
    items = []
    for key, batch in groups.items():
        latest = batch[0]
        natures: dict[str, int] = {}
        for note in batch:
            nature = TYPE_LABELS.get(note.type, note.type)
            natures[nature] = natures.get(nature, 0) + 1
        faces: dict[str, str] = {}
        for note in reversed(batch):
            if note.actor_face:
                faces.setdefault(note.actor, note.actor_face)
        items.append(
            _item(
                Kind.READ,
                key,
                _subject(latest),
                when(latest),
                latest.url,
                issue=latest.issue,
                detail=join(_meta(latest), ", ".join(natures)),
                counted=((GROUPS[Kind.READ].symbol, len(batch)),),
                weight=0,
                avatar=latest.actor_face,
                faces=tuple(faces.values()),
                hint=f"{len(batch)} notification(s) rangée(s) : "
                + ", ".join(f"{count} × {nature}" for nature, count in natures.items()),
            )
        )
    return items


def _issue_meta(issue: Issue, extra: str = "", at: datetime | None = None) -> str:
    who = f"@{issue.assignee}" if issue.assignee else "sans assigné"
    return join(issue.identifier, who, since(at or issue.at), issue.state, extra)


def _issue_item(kind: Kind, issue: Issue, hint: str, extra: str = "", **more) -> Item:
    return _item(
        kind,
        issue.id,
        issue.title,
        issue.at,
        issue.url,
        issue=issue,
        detail=_issue_meta(issue, extra),
        avatar=issue.assignee_face,
        weight=0,
        hint=hint,
        **more,
    )


def work_items(work: Work, me: str, cfg: Config, covered: set[str]) -> list[Item]:
    """Mes tickets : une seule ligne par ticket, dans la section qui dit ce qui le retient.

    L'ordre des cas est l'ordre de ce qui commande : une échéance dépassée passe devant un
    blocage, un blocage devant l'inactivité, l'inactivité devant le simple « en cours ».
    """
    moment = now()
    stale_floor = moment - timedelta(days=max(1, cfg.stale_days))
    soon = moment + timedelta(days=max(1, cfg.due_soon_days))
    items: list[Item] = []
    seen = set(covered)
    for issue in sorted(work.mine, key=lambda entry: entry.at, reverse=True):
        if issue.id in seen or not issue.open:
            continue
        seen.add(issue.id)
        blockers = issue.blockers
        if issue.due is not None and issue.due < moment:
            items.append(_issue_item(Kind.OVERDUE, issue, f"échéance {until(issue.due)}", urgent=True))
        elif blockers:
            names = ", ".join(link.other for link in blockers)
            items.append(
                _issue_item(Kind.BLOCKED, issue, f"bloqué par {names}", extra=f"bloqué par {names}")
            )
        elif issue.state_type == "started" and issue.at < stale_floor:
            items.append(_issue_item(Kind.STALE, issue, f"en cours, sans activité {since(issue.at)}"))
        elif issue.due is not None and issue.due < soon:
            items.append(_issue_item(Kind.DUE_SOON, issue, f"échéance {until(issue.due)}"))
        elif issue.blocks:
            names = ", ".join(link.other for link in issue.blocks)
            items.append(_issue_item(Kind.BLOCKING, issue, f"bloque {names}", extra=f"bloque {names}"))
        elif issue.state_type == "started":
            items.append(_issue_item(Kind.IN_PROGRESS, issue, "en cours, rien ne le retient"))
        else:
            items.append(_issue_item(Kind.TODO, issue, f"{issue.state} : pas encore démarré"))
    for issue in sorted(work.created, key=lambda entry: entry.at, reverse=True):
        if issue.id in seen or not issue.open or issue.assignee == me:
            continue
        seen.add(issue.id)
        who = f"@{issue.assignee}" if issue.assignee else "personne"
        items.append(_issue_item(Kind.CREATED_WAITING, issue, f"créé par toi, {who} l'a en main"))
    for issue in sorted(work.triage, key=lambda entry: entry.at, reverse=True):
        if issue.id in seen:
            continue
        seen.add(issue.id)
        items.append(_issue_item(Kind.TRIAGE_QUEUE, issue, f"en triage dans {issue.team}"))
    touched = 0
    for issue in sorted(work.touched, key=lambda entry: entry.at, reverse=True):
        if issue.id in seen or touched >= max(1, cfg.touched_rows):
            continue
        seen.add(issue.id)
        touched += 1
        items.append(_issue_item(Kind.TOUCHED, issue, "tu y as parlé ou tu le suis, et il a bougé"))
    return items


def conversation_items(issues: list[Issue], me: str, cfg: Config, covered: set[str]) -> list[Item]:
    """Messages restés sans réponse, que la boîte de réception a déjà oubliés.

    Une notification lue disparaît du compte, même si la question qu'elle portait n'a jamais eu
    de réponse. C'est là que les demandes se perdent : ces lignes les rattrapent. Sur un ticket
    clôturé, la ligne compte dans la pastille secondaire — plus rien ne la ramènera autrement.

    Deux bornes, sans quoi la section devient un cimetière : une fenêtre de temps, parce qu'une
    question de trois mois que personne n'a relancée n'attend plus rien ; et le fait que le
    ticket soit à moi, ou qu'un des messages me nomme. Un échange entre deux collègues sur un
    ticket où j'ai parlé une fois ne m'attend pas.
    """
    ignored = cfg.ignored()
    floor = now() - timedelta(days=max(1, cfg.pending_days))
    items: list[Item] = []
    for issue in issues:
        if issue.id in covered or not issue.comments:
            continue
        humans = _humans(issue.comments, ignored)
        if not humans:
            continue
        threads, flat = _threads(humans)
        waiting: list[Comment] = []
        for thread in threads:
            if thread[0].resolved:
                continue  # un fil clos est un point traité
            waiting += _pending(thread, me)
        # Les messages de premier niveau qui ouvrent un fil sont déjà jugés dans leur fil.
        in_threads = {comment.id for thread in threads for comment in thread}
        waiting += _flat_pending([comment for comment in flat if comment.id not in in_threads], me)
        waiting = [comment for comment in waiting if comment.created_at > floor]
        if not waiting:
            continue
        mine = me in (issue.assignee, issue.creator)
        if not mine and not any(_names(comment.body, me) for comment in waiting):
            continue
        oldest = min(waiting, key=lambda comment: comment.created_at)
        latest = max(comment.created_at for comment in waiting)
        closed = not issue.open
        faces: dict[str, str] = {}
        for comment in sorted(waiting, key=lambda entry: entry.created_at):
            faces.setdefault(comment.author, comment.author_face)
        who = ", ".join(f"@{name}" for name in faces)
        items.append(
            _item(
                Kind.PENDING_REPLY,
                issue.id,
                issue.title,
                latest,
                oldest.url or issue.url,
                issue=issue,
                detail=join(_issue_meta(issue, at=oldest.created_at), excerpt(oldest.body)),
                weight=0,
                avatar=oldest.author_face,
                faces=tuple(faces.values()),
                hint=f"{len(waiting)} message(s) de {who} sans réponse de ta part"
                + (" — sur un ticket clôturé" if closed else " — la boîte les a déjà rangés"),
            )
        )
    return items


def done_items(issues: list[Issue], me: str, cfg: Config) -> list[Item]:
    """Mes tickets sortis du périmètre ouvert : qui les a clôturés, et quand.

    De l'histoire, pas du travail : la ligne ne compte dans aucune pastille. Le point ● suffit
    à signaler qu'une clôture est arrivée depuis la dernière ouverture du menu.
    """
    floor = now() - timedelta(days=max(1, cfg.done_days))
    items = []
    for issue in sorted(issues, key=lambda entry: entry.closed_at or entry.at, reverse=True):
        when = issue.closed_at or issue.at
        if when < floor or issue.open:
            continue
        verb = "annulé" if issue.canceled else "terminé"
        by = f"{verb} par @{issue.closed_by}" if issue.closed_by else verb
        items.append(
            _item(
                Kind.RECENT_DONE,
                issue.id,
                issue.title,
                when,
                issue.url,
                issue=issue,
                detail=join(issue.identifier, by, since(when), issue.state),
                weight=0,
                avatar=issue.closed_by_face or issue.assignee_face,
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
    items, covered, talked = inbox_items(notes, cfg) if not impersonating else ([], set(), set())
    # Les conversations d'abord : un ticket dont un message attend une réponse se dit mieux
    # ainsi qu'en « en cours », donc il ne réapparaît pas plus bas.
    talk = conversation_items([issue for issue in [*work.mine, *work.created, *work.touched] if issue.open], me, cfg, talked)
    if cfg.show_done:
        talk += conversation_items([issue for issue in work.done if not issue.open], me, cfg, talked)
    items += talk
    if cfg.show_work:
        items += work_items(work, me, cfg, covered | {item.id.split(":", 1)[-1] for item in talk})
    if cfg.show_done:
        items += done_items(work.done, me, cfg)
    if not cfg.show_waiting:
        items = [item for item in items if item.group.is_action]
    # Deux invariants, un par badge : la somme des pastilles rouges vaut le badge rouge, celle
    # des secondes le badge secondaire. Une ligne informative ne compte dans aucun des deux.
    items = [item if item.group.is_action else replace(item, weight=0) for item in items]
    rank = {kind: index for index, kind in enumerate(ORDER)}
    # Le chaud avant le tiède : dans une section, ce qui n'a pas encore été vu passe devant.
    items.sort(key=lambda item: (rank[item.kind], item.warm, -item.at.timestamp()))
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


def summarize(items: list[Item]) -> tuple[int, bool]:
    """Somme des notifications non lues, et présence d'une urgence : c'est le badge rouge."""
    actions = [item for item in items if item.group.is_action and not item.warm]
    return sum(item.weight for item in actions), any(item.is_urgent for item in actions)


def summarize_warm(items: list[Item]) -> int:
    """Somme des notifications lues qui traînent encore dans la boîte : le badge secondaire, à la couleur de l'app."""
    return sum(item.weight for item in items if item.warm)
