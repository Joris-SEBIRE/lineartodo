"""Requêtes Linear : la boîte de réception, mes tickets, et l'annuaire du workspace.

Les filtres ne sont pas écrits ici mais passés en variables (`IssueFilter`), pour qu'un
changement de périmètre ou de personne observée ne demande pas un second document.
"""

# Les notifications traitées dans l'inbox de Linear sont archivées, pas supprimées : sans
# `includeArchived`, la boîte ne rend que ce qui reste à traiter et l'historique est vide. On
# demande tout, et c'est l'app qui trie ce qui compte de ce qui est déjà rangé.
INCLUDE_ARCHIVED = "includeArchived: true"

# Dans quel sens Linear pagine ses notifications. Rien ne le dit dans le schéma, et se
# tromper afficherait les plus vieilles au lieu des plus fraîches : une requête, une fois par
# lancement, tranche la question au lieu de la supposer.
ORDER_QUERY = """
query Order {
  head: notifications(first: 2, includeArchived: true, orderBy: updatedAt) { nodes { updatedAt } }
  tail: notifications(last: 2, includeArchived: true, orderBy: updatedAt) { nodes { updatedAt } }
}
"""

# Sonde : le compte de non-lues annoncé par Linear, et de quoi savoir si la boîte a bougé.
# Quelques points de complexité, contre plusieurs centaines pour la lecture complète.
PROBE_QUERY = """
query Probe($first: Int, $last: Int) {
  notificationsUnreadCount
  notifications(first: $first, last: $last, includeArchived: true, orderBy: updatedAt) {
    nodes { id updatedAt readAt archivedAt }
  }
}
"""

# Même sonde, sans le compte : `notificationsUnreadCount` est marqué interne par Linear, donc
# susceptible de disparaître. Le jour où il refuse, l'app garde une sonde qui marche.
PROBE_FALLBACK = """
query ProbeLight($first: Int, $last: Int) {
  notifications(first: $first, last: $last, includeArchived: true, orderBy: updatedAt) {
    nodes { id updatedAt readAt archivedAt }
  }
}
"""

WHO = """
fragment Who on User {
  id displayName name avatarUrl avatarBackgroundColor initials
}
"""

# Un message : le corps, qui l'a écrit, ce qu'il cite, et les réactions posées dessus.
# `quotedText`
# est ce que Linear enregistre quand on répond en citant : la citation n'est pas à deviner
# dans le corps du message, elle est donnée.
WORD = """
fragment Word on Comment {
  id url body createdAt resolvedAt quotedText parentId
  parent { id user { id displayName isMe } }
  user { ...Who isMe app }
  botActor { name }
  reactions { emoji user { displayName isMe } }
}
"""

TASK = """
fragment Task on Issue {
  id identifier title url priority estimate dueDate trashed
  createdAt updatedAt startedAt completedAt canceledAt snoozedUntilAt slaBreachesAt
  state { name type color }
  team { key name }
  assignee { ...Who }
  creator { ...Who }
  project { name }
  cycle { number name }
  parent { identifier }
  inverseRelations(first: 6) {
    nodes { type issue { identifier title state { type } assignee { displayName } } }
  }
}
"""

INBOX_QUERY = (
    """
query Inbox($first: Int, $last: Int, $after: String, $before: String) {
  viewer { ...Who email }
  notifications(
    first: $first, last: $last, after: $after, before: $before
    includeArchived: true, orderBy: updatedAt
  ) {
    pageInfo { hasNextPage endCursor hasPreviousPage startCursor }
    nodes { ...Note }
  }
}
fragment Note on Notification {
  id type category createdAt updatedAt readAt archivedAt snoozedUntilAt title subtitle url
  actor { ...Who }
  botActor { name avatarUrl }
  ... on IssueNotification {
    reactionEmoji
    team { key name }
    issue { ...Brief }
    comment { ...Word }
    parentComment { id user { id displayName isMe } }
  }
  ... on ProjectNotification {
    project { id name url }
    projectUpdate { id url }
    comment { ...Word }
  }
  ... on InitiativeNotification {
    initiative { id name url }
    comment { ...Word }
  }
  ... on DocumentNotification { documentId }
  ... on PostNotification { postId }
  ... on CustomerNotification { customer { id name url } }
  ... on CustomerNeedNotification { relatedIssue { ...Brief } }
}
fragment Brief on Issue {
  id identifier title url priority dueDate updatedAt completedAt canceledAt slaBreachesAt trashed
  state { name type color }
  team { key name }
  assignee { ...Who }
  project { name }
  cycle { number name }
}
"""
    + WHO
    + WORD
)

# Mes tickets ouverts. Une seule recherche : ce qui m'est assigné et qui n'est pas clos.
WORK_QUERY = (
    """
query Work($mine: IssueFilter!, $n: Int!) {
  mine: issues(filter: $mine, first: $n, orderBy: updatedAt) {
    pageInfo { hasNextPage } nodes { ...Task }
  }
}
"""
    + TASK
    + WHO
)

# Tickets sortis du périmètre ouvert. `history` donne la main qui a clôturé : Linear n'expose
# pas de `completedBy`, seul l'historique dit qui a bougé l'état.
DONE_QUERY = (
    """
query Done($done: IssueFilter!, $n: Int!) {
  done: issues(filter: $done, first: $n, orderBy: updatedAt, includeArchived: true) {
    pageInfo { hasNextPage }
    nodes {
      ...Ending
      # `history` est trié du plus récent au plus ancien : `first` prend les dernières
      # transitions, `last` prendrait celles de la création du ticket.
      history(first: 8) { nodes { createdAt actor { ...Who } botActor { name } toState { name type } } }
    }
  }
}
fragment Ending on Issue {
  id identifier title url priority dueDate trashed
  createdAt updatedAt startedAt completedAt canceledAt
  state { name type color }
  team { key name }
  assignee { ...Who }
  creator { ...Who }
  project { name }
  cycle { number name }
}
"""
    + WHO
)

# Même lecture, sans les champs que Linear marque internes (`title`, `subtitle`, `url`,
# `category`). Ils rendent le menu plus fidèle à l'app, mais l'app doit survivre au jour où
# ils disparaissent : le titre se reconstruit alors depuis le ticket, la nature depuis le
# seul `type`, et l'URL depuis le ticket ou le message.
INBOX_FALLBACK = (
    """
query InboxLean($first: Int, $last: Int, $after: String, $before: String) {
  viewer { ...Who email }
  notifications(
    first: $first, last: $last, after: $after, before: $before
    includeArchived: true, orderBy: updatedAt
  ) {
    pageInfo { hasNextPage endCursor hasPreviousPage startCursor }
    nodes { ...Note }
  }
}
fragment Note on Notification {
  id type createdAt updatedAt readAt archivedAt snoozedUntilAt
  actor { ...Who }
  botActor { name avatarUrl }
  ... on IssueNotification {
    reactionEmoji
    team { key name }
    issue { ...Brief }
    comment { ...Word }
    parentComment { id user { id displayName isMe } }
  }
  ... on ProjectNotification { project { id name url } comment { ...Word } }
  ... on InitiativeNotification { initiative { id name url } comment { ...Word } }
  ... on CustomerNeedNotification { relatedIssue { ...Brief } }
}
fragment Brief on Issue {
  id identifier title url priority dueDate updatedAt completedAt canceledAt slaBreachesAt trashed
  state { name type color }
  team { key name }
  assignee { ...Who }
  project { name }
  cycle { number name }
}
"""
    + WHO
    + WORD
)

PEOPLE_QUERY = (
    """
query People($n: Int!) {
  users(first: $n, filter: { active: { eq: true } }, orderBy: updatedAt) {
    nodes { ...Who email active app guest lastSeen statusEmoji statusLabel }
  }
}
"""
    + WHO
)
