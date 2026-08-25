"""Accès Linear en lecture seule : une API GraphQL, une clé personnelle, aucune mutation."""

from __future__ import annotations

import getpass
import json
import os
import subprocess
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

from .config import CONFIG_PATH, Config
from .models import (
    CLOSED_STATES,
    Comment,
    Issue,
    Note,
    OPEN_STATES,
    Person,
    Relation,
    Work,
    initials_face,
    parse_day,
    parse_ts,
)
from .queries import (
    DONE_QUERY,
    INBOX_FALLBACK,
    INBOX_QUERY,
    ORDER_QUERY,
    PEOPLE_QUERY,
    PROBE_FALLBACK,
    PROBE_QUERY,
    WHO,
    WORK_QUERY,
)

API = "https://api.linear.app/graphql"
STATUS_PAGE = "https://linearstatus.com"
KEY_FILE = CONFIG_PATH.parent / "token"
KEYCHAIN_SERVICE = "lineartodo"
# Une clé personnelle Linear commence par ce préfixe et s'envoie telle quelle ; un jeton
# OAuth, lui, se présente en porteur.
KEY_PREFIX = "lin_api_"
EPOCH = datetime.fromtimestamp(0, tz=timezone.utc)
# Linear plafonne à 5 000 requêtes et 3 000 000 points de complexité par heure et par clé.
MAX_PEOPLE = 250


class LinearError(Exception):
    """Échec d'un appel Linear, avec de quoi le qualifier : 5xx, refus, réseau, quota.

    Le code et le document servent à dire *quoi* est dégradé, pas seulement que ça a échoué.
    """

    def __init__(self, message: str, status: int | None = None, path: str = "") -> None:
        super().__init__(message)
        self.status = status
        self.path = path

    @property
    def kind(self) -> str:
        """Nature de l'échec, parce que le remède n'est pas le même.

        Le quota se règle en attendant le réarmement horaire, un refus en changeant la clé,
        une panne en attendant Linear. Les confondre enverrait chercher au mauvais endroit, et
        le quota n'est pas une panne de Linear : c'est notre propre consommation.
        """
        text = str(self).lower()
        if self.status == 429 or "rate limit" in text or "ratelimited" in text:
            return "quota"
        if self.status is not None and self.status >= 500:
            return "panne"
        if self.status in (401, 403, 404):
            return "refus"
        if self.status is None:
            return "réseau"
        return "erreur"


def _run(cmd: list[str]) -> str | None:
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout.strip() or None if out.returncode == 0 else None


def _person(node: dict | None) -> Person | None:
    if not node:
        return None
    return Person(
        id=node.get("id") or "",
        display_name=node.get("displayName") or node.get("name") or "?",
        name=node.get("name") or "",
        email=node.get("email") or "",
        avatar=node.get("avatarUrl") or "",
        initials=node.get("initials") or "",
        colour=node.get("avatarBackgroundColor") or "",
        active=bool(node.get("active", True)),
        is_bot=bool(node.get("app")),
        status=" ".join(part for part in [node.get("statusEmoji") or "", node.get("statusLabel") or ""] if part),
        last_seen=parse_ts(node.get("lastSeen")),
    )


def _face_of(node: dict | None) -> str:
    who = _person(node)
    return who.face if who else ""


def _comment(node: dict | None) -> Comment | None:
    if not node:
        return None
    author = _person(node.get("user"))
    bot = (node.get("botActor") or {}).get("name") or ""
    parent = node.get("parent") or {}
    parent_author = (parent.get("user") or {}).get("displayName") or ""
    return Comment(
        id=node.get("id") or "",
        author=author.display_name if author else (bot or "inconnu"),
        author_face=author.face if author else initials_face((bot or "?")[:2], "#8a8f98"),
        created_at=parse_ts(node.get("createdAt")) or EPOCH,
        url=node.get("url") or "",
        body=(node.get("body") or "").strip(),
        is_bot=bool(bot) or bool((node.get("user") or {}).get("app")),
        is_mine=bool((node.get("user") or {}).get("isMe")),
        resolved=bool(node.get("resolvedAt")),
        parent_id=node.get("parentId") or parent.get("id") or "",
        parent_author=parent_author,
        quoted=node.get("quotedText") or "",
        reactions=tuple(
            ((entry.get("emoji") or ""), ((entry.get("user") or {}).get("displayName") or ""))
            for entry in (node.get("reactions") or [])
        ),
    )


def _relations(node: dict) -> tuple[tuple[Relation, ...], tuple[Relation, ...]]:
    """Ce que ce ticket bloque, et ce qui le bloque.

    Un enregistrement de relation va du ticket source vers le ticket lié : `relations` porte
    ceux que je bloque, `inverseRelations` ceux qui me bloquent. C'est la seule lecture qui
    distingue « j'attends quelqu'un » de « quelqu'un m'attend ».
    """
    mine, against = [], []
    for entry in ((node.get("relations") or {}).get("nodes") or []):
        other = entry.get("relatedIssue") or {}
        mine.append(
            Relation(
                type=entry.get("type") or "",
                other=other.get("identifier") or "",
                title=(other.get("title") or "").strip(),
                state=((other.get("state") or {}).get("type") or ""),
                assignee=((other.get("assignee") or {}).get("displayName") or ""),
            )
        )
    for entry in ((node.get("inverseRelations") or {}).get("nodes") or []):
        other = entry.get("issue") or {}
        if (entry.get("type") or "") != "blocks":
            continue  # « duplicate » ou « related » ne contraignent aucun travail
        against.append(
            Relation(
                type="blocks",
                other=other.get("identifier") or "",
                title=(other.get("title") or "").strip(),
                state=((other.get("state") or {}).get("type") or ""),
                assignee=((other.get("assignee") or {}).get("displayName") or ""),
            )
        )
    return tuple(mine), tuple(against)


def _issue(node: dict | None, source: str = "") -> Issue | None:
    if not node:
        return None
    state = node.get("state") or {}
    team = node.get("team") or {}
    cycle = node.get("cycle") or {}
    assignee = _person(node.get("assignee"))
    relations, blocked_by = _relations(node)
    comments = tuple(
        found for found in (_comment(entry) for entry in ((node.get("comments") or {}).get("nodes") or [])) if found
    )
    faces = {comment.author: comment.author_face for comment in comments if comment.author_face}
    if assignee:
        faces.setdefault(assignee.display_name, assignee.face)
    closed_by, closed_face = "", ""
    for entry in ((node.get("history") or {}).get("nodes") or []):
        target = (entry.get("toState") or {}).get("type") or ""
        if target in CLOSED_STATES and entry.get("actor"):
            closed_by = (entry["actor"].get("displayName") or "").strip()
            closed_face = _face_of(entry["actor"])
    return Issue(
        id=node.get("id") or "",
        identifier=node.get("identifier") or "",
        title=(node.get("title") or "").strip(),
        url=node.get("url") or "",
        team=team.get("key") or "",
        team_name=team.get("name") or "",
        state=state.get("name") or "",
        state_type=state.get("type") or "",
        priority=int(node.get("priority") or 0),
        assignee=assignee.display_name if assignee else "",
        assignee_face=assignee.face if assignee else "",
        creator=((node.get("creator") or {}).get("displayName") or ""),
        project=((node.get("project") or {}).get("name") or ""),
        cycle=(f"cycle {int(cycle['number'])}" if cycle.get("number") is not None else ""),
        parent=((node.get("parent") or {}).get("identifier") or ""),
        estimate=node.get("estimate"),
        due=parse_day(node.get("dueDate")),
        created_at=parse_ts(node.get("createdAt")),
        updated_at=parse_ts(node.get("updatedAt")),
        started_at=parse_ts(node.get("startedAt")),
        closed_at=parse_ts(node.get("completedAt")) or parse_ts(node.get("canceledAt")),
        snoozed_until=parse_ts(node.get("snoozedUntilAt")),
        sla_at=parse_ts(node.get("slaBreachesAt")),
        completed=bool(node.get("completedAt")),
        canceled=bool(node.get("canceledAt")),
        comments=comments,
        relations=relations,
        blocked_by=blocked_by,
        closed_by=closed_by,
        closed_by_face=closed_face,
        faces=faces,
        sources={source} if source else set(),
    )


def _note(node: dict) -> Note:
    issue = _issue(node.get("issue")) or _issue(node.get("relatedIssue"))
    comment = _comment(node.get("comment"))
    parent = node.get("parentComment") or {}
    entity, entity_key, url = "", "", node.get("url") or ""
    for field, label in (("project", "projet"), ("initiative", "initiative"), ("customer", "client")):
        block = node.get(field) or {}
        if block:
            entity = f"{label} {block.get('name') or ''}".strip()
            entity_key = block.get("id") or ""
            url = url or block.get("url") or ""
    if not url:
        url = (comment.url if comment else "") or (issue.url if issue else "")
    return Note(
        id=node.get("id") or "",
        type=node.get("type") or "",
        category=node.get("category") or "",
        created_at=parse_ts(node.get("createdAt")) or EPOCH,
        updated_at=parse_ts(node.get("updatedAt")) or parse_ts(node.get("createdAt")) or EPOCH,
        read_at=parse_ts(node.get("readAt")),
        archived_at=parse_ts(node.get("archivedAt")),
        snoozed_until=parse_ts(node.get("snoozedUntilAt")),
        title=(node.get("title") or "").strip(),
        subtitle=(node.get("subtitle") or "").strip(),
        url=url,
        actor=((node.get("actor") or {}).get("displayName") or (node.get("botActor") or {}).get("name") or ""),
        actor_face=(
            _face_of(node.get("actor"))
            or ((node.get("botActor") or {}).get("avatarUrl") or "")
            or initials_face(((node.get("botActor") or {}).get("name") or "?")[:2], "#8a8f98")
        ),
        issue=issue,
        comment=comment,
        parent_comment_mine=bool((parent.get("user") or {}).get("isMe")),
        reaction=node.get("reactionEmoji") or "",
        entity=entity,
        entity_key=entity_key,
    )


def who_filter(user_id: str | None) -> dict:
    """Filtre d'utilisateur : moi, ou la personne observée.

    Une seule fonction pour les deux, sinon chaque recherche aurait sa variante « en tant que »
    et l'une finirait par oublier la bascule.
    """
    return {"id": {"eq": user_id}} if user_id else {"isMe": {"eq": True}}


def _iso(days: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=max(1, days))).isoformat()


def _scoped(cfg: Config, base: dict) -> dict:
    keys = cfg.team_keys()
    return {"and": [base, {"team": {"key": {"in": keys}}}]} if keys else base


def work_variables(cfg: Config, user_id: str | None, rows: int = 40) -> dict:
    """Les quatre recherches de tickets, périmètre et personne observée compris.

    « Où je suis intervenu » prend la parole et l'abonnement, mais seulement sur des tickets
    encore ouverts : un ticket clôturé relève de l'histoire, pas du suivi. Ce que la section
    montre au bout du compte est le reste — ce dont je suis partie sans que ce soit déjà sur
    ma pile.
    """
    who = who_filter(user_id)
    states = list(OPEN_STATES) if cfg.include_backlog else [state for state in OPEN_STATES if state != "backlog"]
    triage_keys = cfg.triage_keys()
    return {
        "n": max(5, min(rows, 100)),
        "mine": _scoped(cfg, {"assignee": who, "state": {"type": {"in": states}}}),
        "created": _scoped(cfg, {"creator": who, "state": {"type": {"in": states}}}),
        "touched": _scoped(
            cfg,
            {
                "and": [
                    {"or": [{"comments": {"some": {"user": who}}}, {"subscribers": {"some": who}}]},
                    {"state": {"type": {"in": states}}},
                    {"updatedAt": {"gt": _iso(cfg.touched_days)}},
                ]
            },
        ),
        "triage": {"team": {"key": {"in": triage_keys}}, "state": {"type": {"eq": "triage"}}},
        "wantTriage": bool(triage_keys),
    }


def done_variables(cfg: Config, user_id: str | None) -> dict:
    """Les tickets sortis du périmètre ouvert : les miens, et ceux que j'ai ouverts."""
    who = who_filter(user_id)
    return {
        "n": max(5, min(cfg.done_rows * 3, 50)),
        "done": _scoped(
            cfg,
            {
                "and": [
                    {"or": [{"assignee": who}, {"creator": who}]},
                    {"state": {"type": {"in": list(CLOSED_STATES)}}},
                    {"updatedAt": {"gt": _iso(cfg.done_days)}},
                ]
            },
        ),
    }


class Linear:
    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg
        self._key: str | None = None
        self.key_origin = ""
        self.requests_left: int | None = None
        self.complexity_left: int | None = None
        # `notificationsUnreadCount` est marqué interne par Linear : au premier refus, on
        # cesse de le demander et la sonde se passe du compte officiel.
        self.counts_unread = True
        # Idem pour les champs de présentation (`title`, `url`, `category`) de la boîte.
        self.rich_inbox = True
        # Sens de pagination des notifications, mesuré une fois : None tant qu'on ne sait pas.
        self.newest_first: bool | None = None

    def key(self, refresh: bool = False) -> str:
        if self._key and not refresh:
            return self._key
        self._key, self.key_origin = None, ""
        if self.cfg.api_key_command:
            self._key = _run(list(self.cfg.api_key_command))
            self.key_origin = "api_key_command (réglage)"
        if not self._key:
            self._key = _run(
                ["/usr/bin/security", "find-generic-password", "-a", getpass.getuser(), "-s", KEYCHAIN_SERVICE, "-w"]
            )
            self.key_origin = f"trousseau macOS (service « {KEYCHAIN_SERVICE} »)"
        if not self._key and KEY_FILE.exists():
            self._key = KEY_FILE.read_text().strip() or None
            self.key_origin = str(KEY_FILE)
        if not self._key:
            self._key = os.environ.get("LINEAR_API_KEY") or os.environ.get("LINEAR_TOKEN")
            self.key_origin = "variable d'environnement LINEAR_API_KEY / LINEAR_TOKEN"
        if not self._key:
            self.key_origin = ""
            raise LinearError(
                "Aucune clé d'API Linear. Crée-la sur linear.app/settings/account/security, puis "
                f"`security add-generic-password -a \"$USER\" -s {KEYCHAIN_SERVICE} -w '<clé>'`, "
                f"ou écris-la dans {KEY_FILE}."
            )
        return self._key

    def _authorization(self) -> str:
        key = self.key()
        return key if key.startswith(KEY_PREFIX) else f"Bearer {key}"

    def _remember_limits(self, headers) -> None:
        for name, attribute in (
            ("X-RateLimit-Requests-Remaining", "requests_left"),
            ("X-RateLimit-Complexity-Remaining", "complexity_left"),
        ):
            raw = headers.get(name)
            if raw is None:
                continue
            try:
                setattr(self, attribute, int(raw))
            except (TypeError, ValueError):
                continue

    def graphql(self, document: str, variables: dict, name: str = "") -> dict:
        body = json.dumps({"query": document, "variables": variables}).encode()
        request = urllib.request.Request(API, data=body, method="POST")
        request.add_header("Authorization", self._authorization())
        request.add_header("Content-Type", "application/json")
        request.add_header("User-Agent", "LinearTodo")
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                self._remember_limits(response.headers)
                payload = json.loads(response.read() or b"null") or {}
        except urllib.error.HTTPError as exc:
            self._remember_limits(exc.headers)
            detail = (exc.read() or b"").decode()[:200]
            if exc.code == 401:
                self.key(refresh=True)
            raise LinearError(f"Linear {exc.code} sur {name or 'graphql'} : {detail}", status=exc.code, path=name) from exc
        except urllib.error.URLError as exc:
            raise LinearError(f"Réseau indisponible ({exc.reason})", path=name) from exc
        except TimeoutError as exc:
            # urllib lève TimeoutError sans l'emballer dans URLError : sans cette branche, une
            # lenteur réseau tuait le cycle au lieu d'être une panne passagère.
            raise LinearError("Délai dépassé côté réseau", path=name) from exc
        if errors := payload.get("errors"):
            message = "; ".join(str(entry.get("message") or "?") for entry in errors)[:300]
            raise LinearError(f"GraphQL : {message}", path=name)
        return payload.get("data") or {}

    def newest_page(self, size: int, cursor: str | None = None) -> dict:
        """Arguments de pagination qui ramènent les notifications les plus récentes.

        Linear ne dit pas dans quel sens il trie : quand c'est du plus ancien au plus récent,
        on remonte la liste par la fin. Sans cela, l'app afficherait fidèlement la boîte
        d'il y a trois ans.
        """
        if self.newest_first is False:
            return {"first": None, "last": size, "after": None, "before": cursor}
        return {"first": size, "last": None, "after": cursor, "before": None}

    def learn_order(self) -> bool:
        """Mesure le sens du tri, une fois, et le retient pour la durée du processus."""
        if self.newest_first is not None:
            return self.newest_first
        try:
            data = self.graphql(ORDER_QUERY, {}, "sens de tri")
        except LinearError:
            self.newest_first = True  # au pire, le comportement Relay le plus répandu
            return self.newest_first

        def newest(block) -> str:
            return max((node.get("updatedAt") or "" for node in ((block or {}).get("nodes") or [])), default="")

        head, tail = newest(data.get("head")), newest(data.get("tail"))
        self.newest_first = head >= tail
        return self.newest_first

    def probe(self) -> tuple[str, int | None]:
        """Empreinte de la boîte de réception, pour quelques points au lieu de plusieurs cents.

        L'empreinte porte aussi `readAt` : lire une notification depuis le téléphone ou depuis
        l'app doit faire tomber le compte ici aussi, pas seulement l'arrivée d'une nouvelle.
        """
        self.learn_order()
        page = self.newest_page(max(5, min(self.cfg.inbox_page_size, 50)))
        variables = {"first": page["first"], "last": page["last"]}
        if self.counts_unread:
            try:
                data = self.graphql(PROBE_QUERY, variables, "sonde")
            except LinearError as exc:
                if exc.kind != "erreur":
                    raise
                self.counts_unread = False
                data = self.graphql(PROBE_FALLBACK, variables, "sonde")
        else:
            data = self.graphql(PROBE_FALLBACK, variables, "sonde")
        nodes = ((data.get("notifications") or {}).get("nodes") or [])
        signature = "|".join(
            f"{node.get('id')}:{node.get('updatedAt')}:{node.get('readAt') or ''}:{node.get('archivedAt') or ''}"
            for node in nodes
            if node
        )
        return signature, data.get("notificationsUnreadCount")

    def fetch_inbox(self, wanted: int | None = None) -> tuple[list[Note], Person | None, list[str], int | None]:
        """Boîte de réception, page par page, jusqu'à tenir toutes les non-lues.

        Linear sert les lues et les non-lues mêlées, sans filtre sur `readAt` : on pagine
        jusqu'à ce que le compte officiel soit atteint, ce qui tient en une page dans le cas
        normal. Le plafond de pages existe pour ne pas dérouler une boîte de plusieurs années.

        `wanted` est le compte annoncé par la sonde, qui vient de le lire : le redemander
        coûterait une requête pour la même réponse.
        """
        self.learn_order()
        size = max(10, min(self.cfg.inbox_page_size, 100))
        if wanted is None and self.counts_unread:
            try:
                wanted = self.graphql("query { notificationsUnreadCount }", {}, "compte des non-lues").get(
                    "notificationsUnreadCount"
                )
            except LinearError as exc:
                if exc.kind in ("panne", "réseau", "quota", "refus"):
                    raise
                self.counts_unread = False
        notes: list[Note] = []
        viewer: Person | None = None
        cursor, truncated, more = None, [], False
        for _ in range(max(1, self.cfg.inbox_pages)):
            document = INBOX_QUERY if self.rich_inbox else INBOX_FALLBACK
            variables = self.newest_page(size, cursor)
            try:
                data = self.graphql(document, variables, "boîte de réception")
            except LinearError as exc:
                if self.rich_inbox and exc.kind == "erreur":
                    # Un champ de présentation a disparu : on repart sans eux plutôt que de
                    # laisser la boîte inaccessible.
                    self.rich_inbox = False
                    data = self.graphql(INBOX_FALLBACK, variables, "boîte de réception")
                else:
                    raise
            viewer = viewer or _person(data.get("viewer"))
            block = data.get("notifications") or {}
            notes += [_note(node) for node in (block.get("nodes") or []) if node]
            page_info = block.get("pageInfo") or {}
            backward = self.newest_first is False
            more = bool(page_info.get("hasPreviousPage" if backward else "hasNextPage"))
            cursor = page_info.get("startCursor" if backward else "endCursor")
            unread = sum(1 for note in notes if note.unread and not note.archived)
            enough_read = sum(1 for note in notes if note.archived or not note.unread) >= self.cfg.read_rows
            if not more or (wanted is not None and unread >= wanted and enough_read):
                break
        unread = sum(1 for note in notes if note.unread and not note.archived)
        if wanted is not None and unread < wanted:
            truncated.append(f"{wanted} non-lues annoncées, {unread} lues dans les {len(notes)} plus récentes")
        elif wanted is None and more:
            truncated.append(f"{len(notes)} notifications lues, les plus anciennes ignorées")
        return notes, viewer, truncated, wanted

    def fetch_work(self, user_id: str | None, rows: int = 40) -> tuple[Work, list[str]]:
        """Mes tickets : ce qui m'est assigné, ce que j'ai créé, ce où je suis intervenu."""
        variables = work_variables(self.cfg, user_id, rows)
        data = self.graphql(WORK_QUERY, variables, "mes tickets")
        work, truncated = Work(), []
        for source, target in (("mine", "mine"), ("created", "created"), ("touched", "touched"), ("triage", "triage")):
            block = data.get(source) or {}
            found = [issue for issue in (_issue(node, source) for node in (block.get("nodes") or [])) if issue]
            getattr(work, target).extend(found)
            if (block.get("pageInfo") or {}).get("hasNextPage"):
                truncated.append(f"{source} : plus de {len(found)} tickets, la liste est écrêtée")
        return work, truncated

    def fetch_done(self, user_id: str | None) -> tuple[list[Issue], list[str]]:
        """Tickets sortis du périmètre ouvert, et ce qui s'y dit encore."""
        variables = done_variables(self.cfg, user_id)
        data = self.graphql(DONE_QUERY, variables, "tickets clôturés")
        block = data.get("done") or {}
        found = [issue for issue in (_issue(node, "done") for node in (block.get("nodes") or [])) if issue]
        truncated = []
        if (block.get("pageInfo") or {}).get("hasNextPage"):
            truncated.append("clôturés : la fenêtre en contient plus que la liste")
        return found, truncated

    def fetch_viewer(self) -> Person | None:
        """Le propriétaire de la clé. La boîte de réception le donne déjà : c'est pour les
        cycles où on ne la lit pas, en « voir en tant que »."""
        document = "query Me { viewer { ...Who email } }" + WHO
        return _person(self.graphql(document, {}, "identité").get("viewer"))

    def fetch_people(self) -> list[Person]:
        """Membres actifs du workspace, les plus récemment vus d'abord."""
        data = self.graphql(PEOPLE_QUERY, {"n": MAX_PEOPLE}, "annuaire")
        found = [
            person
            for person in (_person(node) for node in ((data.get("users") or {}).get("nodes") or []))
            if person and not person.is_bot
        ]
        found.sort(key=lambda person: (person.name or person.display_name).lower())
        found.sort(key=lambda person: person.last_seen or EPOCH, reverse=True)
        return found

    def find_person(self, wanted: str) -> Person | None:
        """La personne désignée par un handle, un e-mail ou un nom, sans charger l'annuaire."""
        needle = wanted.strip()
        if not needle:
            return None
        document = (
            "query Find($who: UserFilter!) { users(first: 5, filter: $who) { nodes { ...Who email active app } } }"
            + WHO
        )
        variables = {
            "who": {
                "or": [
                    {"displayName": {"eqIgnoreCase": needle}},
                    {"email": {"eqIgnoreCase": needle}},
                    {"name": {"eqIgnoreCase": needle}},
                ]
            }
        }
        nodes = ((self.graphql(document, variables, "recherche de personne").get("users") or {}).get("nodes") or [])
        for node in nodes:
            person = _person(node)
            if person and person.answers_to(needle):
                return person
        return _person(nodes[0]) if nodes else None
