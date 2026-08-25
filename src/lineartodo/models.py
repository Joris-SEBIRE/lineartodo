"""Domaine : ce qu'on lit de Linear et ce qu'on en déduit à faire."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum


def parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def parse_day(value: str | None) -> datetime | None:
    """`dueDate` est une date sans heure : on la place à la fin de la journée, en local.

    Une échéance au 12 est dépassée le 13 au matin, pas le 12 à minuit une.
    """
    if not value:
        return None
    try:
        day = datetime.fromisoformat(str(value)[:10])
    except ValueError:
        return None
    return day.replace(hour=23, minute=59, second=59).astimezone(timezone.utc)


EPOCH = datetime.fromtimestamp(0, tz=timezone.utc)


class Kind(str, Enum):
    INBOX = "inbox"
    FILED = "filed"
    MINE = "mine"
    CLOSED = "closed"


@dataclass(frozen=True)
class Group:
    kind: Kind
    label: str
    symbol: str
    is_action: bool
    urgent: bool = False


GROUPS: dict[Kind, Group] = {
    Kind.INBOX: Group(Kind.INBOX, "Ma boîte de réception", "tray.full", True),
    Kind.MINE: Group(Kind.MINE, "Tickets qui me sont assignés", "checklist", False),
    Kind.FILED: Group(Kind.FILED, "Notifications archivées", "archivebox", False),
    Kind.CLOSED: Group(Kind.CLOSED, "Tickets clos ou supprimés", "flag.checkered", False),
}

# L'ordre du menu est celui de ce dictionnaire, du plus utile au moins utile : ce qui attend une
# réponse, le travail en cours, puis les deux histoires — celle de la boîte, celle des tickets.
# On ne descend dans le menu que pour retrouver quelque chose, jamais pour savoir quoi faire.
ORDER: list[Kind] = list(GROUPS)

# Nature d'un événement, en français, pour la ligne et son infobulle. Ce qui n'y est pas
# s'affiche sous son nom Linear : moins beau, jamais faux.
EVENTS: dict[str, str] = {
    "issueNewComment": "commentaire",
    "issueCommentMention": "mention dans un message",
    "issueMention": "mention",
    "issueAssignedToYou": "assignation",
    "issueUnassignedFromYou": "désassignation",
    "issueStatusChanged": "changement de statut",
    "issueStatusChangedAll": "changement de statut",
    "issueReopened": "réouverture",
    "issueDeleted": "ticket supprimé",
    "issueEmojiReaction": "réaction",
    "issueCommentReaction": "réaction",
    "issueAddedToTriage": "arrivée en triage",
    "issueThreadResolved": "fil clos",
    "issueDue": "échéance",
    "issueSlaBreached": "SLA dépassé",
    "issueSlaHighRisk": "SLA en danger",
    "issuePriorityUrgent": "passage en urgent",
    "issueBlocking": "ticket bloquant",
    "issueUnblocked": "déblocage",
    "issueSubscribed": "abonnement",
    "issueUnsubscribed": "désabonnement",
    "issueCreated": "création",
    "issueReminder": "rappel",
    "projectUpdateCreated": "update de projet",
    "projectUpdatePrompt": "update de projet à écrire",
    "projectNewComment": "commentaire de projet",
    "projectDescriptionContentChange": "description de projet modifiée",
    "projectAddedAsLead": "projet confié",
    "projectAddedAsMember": "ajout à un projet",
    "documentMention": "mention dans un document",
    "documentNewComment": "commentaire de document",
    "documentContentChange": "document modifié",
    "teamUpdateCreated": "update d'équipe",
    "pullRequestReviewRequested": "review demandée",
    "pullRequestApproved": "PR approuvée",
    "pullRequestChangesRequested": "changements demandés",
    "pullRequestChecksFailed": "CI en échec",
    "pullRequestCommented": "commentaire de PR",
}


def event_label(kind: str) -> str:
    return EVENTS.get(kind, kind)


# Types d'état Linear, du plus loin au plus proche de la fin.
OPEN_STATES = ("triage", "backlog", "unstarted", "started")
CLOSED_STATES = ("completed", "canceled", "duplicate")
# Priorité Linear : 0 aucune, 1 urgent, 2 haute, 3 moyenne, 4 basse.
PRIORITY_LABELS = {1: "urgent", 2: "haute", 3: "moyenne", 4: "basse"}


@dataclass(frozen=True)
class Person:
    id: str
    display_name: str
    name: str = ""
    email: str = ""
    avatar: str = ""
    initials: str = ""
    colour: str = ""
    active: bool = True
    is_bot: bool = False
    status: str = ""
    last_seen: datetime | None = None

    @property
    def label(self) -> str:
        return f"{self.name} (@{self.display_name})" if self.name else f"@{self.display_name}"

    @property
    def face(self) -> str:
        """Photo de profil, ou initiales sur fond coloré à défaut.

        Beaucoup de comptes Linear n'ont pas d'image : sans ce repli, la moitié des lignes
        n'aurait aucun visage. Les initiales et la couleur viennent de Linear, donc le menu
        montre les mêmes pastilles que l'app.
        """
        return self.avatar or initials_face(self.initials or self.display_name[:2], self.colour)

    def answers_to(self, wanted: str) -> bool:
        """Reconnaît une personne à son handle, son e-mail ou son nom, sans casse."""
        needle = wanted.strip().lower()
        return needle in {
            self.display_name.lower(),
            self.email.lower(),
            self.name.lower(),
            self.id.lower(),
        }


def initials_face(initials: str, colour: str) -> str:
    """Pseudo-URL d'un visage dessiné localement : `initials:JS:#5e6ad2`.

    Passer par la même plomberie que les photos évite un second chemin de rendu dans le menu :
    le cache et la mise en page ne savent rien de la différence.
    """
    return "initials:" + (initials or "?").upper()[:2] + ":" + (colour or "#5e6ad2")


@dataclass(frozen=True)
class Comment:
    id: str
    author: str
    author_face: str
    created_at: datetime
    url: str
    body: str
    is_bot: bool = False
    is_mine: bool = False
    resolved: bool = False
    parent_id: str = ""
    parent_author: str = ""
    quoted: str = ""
    # Réactions posées sur ce message, par qui : un 👍 de la personne observée vaut accusé de
    # réception. Le « moi » de Linear est celui de la clé, qui n'est pas forcément la personne
    # observée, d'où le nom plutôt que le drapeau.
    reactions: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class Relation:
    """Lien entre deux tickets. `blocks` est le seul qui porte une contrainte de travail."""

    type: str
    other: str  # identifiant lisible, « ENG-142 »
    title: str
    state: str  # type d'état de l'autre ticket
    assignee: str = ""

    @property
    def open(self) -> bool:
        return self.state not in CLOSED_STATES


@dataclass
class Issue:
    id: str
    identifier: str
    title: str
    url: str
    team: str
    team_name: str = ""
    state: str = ""
    state_type: str = ""
    # Couleur de l'état, telle que Linear la donne : la même pastille que dans son interface.
    colour: str = ""
    priority: int = 0
    assignee: str = ""
    assignee_face: str = ""
    creator: str = ""
    creator_face: str = ""
    project: str = ""
    cycle: str = ""
    parent: str = ""
    estimate: float | None = None
    due: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    started_at: datetime | None = None
    closed_at: datetime | None = None
    snoozed_until: datetime | None = None
    sla_at: datetime | None = None
    completed: bool = False
    canceled: bool = False
    # Ticket mis à la corbeille : Linear le retire de ses listes et de sa boîte de réception,
    # mais les notifications qui le visaient survivent dans l'API.
    trashed: bool = False
    comments: tuple[Comment, ...] = ()
    relations: tuple[Relation, ...] = ()
    blocked_by: tuple[Relation, ...] = ()
    # Dernier changement d'état connu, et par la main de qui.
    closed_by: str = ""
    closed_by_face: str = ""
    faces: dict[str, str] = field(default_factory=dict)
    sources: set[str] = field(default_factory=set)

    @property
    def at(self) -> datetime:
        return self.updated_at or self.created_at or EPOCH

    @property
    def open(self) -> bool:
        return self.state_type in OPEN_STATES

    @property
    def blockers(self) -> tuple[Relation, ...]:
        return tuple(link for link in self.blocked_by if link.open)

    @property
    def blocks(self) -> tuple[Relation, ...]:
        return tuple(link for link in self.relations if link.type == "blocks" and link.open)


@dataclass
class Note:
    """Une notification de la boîte de réception, quelle que soit son espèce."""

    id: str
    type: str
    category: str
    created_at: datetime
    updated_at: datetime
    read_at: datetime | None
    archived_at: datetime | None
    snoozed_until: datetime | None
    title: str
    subtitle: str
    url: str
    actor: str = ""
    actor_face: str = ""
    issue: Issue | None = None
    comment: Comment | None = None
    parent_comment_mine: bool = False
    reaction: str = ""
    # Entité visée quand ce n'est pas un ticket : projet, document, initiative.
    entity: str = ""
    entity_key: str = ""

    @property
    def unread(self) -> bool:
        return self.read_at is None

    @property
    def stale(self) -> bool:
        """Le sujet de la notification est parti à la corbeille.

        Linear laisse alors la notification non lue dans son API, tout en la retirant de sa
        boîte de réception : la compter afficherait un « à faire » que rien ne peut éteindre,
        et son lien ouvre un ticket supprimé.
        """
        return bool(self.issue and self.issue.trashed)

    @property
    def archived(self) -> bool:
        """Rangée : traiter une notification dans l'inbox de Linear l'archive.

        Une notification archivée sans avoir été lue ne compte pas non plus — Linear ne la
        compte pas davantage. C'est l'inbox qui fait foi, pas le drapeau « lu ».
        """
        return self.archived_at is not None

    @property
    def asleep(self) -> bool:
        """En sommeil : Linear la retire de la boîte jusqu'à son réveil."""
        return self.snoozed_until is not None and self.snoozed_until > datetime.now(timezone.utc)

    @property
    def key(self) -> str:
        """Sujet auquel rattacher la ligne : un ticket, sinon l'entité visée."""
        return self.issue.id if self.issue else (self.entity_key or self.id)


@dataclass(frozen=True)
class Item:
    id: str
    kind: Kind
    title: str
    detail: str
    url: str
    at: datetime
    fingerprint: str
    team: str = ""
    # Identifiant lisible du ticket (« ENG-142 »), pour la variante « copier l'identifiant ».
    ident: str = ""
    # Visage de la personne concernée par la ligne (auteur du message, ou assigné du ticket).
    avatar: str = ""
    # Toutes les personnes concernées, la première à avoir parlé en tête. `avatar` reste la
    # principale : c'est elle qu'on affiche seule quand il n'y en a qu'une.
    faces: tuple[str, ...] = ()
    # Nombre de notifications portées par la ligne. 0 pour les lignes informatives.
    weight: int = 1
    # État du ticket résumé en pastilles (symbole SF, nombre ou libellé éventuel).
    chips: tuple[tuple[str, str], ...] = ()
    # Explication au survol : ce que la pastille compte, et pourquoi la ligne est là.
    hint: str = ""
    # « équipe · projet · cycle », affiché sous les métadonnées.
    route: str = ""
    # Étiquette dessinée en tête des métadonnées, pour un état qui doit sauter aux yeux.
    tag: str = ""
    # None = l'urgence par défaut de la catégorie.
    urgent: bool | None = None
    # Sujet lu mais toujours dans la boîte : à faire, sans urgence. Il compte dans la pastille
    # secondaire, pas dans la rouge, et les deux sommes valent chacune leur badge.
    warm: bool = False
    # Tout ce que le sujet porte est en sommeil : la ligne reste visible, sans compter nulle part.
    asleep: bool = False

    @property
    def group(self) -> Group:
        return GROUPS[self.kind]

    @property
    def is_urgent(self) -> bool:
        return self.group.urgent if self.urgent is None else self.urgent


@dataclass
class Work:
    """Mes tickets, tels que les deux recherches les rendent. Vides si la lecture a échoué."""

    mine: list[Issue] = field(default_factory=list)
    done: list[Issue] = field(default_factory=list)

    def all(self) -> list[Issue]:
        return [*self.mine, *self.done]


@dataclass
class Snapshot:
    items: list[Item]
    viewer: str = ""
    # Identité observée : le propriétaire de la clé, ou la personne du mode « voir en tant que ».
    identity: str = ""
    fetched_at: datetime | None = None
    # Restes annoncés par Linear dans les en-têtes : requêtes, puis points de complexité.
    requests_left: int | None = None
    complexity_left: int | None = None
    error: str | None = None
    truncated: list[str] = field(default_factory=list)
    people: tuple[Person, ...] = ()
    # Compte de non-lues annoncé par Linear : la vérité contre laquelle on se mesure.
    unread_total: int | None = None
    # Non-lues que Linear compte encore mais dont le ticket est à la corbeille : elles
    # expliquent l'écart entre son compteur et le nôtre.
    stale: int = 0

    @property
    def impersonating(self) -> bool:
        return bool(self.identity) and self.identity != self.viewer

    def actions(self) -> list[Item]:
        return [item for item in self.items if item.group.is_action]
