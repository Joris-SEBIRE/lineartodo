"""Le son d'un nouvel élément dans les compteurs.

Un son se décide sur une transition, d'une lecture à la suivante, et jamais sur un état : la
première lecture ne sonne pas, ni celle qui suit un passage à une autre identité. Ce qui sonne,
c'est une notification non lue jamais entendue, reconnue à son identifiant et à sa date : un
nouveau sujet, ou une nouvelle notification sur un sujet déjà compté, rouge ou bleu. Lire un
sujet, qui passe du rouge au bleu, ne crée aucune notification non lue, donc ne sonne pas ; une
ligne qui s'efface le temps d'une lecture incomplète puis revient à l'identique non plus.
"""

from __future__ import annotations

from .models import Item


class Bell:
    def __init__(self) -> None:
        # Notifications non lues déjà entendues, « identifiant@date ».
        self.heard: set[str] = set()
        self.identity: str | None = None

    def feed(self, items: list[Item], identity: str) -> bool:
        """Cette lecture fait-elle entrer un nouvel élément dans un compteur ?"""
        heard = {note for item in items if item.weight for note in item.notes}
        ring = identity == self.identity and bool(heard - self.heard)
        if identity != self.identity:
            self.heard, self.identity = set(), identity
        self.heard |= heard
        return ring
