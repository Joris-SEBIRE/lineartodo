"""Configuration utilisateur, dans ~/.config/lineartodo/config.json."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

# Surchargeables pour tester sans toucher à la configuration et à l'état réels.
CONFIG_PATH = Path(os.environ.get("LINEARTODO_CONFIG") or Path.home() / ".config" / "lineartodo" / "config.json")
STATE_PATH = Path(
    os.environ.get("LINEARTODO_STATE")
    or Path.home() / "Library" / "Application Support" / "LinearTodo" / "state.json"
)

# Comptes dont les messages n'attendent jamais de réponse. Linear les expose en `botActor`,
# mais un collègue peut aussi avoir branché un compte de service : les noms se règlent ici.
DEFAULT_IGNORED = ["linear", "github", "gitlab", "sentry", "slack", "zapier", "intercom"]


@dataclass
class Config:
    # Clés d'équipe auxquelles se restreindre (« ENG », « OPS »). [] = tout ce que la clé voit,
    # ce qui est le cas normal : une boîte de réception n'a pas de périmètre.
    teams: list[str] = field(default_factory=list)
    # Personne observée : son `displayName` ou son e-mail Linear. null pour soi-même.
    view_as: str | None = None
    refresh_seconds: int = 20
    # La sonde ne voit pas tout : un commentaire lu ailleurs, une réaction posée depuis le
    # téléphone ne changent pas forcément le compte de non-lues. D'où une lecture complète
    # forcée à cet intervalle.
    full_refresh_seconds: int = 60
    # Mes tickets : lecture plus lourde (relations, commentaires) et plus lente à bouger que
    # la boîte de réception. Sa propre cadence.
    work_refresh_seconds: int = 120
    # Tickets clôturés : de l'histoire, plus ce qui se dit encore dessus.
    done_refresh_seconds: int = 300
    # Annuaire du workspace, pour le menu « voir en tant que ».
    people_refresh_seconds: int = 1800
    # Boîte de réception : Linear sert 50 notifications par page, lues et non lues mêlées. On
    # s'arrête dès que toutes les non-lues annoncées sont trouvées, ce plafond n'est qu'un
    # garde-fou pour une boîte très ancienne.
    inbox_pages: int = 4
    inbox_page_size: int = 50
    # Section d'historique : les notifications déjà lues, les plus récentes d'abord.
    show_read: bool = True
    read_days: int = 7
    read_rows: int = 12
    # Auteurs dont les commentaires ne déclenchent jamais un « à répondre ».
    ignored_actors: list[str] = field(default_factory=lambda: list(DEFAULT_IGNORED))
    # Sections déduites de mes tickets (en cours, bloqués, échéances, à démarrer).
    show_work: bool = True
    # Le backlog d'un dev actif compte des centaines de tickets : hors périmètre par défaut,
    # seuls le triage, « à faire » et « en cours » sont du travail engagé.
    include_backlog: bool = False
    # Au-delà, un message sans réponse est un message mort : plus personne ne l'attend.
    pending_days: int = 30
    # Au-delà, un ticket « en cours » est un ticket oublié.
    stale_days: int = 7
    due_soon_days: int = 3
    # Clés d'équipe dont on surveille la file de triage. [] = aucune : c'est du travail
    # d'équipe, pas du travail personnel, on ne l'impose pas.
    triage_teams: list[str] = field(default_factory=list)
    show_done: bool = True
    done_days: int = 14
    done_rows: int = 10
    # Fenêtre de la section « où je suis intervenu récemment ».
    touched_days: int = 7
    touched_rows: int = 10
    # Sections informatives (en cours, à démarrer, historique) affichées sous les actions.
    show_waiting: bool = True
    hide_when_zero: bool = False
    # Anneau de progression autour de la photo : il se remplit jusqu'au prochain cycle, ce qui
    # dit quand l'app va relire sans avoir à ouvrir le menu.
    show_refresh_ring: bool = True
    # Format de l'élément dans la barre : "avatar" (photo de l'identité + pastille de
    # comptage), "count" (nombre seul), "icon_count", "icon" (icône seule). Une barre saturée
    # évince les éléments les plus larges.
    badge_style: str = "avatar"
    # Commande qui imprime une clé d'API sur sa sortie standard.
    api_key_command: list[str] | None = None

    @classmethod
    def load(cls) -> "Config":
        known = {f.name for f in fields(cls)}
        data: dict = {}
        if CONFIG_PATH.exists():
            try:
                raw = json.loads(CONFIG_PATH.read_text() or "{}")
                data = {k: v for k, v in raw.items() if k in known}
            except (json.JSONDecodeError, OSError):
                data = {}
        cfg = cls(**data)
        # Réécrit le fichier quand des options apparaissent, pour qu'il reste exhaustif.
        if set(data) != known:
            cfg.save()
        return cfg

    def save(self) -> None:
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        CONFIG_PATH.write_text(json.dumps(asdict(self), indent=2, ensure_ascii=False) + "\n")

    def ignored(self) -> set[str]:
        return {name.lower() for name in self.ignored_actors}

    def team_keys(self) -> list[str]:
        return [key.strip().upper() for key in self.teams if key.strip()]

    def triage_keys(self) -> list[str]:
        return [key.strip().upper() for key in self.triage_teams if key.strip()]
