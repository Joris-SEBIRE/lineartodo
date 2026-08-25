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
    ANSWER = "answer"
    REPLIES = "replies"
    MENTION = "mention"
    ASSIGNED = "assigned"
    TRIAGE = "triage"
    ALERT = "alert"
    PULL_REQUEST = "pull_request"
    STATUS = "status"
    REACTION = "reaction"
    PROJECT_NEWS = "project_news"
    DOCUMENT = "document"
    CUSTOMER = "customer"
    REMINDER = "reminder"
    UNASSIGNED = "unassigned"
    OTHER = "other"
    SNOOZED = "snoozed"
    PENDING_REPLY = "pending_reply"
    OVERDUE = "overdue"
    BLOCKED = "blocked"
    STALE = "stale"
    DUE_SOON = "due_soon"
    BLOCKING = "blocking"
    IN_PROGRESS = "in_progress"
    TODO = "todo"
    TRIAGE_QUEUE = "triage_queue"
    CREATED_WAITING = "created_waiting"
    TOUCHED = "touched"
    READ = "read"
    RECENT_DONE = "recent_done"


@dataclass(frozen=True)
class Group:
    kind: Kind
    label: str
    symbol: str
    is_action: bool
    urgent: bool = False


GROUPS: dict[Kind, Group] = {
    Kind.ANSWER: Group(Kind.ANSWER, "On attend ma réponse", "bubble.left.and.bubble.right", True),
    Kind.REPLIES: Group(Kind.REPLIES, "Réponses et fils clos", "arrowshape.turn.up.left", True),
    Kind.MENTION: Group(Kind.MENTION, "On m'a nommé", "at", True),
    Kind.ASSIGNED: Group(Kind.ASSIGNED, "On m'a confié", "person.crop.circle.badge.checkmark", True),
    Kind.TRIAGE: Group(Kind.TRIAGE, "Arrivées en triage", "tray.and.arrow.down", True),
    Kind.ALERT: Group(Kind.ALERT, "Alertes", "exclamationmark.octagon", True, True),
    Kind.PULL_REQUEST: Group(Kind.PULL_REQUEST, "Pull requests", "arrow.triangle.pull", True),
    Kind.STATUS: Group(Kind.STATUS, "Changements de statut", "arrow.triangle.swap", True),
    Kind.REACTION: Group(Kind.REACTION, "Réactions", "hand.thumbsup", True),
    Kind.PROJECT_NEWS: Group(Kind.PROJECT_NEWS, "Projets et updates", "rectangle.stack", True),
    Kind.DOCUMENT: Group(Kind.DOCUMENT, "Documents", "doc.text", True),
    Kind.CUSTOMER: Group(Kind.CUSTOMER, "Clients", "person.2", True),
    Kind.REMINDER: Group(Kind.REMINDER, "Rappels", "bell", True),
    Kind.UNASSIGNED: Group(Kind.UNASSIGNED, "Retirées de moi", "person.crop.circle.badge.xmark", True),
    Kind.OTHER: Group(Kind.OTHER, "Autres notifications", "bell.badge", True),
    Kind.SNOOZED: Group(Kind.SNOOZED, "En sommeil", "moon.zzz", False),
    Kind.PENDING_REPLY: Group(
        Kind.PENDING_REPLY, "Messages restés sans réponse", "exclamationmark.bubble", False
    ),
    Kind.OVERDUE: Group(Kind.OVERDUE, "Échéance dépassée", "calendar.badge.exclamationmark", False, True),
    Kind.BLOCKED: Group(Kind.BLOCKED, "Mes tickets bloqués", "hand.raised", False),
    Kind.STALE: Group(Kind.STALE, "En cours sans activité", "hourglass", False),
    Kind.DUE_SOON: Group(Kind.DUE_SOON, "Échéances proches", "calendar", False),
    Kind.BLOCKING: Group(Kind.BLOCKING, "Mes tickets qui en bloquent d'autres", "exclamationmark.triangle", False),
    Kind.IN_PROGRESS: Group(Kind.IN_PROGRESS, "Mes tickets en cours", "play.circle", False),
    Kind.TODO: Group(Kind.TODO, "Mes tickets à démarrer", "circle.dashed", False),
    Kind.TRIAGE_QUEUE: Group(Kind.TRIAGE_QUEUE, "File de triage", "tray.full", False),
    Kind.CREATED_WAITING: Group(Kind.CREATED_WAITING, "Créés par moi, chez quelqu'un d'autre", "paperplane", False),
    Kind.TOUCHED: Group(Kind.TOUCHED, "Où je suis intervenu récemment", "clock.arrow.circlepath", False),
    Kind.READ: Group(Kind.READ, "Historique des notifications", "envelope.open", False),
    # Histoire, pas travail : en toute fin de menu. Ses lignes comptent malgré tout, dans la
    # pastille secondaire et non dans la rouge, tant qu'on ne les a pas ouvertes.
    Kind.RECENT_DONE: Group(Kind.RECENT_DONE, "Mes tickets récemment clôturés", "flag.checkered", False),
}

# L'ordre du menu est celui de ce dictionnaire : d'abord la boîte de réception, puis mes
# tickets, puis l'histoire. Renommer ou déplacer une section se fait ici, et nulle part ailleurs.
ORDER: list[Kind] = list(GROUPS)

# Nature d'une notification, d'après son `type`. Linear en compte plus de cent : celles qui
# n'y sont pas tombent dans la table des catégories, puis dans « Autres notifications ». Le
# total des lignes vaut donc toujours le nombre de non-lues, y compris quand Linear en invente.
BY_TYPE: dict[str, Kind] = {
    "issueNewComment": Kind.ANSWER,
    "documentNewComment": Kind.ANSWER,
    "projectNewComment": Kind.ANSWER,
    "projectUpdateNewComment": Kind.ANSWER,
    "projectMilestoneNewComment": Kind.ANSWER,
    "initiativeNewComment": Kind.ANSWER,
    "initiativeUpdateNewComment": Kind.ANSWER,
    "teamUpdateNewComment": Kind.ANSWER,
    "pullRequestCommented": Kind.ANSWER,
    "issueThreadResolved": Kind.REPLIES,
    "documentThreadResolved": Kind.REPLIES,
    "projectThreadResolved": Kind.REPLIES,
    "projectMilestoneThreadResolved": Kind.REPLIES,
    "initiativeThreadResolved": Kind.REPLIES,
    "issueMention": Kind.MENTION,
    "issueCommentMention": Kind.MENTION,
    "documentMention": Kind.MENTION,
    "documentCommentMention": Kind.MENTION,
    "projectMention": Kind.MENTION,
    "projectCommentMention": Kind.MENTION,
    "projectMilestoneMention": Kind.MENTION,
    "projectMilestoneCommentMention": Kind.MENTION,
    "projectUpdateMention": Kind.MENTION,
    "projectUpdateCommentMention": Kind.MENTION,
    "initiativeMention": Kind.MENTION,
    "initiativeCommentMention": Kind.MENTION,
    "initiativeUpdateMention": Kind.MENTION,
    "initiativeUpdateCommentMention": Kind.MENTION,
    "teamUpdateMention": Kind.MENTION,
    "teamUpdateCommentMention": Kind.MENTION,
    "agentConversationMention": Kind.MENTION,
    "pullRequestMention": Kind.MENTION,
    "pullRequestCommentMention": Kind.MENTION,
    "issueAssignedToYou": Kind.ASSIGNED,
    "projectAddedAsLead": Kind.ASSIGNED,
    "projectAddedAsMember": Kind.ASSIGNED,
    "documentAddedAsOwner": Kind.ASSIGNED,
    "initiativeAddedAsOwner": Kind.ASSIGNED,
    "customerAddedAsOwner": Kind.ASSIGNED,
    "issueUnassignedFromYou": Kind.UNASSIGNED,
    "documentRemovedAsOwner": Kind.UNASSIGNED,
    "issueAddedToTriage": Kind.TRIAGE,
    "triageResponsibilityIssueAddedToTriage": Kind.TRIAGE,
    "issueDue": Kind.ALERT,
    "issuePriorityUrgent": Kind.ALERT,
    "issueSlaBreached": Kind.ALERT,
    "issueSlaHighRisk": Kind.ALERT,
    "issueBlocking": Kind.ALERT,
    "pullRequestReviewRequested": Kind.PULL_REQUEST,
    "pullRequestReviewRerequested": Kind.PULL_REQUEST,
    "pullRequestApproved": Kind.PULL_REQUEST,
    "pullRequestChangesRequested": Kind.PULL_REQUEST,
    "pullRequestChecksFailed": Kind.PULL_REQUEST,
    "pullRequestRemovedFromMergeQueue": Kind.PULL_REQUEST,
    "issueStatusChanged": Kind.STATUS,
    "issueStatusChangedAll": Kind.STATUS,
    "issueReopened": Kind.STATUS,
    "issueUnblocked": Kind.STATUS,
    "issueEmojiReaction": Kind.REACTION,
    "issueCommentReaction": Kind.REACTION,
    "documentCommentReaction": Kind.REACTION,
    "projectCommentReaction": Kind.REACTION,
    "projectMilestoneCommentReaction": Kind.REACTION,
    "projectUpdateReaction": Kind.REACTION,
    "projectUpdateCommentReaction": Kind.REACTION,
    "initiativeCommentReaction": Kind.REACTION,
    "initiativeUpdateReaction": Kind.REACTION,
    "initiativeUpdateCommentReaction": Kind.REACTION,
    "teamUpdateReaction": Kind.REACTION,
    "teamUpdateCommentReaction": Kind.REACTION,
    "projectUpdateCreated": Kind.PROJECT_NEWS,
    "projectUpdatePrompt": Kind.PROJECT_NEWS,
    "initiativeUpdateCreated": Kind.PROJECT_NEWS,
    "initiativeUpdatePrompt": Kind.PROJECT_NEWS,
    "teamUpdateCreated": Kind.PROJECT_NEWS,
    "projectDescriptionContentChange": Kind.PROJECT_NEWS,
    "projectMilestoneDescriptionContentChange": Kind.PROJECT_NEWS,
    "initiativeDescriptionContentChange": Kind.PROJECT_NEWS,
    "documentContentChange": Kind.DOCUMENT,
    "documentMoved": Kind.DOCUMENT,
    "documentDeleted": Kind.DOCUMENT,
    "documentRestored": Kind.DOCUMENT,
    "customerNeedCreated": Kind.CUSTOMER,
    "customerNeedMarkedAsImportant": Kind.CUSTOMER,
    "customerNeedResolved": Kind.CUSTOMER,
    "issueReminder": Kind.REMINDER,
    "documentReminder": Kind.REMINDER,
    "projectReminder": Kind.REMINDER,
    "initiativeReminder": Kind.REMINDER,
}

# Repli par catégorie : Linear la sert sur toutes les notifications, quelle que soit leur
# nouveauté. Une catégorie inconnue tombe dans « Autres notifications ».
BY_CATEGORY: dict[str, Kind] = {
    "mentions": Kind.MENTION,
    "commentsAndReplies": Kind.ANSWER,
    "assignments": Kind.ASSIGNED,
    "triage": Kind.TRIAGE,
    "statusChanges": Kind.STATUS,
    "reactions": Kind.REACTION,
    "reviews": Kind.PULL_REQUEST,
    "postsAndUpdates": Kind.PROJECT_NEWS,
    "documentChanges": Kind.DOCUMENT,
    "customers": Kind.CUSTOMER,
    "reminders": Kind.REMINDER,
}

# Types d'état Linear, du plus loin au plus proche de la fin.
OPEN_STATES = ("triage", "backlog", "unstarted", "started")
CLOSED_STATES = ("completed", "canceled")
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
    priority: int = 0
    assignee: str = ""
    assignee_face: str = ""
    creator: str = ""
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

    @property
    def kind(self) -> Kind:
        found = BY_TYPE.get(self.type)
        if found is Kind.ANSWER and self.parent_comment_mine:
            # Une réponse dans un fil que j'ai ouvert : à lire, puis à clore.
            return Kind.REPLIES
        return found or BY_CATEGORY.get(self.category) or Kind.OTHER


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
    # Notification lue mais toujours dans la boîte : à faire, sans urgence. Elle compte dans
    # la pastille secondaire, pas dans la rouge, et les deux sommes valent chacune leur badge.
    warm: bool = False

    @property
    def group(self) -> Group:
        return GROUPS[self.kind]

    @property
    def is_urgent(self) -> bool:
        return self.group.urgent if self.urgent is None else self.urgent


@dataclass
class Work:
    """Mes tickets, tels que les recherches les rendent. Vide quand la lecture a échoué."""

    mine: list[Issue] = field(default_factory=list)
    created: list[Issue] = field(default_factory=list)
    touched: list[Issue] = field(default_factory=list)
    done: list[Issue] = field(default_factory=list)
    triage: list[Issue] = field(default_factory=list)

    def all(self) -> list[Issue]:
        return [*self.mine, *self.created, *self.touched, *self.done, *self.triage]


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

    @property
    def impersonating(self) -> bool:
        return bool(self.identity) and self.identity != self.viewer

    def actions(self) -> list[Item]:
        return [item for item in self.items if item.group.is_action]
