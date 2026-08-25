"""Point d'entrée : app de barre des menus, ou dump texte pour vérifier/déboguer.

    python -m lineartodo                  lance l'app
    python -m lineartodo --print          affiche ce que le menu contiendrait
    python -m lineartodo --print --as X   idem, vu à la place de la personne X
"""

from __future__ import annotations

import sys

from .config import CONFIG_PATH, Config
from .engine import build_items, count_stale, summarize, summarize_warm
from .linear import Linear, LinearError
from .models import GROUPS, ORDER, Work


def dump(argv: list[str]) -> int:
    cfg = Config.load()
    if "--as" in argv:
        position = argv.index("--as") + 1
        if position >= len(argv):
            print("--as attend un nom, un handle ou un e-mail Linear", file=sys.stderr)
            return 2
        cfg.view_as = argv[position]
    client = Linear(cfg)
    truncated: list[str] = []
    try:
        viewer = client.fetch_viewer()
        target = None
        if cfg.view_as:
            target = client.find_person(cfg.view_as)
            if target is None:
                print(f"Personne introuvable dans le workspace : {cfg.view_as}", file=sys.stderr)
                return 1
        identity = target or viewer
        notes, unread = [], None
        if target is None:
            _, unread = client.probe()
            notes, _, notes_truncated, unread = client.fetch_inbox(unread)
            truncated += notes_truncated
        work = Work()
        if cfg.show_mine:
            work, work_truncated = client.fetch_work(target.id if target else None)
            truncated += work_truncated
        if cfg.show_closed:
            work.done, done_truncated = client.fetch_done(target.id if target else None)
            truncated += done_truncated
    except LinearError as exc:
        print(f"Erreur : {exc}", file=sys.stderr)
        return 1
    me = identity.display_name if identity else ""
    items = build_items(notes, work, me, cfg, impersonating=target is not None)
    badge, _ = summarize(items)
    seen_as = f" (clé de @{viewer.display_name})" if viewer and target else ""
    quota = f"quota {client.requests_left} requêtes" if client.requests_left is not None else "quota inconnu"
    print(
        f"@{me}{seen_as} · {len(notes)} notification(s) lues · non lues {badge}"
        f" · lues à traiter {summarize_warm(items)} · {quota}"
    )
    if unread is not None:
        orphelines = count_stale(notes)
        reste = f", dont {orphelines} sur un ticket supprimé" if orphelines else ""
        print(f"Linear annonce {unread} non-lue(s){reste}")
    print(f"config {CONFIG_PATH}")
    for note in truncated:
        print(f"  ⚠︎ limite atteinte : {note}")
    for kind in ORDER:
        group = [item for item in items if item.kind == kind]
        if not group:
            continue
        marker = "!" if GROUPS[kind].is_action else " "
        total = sum(item.weight for item in group) if GROUPS[kind].is_action else len(group)
        print(f"\n{marker} {GROUPS[kind].label.upper()} ({total})")
        for item in group:
            pill = f"[{item.weight}] " if item.weight else "[ ] "
            chips = "  ".join(f"{name}{' ' + label if label else ''}" for name, label in item.chips)
            print(f"    {pill}{item.title}\n      {item.detail}\n      {chips}\n      {item.url}")
    return 0


def main() -> None:
    if "--print" in sys.argv:
        raise SystemExit(dump(sys.argv))
    from .app import run

    run()


if __name__ == "__main__":
    main()
