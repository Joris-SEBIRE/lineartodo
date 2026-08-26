"""Configuration utilisateur, dans ~/.config/lineartodo/config.json."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from types import UnionType
from typing import Union, get_args, get_origin, get_type_hints

# Surchargeables pour tester sans toucher à la configuration et à l'état réels.
CONFIG_PATH = Path(os.environ.get("LINEARTODO_CONFIG") or Path.home() / ".config" / "lineartodo" / "config.json")
STATE_PATH = Path(
    os.environ.get("LINEARTODO_STATE")
    or Path.home() / "Library" / "Application Support" / "LinearTodo" / "state.json"
)



def _accepted(hint) -> tuple:
    """Types concrets qu'une annotation accepte : `str | None` et `list[str]` compris."""
    if get_origin(hint) in (Union, UnionType):
        return tuple(t for arm in get_args(hint) for t in _accepted(arm))
    origin = get_origin(hint) or hint
    return (origin,) if isinstance(origin, type) else ()


def _keep(value, hint) -> bool:
    """Le fichier est modifiable à la main : une valeur du mauvais type est écartée.

    Sans ce filtre, un `refresh_seconds: "vingt"` fait lever une exception à chaque cycle,
    dans le fil de fond, et l'app se fige en continuant d'afficher un état crédible.
    """
    accepted = _accepted(hint)
    if not accepted:
        return True
    # `True` est un entier pour Python : sans ce garde-fou, un booléen passerait pour un délai.
    if isinstance(value, bool) and bool not in accepted:
        return False
    return isinstance(value, accepted)

@dataclass
class Config:
    # Clés d'équipe auxquelles se restreindre (« ENG », « OPS »). [] = tout ce que la clé voit,
    # ce qui est le cas normal : une boîte de réception n'a pas de périmètre.
    teams: list[str] = field(default_factory=list)
    # Personne observée : son `displayName` ou son e-mail Linear. null pour soi-même.
    view_as: str | None = None
    refresh_seconds: int = 20
    # La sonde ne voit pas tout : une notification lue depuis le téléphone ne change pas
    # toujours l'échantillon qu'elle observe. D'où une lecture complète forcée à cet intervalle.
    full_refresh_seconds: int = 60
    # Mes tickets : lecture plus lourde et plus lente à bouger que la boîte. Sa propre cadence.
    mine_refresh_seconds: int = 120
    # Tickets clos : de l'histoire, elle peut attendre.
    closed_refresh_seconds: int = 300
    # Annuaire du workspace, pour le menu « voir en tant que ».
    people_refresh_seconds: int = 1800
    # Boîte de réception : Linear sert 50 notifications par page, rangées et non rangées mêlées.
    # On s'arrête dès que les non-lues annoncées sont trouvées, ce plafond n'est qu'un garde-fou
    # pour une boîte très ancienne.
    inbox_pages: int = 4
    inbox_page_size: int = 50
    # Section des notifications sorties de la boîte.
    show_filed: bool = True
    filed_days: int = 7
    filed_rows: int = 15
    # Section des tickets qui me sont assignés et qui ne sont pas clos.
    show_mine: bool = True
    mine_rows: int = 20
    # Le backlog d'un dev actif compte des centaines de tickets : hors périmètre par défaut,
    # seuls le triage, « à faire » et « en cours » sont du travail engagé.
    include_backlog: bool = False
    # Section des tickets clos.
    show_closed: bool = True
    closed_days: int = 14
    closed_rows: int = 15
    hide_when_zero: bool = False
    # Anneau de progression autour de la photo : il se remplit jusqu'au prochain cycle, ce qui
    # dit quand l'app va relire sans avoir à ouvrir le menu.
    show_refresh_ring: bool = True
    # Format de l'élément dans la barre : "avatar" (photo de l'identité + pastille de comptage),
    # "count" (nombre seul), "icon_count", "icon" (icône seule). Une barre saturée évince les
    # éléments les plus larges.
    badge_style: str = "avatar"
    # Commande qui imprime une clé d'API sur sa sortie standard.
    api_key_command: list[str] | None = None

    @classmethod
    def load(cls) -> "Config":
        known = {f.name for f in fields(cls)}
        hints = get_type_hints(cls)
        data: dict = {}
        if CONFIG_PATH.exists():
            try:
                raw = json.loads(CONFIG_PATH.read_text() or "{}")
            except (json.JSONDecodeError, OSError):
                raw = {}
            if isinstance(raw, dict):
                data = {k: v for k, v in raw.items() if k in known and _keep(v, hints[k])}
        cfg = cls(**data)
        # Réécrit le fichier quand des options apparaissent ou disparaissent, pour qu'il reste
        # le reflet exact de ce que l'app sait lire.
        if set(data) != known:
            cfg.save()
        return cfg

    def save(self) -> None:
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        CONFIG_PATH.write_text(json.dumps(asdict(self), indent=2, ensure_ascii=False) + "\n")

    def team_keys(self) -> list[str]:
        return [key.strip().upper() for key in self.teams if key.strip()]
