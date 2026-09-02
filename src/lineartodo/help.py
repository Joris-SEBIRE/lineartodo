"""Panneau « Réglages et mode d'emploi » : le manuel complet, dans l'app.

Le texte est volontairement autoportant. Quelqu'un qui n'a jamais vu LinearTodo doit pouvoir
comprendre d'où viennent les informations, avec quelle clé, et comment tout se règle. Les
valeurs propres à l'installation (compte, origine de la clé, périmètre, chemins) y sont
injectées, pour que le panneau décrive la réalité et pas un exemple.
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

import objc
from Cocoa import (
    NSAttributedString,
    NSBackingStoreBuffered,
    NSBox,
    NSBoxSeparator,
    NSColor,
    NSFont,
    NSFontAttributeName,
    NSFontWeightRegular,
    NSFontWeightSemibold,
    NSForegroundColorAttributeName,
    NSMakeRect,
    NSMakeSize,
    NSMutableAttributedString,
    NSMutableParagraphStyle,
    NSObject,
    NSParagraphStyleAttributeName,
    NSScrollView,
    NSTextView,
    NSView,
    NSViewHeightSizable,
    NSViewMaxXMargin,
    NSViewMinYMargin,
    NSViewWidthSizable,
    NSWindowStyleMaskClosable,
    NSWindowStyleMaskResizable,
    NSWindowStyleMaskTitled,
)

from . import IDENTITY_TINT, settings
from .config import CONFIG_PATH, STATE_PATH, Config

# Deux volets : le formulaire tient dans une colonne étroite, le texte a besoin de largeur.
FORM_WIDTH = 380.0
DOC_WIDTH = 620.0
BAR_HEIGHT = 34.0
BAR_INSET = 14.0

TEXT = """
# LinearTodo

Ce qu'il te reste à faire sur Linear, dans la barre des menus. **Lecture seule** : aucune \
écriture sur Linear, aucune mutation GraphQL.

## Cette installation

- Compte observé : {identity}
- Clé fournie par : {key}
- Périmètre : {teams}
- Réglages : `{config}`
- État local : `{state}`
- Version {version}, code du {built}

## Clé et accès

Aucune clé n'est stockée par l'app. Elle en cherche une dans cet ordre, et s'arrête à la \
première trouvée.

- `api_key_command` : une commande qui imprime une clé
- le trousseau macOS, service `{service}`
- le fichier `{key_file}`
- `LINEAR_API_KEY`, sinon `LINEAR_TOKEN`

Le plus simple est de la coller dans le champ **Clé d'API** du formulaire, à gauche : ⌘V y \
fonctionne — cette fenêtre route elle-même les raccourcis d'édition, une app sans barre de menus \
n'en ayant pas d'autre moyen. Le bouton au bout du champ la range dans le trousseau, l'essaie \
aussitôt auprès de Linear, et le bandeau du bas dit ce qui s'est passé : le compte auquel elle \
donne accès, ou la raison du refus. La coche ne reste que si la clé a été acceptée. La lecture \
repart alors avec elle, sans relancer l'app ; le champ se vide après coup, et rien n'est écrit \
dans le fichier de réglages.

La clé personnelle se crée sur `linear.app/settings/account/security`. Elle porte tes droits, \
ni plus ni moins : un ticket d'une équipe privée que tu ne vois pas n'existe pas pour l'app.

## Sources

- **Boîte de réception** : `notifications`, la même liste que l'inbox de Linear. Chaque \
notification porte son `type`, sa `category`, son `readAt`, son `archivedAt`, son \
`snoozedUntilAt`, la personne qui l'a causée, et le ticket, le message ou le projet visé. \
Traiter une notification dans Linear l'archive : la lecture demande donc `includeArchived`, \
sinon l'historique serait vide. Linear ne sait pas filtrer sur « non lue » : l'app pagine \
jusqu'à retrouver le compte de non-lues qu'il annonce, ce qui tient en une page dans le cas \
normal. Le sens du tri n'étant pas documenté, il est mesuré une fois par lancement plutôt que \
supposé
- **Mes tickets** : une recherche `issues` — ce qui m'est assigné et n'est pas clos, avec son \
état, son échéance, sa priorité, son cycle et les tickets qui le bloquent
- **Tickets clos** : la même recherche une fois `completed` ou `canceled`, avec l'historique \
d'états. C'est la seule façon de savoir *qui* a clôturé, Linear n'exposant pas de `completedBy` — \
et cet historique se lit du plus récent au plus ancien, donc par `first`, pas par `last`
- **Annuaire** : `users`, pour le menu « voir en tant que », classé par dernière présence
- **Visages** : la photo de profil quand il y en a une, sinon les initiales sur la couleur que \
Linear attribue au compte. Cache disque de quatorze jours

## Rythme

Linear accorde 2 500 requêtes et 3 000 000 points de complexité par heure et par clé, et l'annonce \
dans ses en-têtes de réponse. Mesuré sur cette installation : 76 points pour la sonde, ~1 480 pour \
la lecture complète de la boîte, ~41 pour mes tickets, ~53 pour les clos, ~575 pour l'annuaire. \
Au rythme par défaut, le pire des cas tient autour de 400 requêtes et 280 000 points par heure.

- toutes les {refresh} s (`refresh_seconds`), une sonde lit le compte de non-lues et \
l'empreinte des dernières notifications. Empreinte identique, le cycle s'arrête là
- empreinte différente : lecture complète de la boîte
- toutes les {full} s au plus tard (`full_refresh_seconds`), lecture complète forcée. Un \
message lu depuis le téléphone ne change pas toujours l'échantillon de la sonde
- toutes les {work} s (`work_refresh_seconds`), mes tickets ; toutes les {done} s \
(`done_refresh_seconds`), les clôturés. Ils bougent moins vite et coûtent plus cher
- ⌘R relance tout, sans passer par la sonde
- sous 300 requêtes restantes, le rythme passe à 2 min et le menu le signale

Le menu se met à jour pendant qu'il est ouvert.

## Quand Linear répond mal

Un triangle d'avertissement apparaît en haut à gauche de la photo, et une section en tête du menu \
dit quelle source ne répond pas, depuis quand, et ce que cela fausse. Les deux comptes restent \
affichés dans leurs coins, le rouge en haut à droite et le bleu en bas à gauche : le triangle \
occupe le troisième coin, sans jamais en masquer un — c'est lui qui dit que les nombres datent.

Trois niveaux, du plus bénin au plus grave, à la couleur du triangle et au titre de la section :

- jaune, « données incomplètes » : rien n'est cassé chez Linear, mais l'app ne peut plus tout \
lire. Quota épuisé, clé refusée, ou personne observée introuvable
- orange, « Linear répond mal » : une source auxiliaire tombe en erreur serveur ou reste \
injoignable
- rouge, « Linear en panne » : la boîte de réception elle-même échoue

Linear ne publie pas d'API d'état : le niveau ne vient que de nos propres échecs, et chaque \
ligne ouvre `linearstatus.com` pour trancher. Une source auxiliaire qui tombe ne fait pas perdre \
le reste du cycle : la boîte reste affichée, et la dernière lecture connue est conservée.

## Sections

Quatre, et rien d'autre. L'app montre l'état de Linear, elle n'en déduit pas une seconde liste \
de travail à côté.

- **Ma boîte de réception** : tout ce qui s'y trouve encore, lu ou non, du plus récent au plus \
ancien. Une ligne par sujet, comme dans Linear
- **Tickets qui me sont assignés** : ce qui n'est pas clos, du plus récemment bougé au plus \
dormant. Le visage est celui du créateur — l'assigné, c'est moi, il n'apprend rien
- **Notifications archivées** : celles qui ont été rangées dans Linear, ou dont le ticket est \
parti à la corbeille. Même fenêtre de lecture, même tri
- **Tickets clos ou supprimés** : terminés, annulés, marqués en doublon ou supprimés, et par \
quelle main

**Un sujet, une ligne, une unité.** Linear regroupe dans sa boîte tous les événements d'un même \
ticket : l'app fait pareil, sinon les deux comptes ne se ressemblent plus. Une ligne vaut donc \
un, et sa pastille porte ce un : les lignes d'une section s'additionnent au nombre de son titre, \
et les sections au badge de la barre. Deux dans la pastille violette, ce sont deux lignes \
marquées d'un 1 violet — la somme se vérifie à l'œil, sans rien croire sur parole.

Le nombre d'événements, lui, se lit en pastille grise, et leur nature s'écrit dans les \
métadonnées : « commentaire, assignation ». Il ne compte dans aucun badge.

Le tri fait le travail des anciennes sections déduites : un ticket qui n'a pas bougé depuis des \
semaines tombe de lui-même au bas de « Mes tickets », et ce qui le retient — échéance dépassée, \
blocage, urgence — porte son étiquette rouge sur sa propre ligne.

## Règles

- la boîte de réception **est** la liste de ce qu'il reste à faire, et Linear la range en trois \
états : non lue, c'est chaud ; lue mais toujours dans la boîte, c'est à faire sans urgence ; \
rangée, c'est fait. Les deux premiers comptent, chacun dans sa pastille — **rouge** pour le \
chaud, **bleu** pour le tiède
- **lire n'est pas traiter** : une notification lue reste dans la boîte, donc à faire, et son \
sujet passe simplement du rouge au bleu. Ce qui l'éteint, c'est de la ranger dans Linear — l'app \
ne le fait jamais à ta place, elle le lit au cycle suivant
- un sujet qui porte à la fois du lu et du non-lu est rouge : il reste quelque chose à découvrir
- une notification rangée dans l'inbox de Linear est archivée, pas supprimée : elle quitte les \
deux comptes et reste dans l'historique, y compris si elle n'a jamais été ouverte
- un ticket parti à la corbeille emporte ses notifications hors des comptes, même celles que \
Linear laisse non lues : son compteur les additionne encore, sa boîte ne les montre plus, et \
leur lien n'ouvre plus rien. Elles finissent dans l'historique, marquées « ticket supprimé »
- un sujet dont tout est en sommeil reste affiché dans la boîte, avec l'heure de son réveil, \
sans compter dans aucune pastille
- ouvrir une ligne ne marque rien comme lu ici : c'est Linear qui le fait quand la page s'ouvre \
chez lui, et la ligne passe alors du rouge au bleu au cycle suivant. L'app n'écrit jamais
- dans un titre de section, un compte suivi d'un `+` est un plancher : la liste est écrêtée. La \
pastille de la barre ne porte jamais de `+` : à sa taille il ne se lirait pas, et il resterait \
allumé en permanence dès qu'une source est écrêtée. Quand Linear annonce plus de non-lues que sa \
boîte n'en a servi, le menu chiffre l'écart en bas ; les notifications sur ticket supprimé en \
sont retirées, sans quoi l'écart ne mènerait à rien
- le compteur de Linear additionne des notifications, la pastille compte des sujets : trois \
commentaires sur un même ticket font 3 chez lui et 1 ici, exactement comme sa boîte n'affiche \
qu'une ligne

## Une ligne

Visage de la personne concernée, ou l'icône de la section à défaut, surmonté du nombre de \
notifications. Toutes les vignettes font la même largeur, sinon les titres ne s'aligneraient \
plus d'une ligne à l'autre. Puis le titre du ticket. Puis des métadonnées constantes : \
identifiant, personne, délai, état, et un extrait du message. Puis l'équipe, le projet et le \
cycle.

Le délai prend la couleur de la pastille de la ligne — rouge pour ce qui n'a pas été vu, bleu \
pour ce qui attend d'être traité — et reste gris sur une ligne qui ne compte rien. Les pastilles \
grises, elles, ne comptent jamais : elles disent le nombre d'événements du sujet et l'état du \
ticket.

Le deuxième renseignement d'une ligne dit toujours à qui appartient le visage : « notifié par » \
dans la boîte et son histoire, « créé par » dans mes tickets — l'assigné, c'est moi —, « terminé \
par », « annulé par » ou « supprimé par » dans l'histoire des tickets.

L'état d'un ticket est dessiné comme dans Linear, dans la couleur que Linear lui donne : anneau \
pointillé pour le backlog, anneau vide pour « à faire », anneau à moitié plein pour ce qui est \
commencé, disque coché pour ce qui est terminé, disque barré pour ce qui est annulé ou en \
doublon. Un ticket parti à la corbeille n'a pas d'état d'avancement : il porte une corbeille, \
dans le gris que Linear donne à ce qui est clos.

L'étiquette rouge dit l'état qui doit sauter aux yeux : `en retard`, `SLA`, `urgent`, `bloqué`.

Clic : ouvrir au bon endroit. **⌥** : masquer jusqu'à la prochaine activité, en local. **⌘** : \
copier le lien. **⌃** : copier l'identifiant, de quoi nommer une branche. Le point ● marque ce \
qui est arrivé depuis la dernière ouverture du menu.

## Voir en tant que

Les membres du workspace, les plus récemment vus en tête, avec leur statut Linear s'ils en ont \
posé un. La clé ne change pas, seules les recherches changent.

La boîte de réception, elle, est celle de la clé : **elle n'existe pas pour un collègue**, et \
Linear n'a aucune API pour la lire à sa place. Le menu le dit alors, la pastille rouge tombe à \
zéro, et ce qui reste est tout ce qui se déduit de ses tickets — ce qui l'attend, ce qui le \
bloque, ce qu'il a clôturé, et les messages restés sans sa réponse. C'est la réponse à « où en \
est un collègue », pas à « qu'a-t-il à lire ».

Les éléments masqués sont mémorisés par identité.

## Réglages

À gauche. Chaque champ est écrit dans `{config}`, relu à chaud : l'enregistrement suffit, sans \
redémarrage. Le fichier se complète seul quand une option apparaît.

**Chaque ligne s'enregistre seule.** Tant qu'elle vaut ce qui est sur le disque, elle ne porte \
rien. Modifiée, un bouton paraît au bout de son champ, et la valeur enregistrée se rappelle en \
dessous — c'est ce qu'on s'apprête à remplacer. Enregistrée, un trait vert passe sous le champ et \
une coche reste à sa place, jusqu'à la modification suivante : on voit d'un coup d'œil ce qui est \
en attente et ce qui vient d'être écrit. Le second bouton, à gauche, revient à la valeur \
d'origine, et le bandeau du bas répète en clair ce qui a été écrit.

Rien ne se garde d'une fois sur l'autre : à l'ouverture, la fenêtre montre le fichier, jamais un \
brouillon abandonné. Les raccourcis d'édition — ⌘X, ⌘C, ⌘V, ⌘A, ⌘Z — fonctionnent dans les \
champs : une app d'accessoire n'a pas de menu Édition, donc cette fenêtre les route elle-même, \
sans quoi macOS ne les enverrait nulle part.

## Diagnostic

- `{status}` : ce que la barre affiche, avec la géométrie réelle de l'élément
- `{errors}` : les pannes et leur pile
- une seule instance à la fois. Sans donnée fraîche, l'icône passe en alerte et le pied du menu \
affiche « figé depuis »
- `python -m lineartodo --print` en texte, `--as <personne>` pour la vue d'un collègue

## La couleur de l'app

LinearTodo est **bleu**, GitTodo est **violet** : deux icônes voisines dans la barre, la même \
mise en page et le même vocabulaire dans les menus, il faut bien un signe pour savoir laquelle \
parle. Cette couleur ne dit rien de l'état, seulement *qui* affiche.

On la trouve à quatre endroits : l'anneau du prochain cycle et le compteur animé qui le \
remplace, le compte secondaire, les titres de section — icône et texte — et les titres de cette \
fenêtre. Le rouge, lui, reste au rouge : c'est de l'urgence, pas une identité. Et la section des \
pannes garde la couleur de son niveau, jaune, orange ou rouge : là, l'alerte passe devant \
l'identité.

## Icône de la barre

Deux comptes, deux coins, une seule source : la boîte de réception. La pastille **rouge**, en \
haut à droite, est ce qui n'a pas encore été vu — à faire tout de suite. La pastille **bleue**, \
en bas à gauche, est ce qui a été vu et attend toujours d'être traité — à faire, sans urgence. \
Leur somme est le contenu de la boîte ; ranger une notification dans Linear la retire des deux.

Par défaut, la photo de l'identité observée, la pastille rouge, et un anneau qui se remplit dans \
le sens horaire jusqu'au prochain cycle. L'anneau s'efface pendant une lecture, où le compteur \
animé prend le relais ; il continue de tourner quand une source ne répond plus, puisqu'un nouvel \
essai est justement ce qu'on attend. `show_refresh_ring` l'éteint. `badge_style` accepte aussi `count`, `icon_count` et `icon`, plus \
étroits quand la barre des menus est saturée. ⌘-glisser l'icône vers la droite la met à l'abri \
des masquages de macOS.
"""

def built_at() -> str:
    """Date du code réellement exécuté, pour repérer un bundle installé resté en arrière.

    Le numéro de version ne bouge pas à chaque modification : une copie périmée afficherait la
    même. La date des sources chargées, elle, la trahit.
    """
    stamps = [source.stat().st_mtime for source in Path(__file__).parent.glob("*.py")]
    return datetime.fromtimestamp(max(stamps)).strftime("%d/%m/%Y à %H:%M") if stamps else "inconnue"


def document(context: dict) -> str:
    from . import VERSION
    from .linear import KEY_FILE, KEYCHAIN_SERVICE

    cfg = Config.load()
    identity = context.get("identity") or "inconnu"
    viewer = context.get("viewer") or "inconnu"
    teams = ", ".join(context.get("teams") or []) or "toutes les équipes que la clé voit"
    return TEXT.format(
        identity=f"@{identity}" + (f", observé avec la clé de @{viewer}" if identity != viewer else ""),
        key=context.get("key") or "aucune clé trouvée",
        teams=teams,
        config=CONFIG_PATH,
        state=STATE_PATH,
        status=STATE_PATH.with_name("status.json"),
        errors=STATE_PATH.with_name("errors.log"),
        key_file=KEY_FILE,
        service=KEYCHAIN_SERVICE,
        version=VERSION,
        built=built_at(),
        refresh=cfg.refresh_seconds,
        full=cfg.full_refresh_seconds,
        work=cfg.mine_refresh_seconds,
        done=cfg.closed_refresh_seconds,
    )


BULLET = "•   "
_INLINE = re.compile(r"(\*\*[^*]+\*\*|`[^`]+`)")


def _style(before: float = 0.0, indent: float = 0.0) -> NSMutableParagraphStyle:
    style = NSMutableParagraphStyle.alloc().init()
    style.setParagraphSpacingBefore_(before)
    style.setParagraphSpacing_(2.0)
    style.setLineSpacing_(2.0)
    if indent:
        style.setHeadIndent_(indent)
    return style


def _inline(line: str, size: float, weight: float, colour, style) -> NSMutableAttributedString:
    """Rend une ligne en gérant **gras** et `code`, le reste étant du texte courant."""
    out = NSMutableAttributedString.alloc().init()
    for piece in _INLINE.split(line):
        if not piece:
            continue
        font = NSFont.systemFontOfSize_weight_(size, weight)
        shade = colour
        if piece.startswith("**") and piece.endswith("**"):
            piece, font = piece[2:-2], NSFont.systemFontOfSize_weight_(size, NSFontWeightSemibold)
        elif piece.startswith("`") and piece.endswith("`"):
            piece = piece[1:-1]
            font = NSFont.monospacedSystemFontOfSize_weight_(size - 1.0, NSFontWeightRegular)
            shade = NSColor.secondaryLabelColor()
        out.appendAttributedString_(
            NSAttributedString.alloc().initWithString_attributes_(
                piece,
                {
                    NSFontAttributeName: font,
                    NSForegroundColorAttributeName: shade,
                    NSParagraphStyleAttributeName: style,
                },
            )
        )
    return out


def _identity():
    """Couleur de l'app, pour que la fenêtre se reconnaisse avant même d'être lue."""
    return getattr(NSColor, IDENTITY_TINT)()


def render(document_text: str) -> NSMutableAttributedString:
    body = NSMutableAttributedString.alloc().init()
    for raw in document_text.strip("\n").split("\n"):
        line = raw.rstrip()
        if not line:
            continue
        if line.startswith("# "):
            piece = _inline(line[2:], 22.0, NSFontWeightSemibold, _identity(), _style(2.0))
        elif line.startswith("## "):
            piece = _inline(line[3:], 15.0, NSFontWeightSemibold, _identity(), _style(22.0))
        elif line.startswith("### "):
            piece = _inline(line[4:], 12.5, NSFontWeightSemibold, NSColor.labelColor(), _style(14.0))
        elif line.startswith("- "):
            piece = _inline(BULLET + line[2:], 12.0, NSFontWeightRegular, NSColor.labelColor(), _style(3.0, 20.0))
        else:
            piece = _inline(line, 12.0, NSFontWeightRegular, NSColor.labelColor(), _style(8.0))
        body.appendAttributedString_(piece)
        body.appendAttributedString_(NSAttributedString.alloc().initWithString_("\n"))
    return body


class Panel(NSObject):
    """Fenêtre unique : le mode d'emploi à droite, les réglages modifiables à gauche.

    Chaque ligne s'enregistre pour elle-même, au bout de son champ : rien n'attend un bouton
    lointain, et ce qui est écrit se voit là où on vient de le taper.
    """

    def initWithContext_(self, context):
        self = objc.super(Panel, self).init()
        if self is None:
            return None
        self.status = None
        self.form = settings.SettingsForm.alloc().initWithConfig_origin_onMessage_(
            Config.load(), context.get("key") or "", self.tell
        )
        self.form.apply_key = context.get("apply_key")
        self.window = self._window(context)
        return self

    @objc.python_method
    def refresh(self, context: dict) -> None:
        """Reprend le disque et le contexte à chaque ouverture.

        Une fenêtre gardée en mémoire montrerait sinon l'état de la dernière fois : les valeurs
        d'alors, et un brouillon jamais enregistré. On veut l'inverse — ce qui est enregistré,
        et rien d'autre.
        """
        self.form.apply_key = context.get("apply_key") or self.form.apply_key
        self.form.origin = context.get("key") or self.form.origin
        if self.form.secret is not None:
            self.form.secret.setPlaceholderString_(self.form.origin or "aucune clé trouvée")
        self.form.reload()
        self.tell("")

    @objc.python_method
    def tell(self, message: str, trouble: bool = False) -> None:
        """Écrit dans le bandeau ce que la dernière action a produit."""
        if self.status is None:
            return
        self.status.setStringValue_(message)
        self.status.setTextColor_(NSColor.systemRedColor() if trouble else _identity())

    def windowWillClose_(self, notification):
        # Ce qui n'a pas été enregistré est perdu, et c'est voulu : à la réouverture, la fenêtre
        # doit montrer ce qui est sur le disque, pas un brouillon d'il y a trois jours.
        _ALIVE.pop("panel", None)

    @objc.python_method
    def _window(self, context: dict):
        frame = NSMakeRect(0, 0, FORM_WIDTH + DOC_WIDTH, 760)
        window = settings.EditableWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            frame,
            NSWindowStyleMaskTitled | NSWindowStyleMaskClosable | NSWindowStyleMaskResizable,
            NSBackingStoreBuffered,
            False,
        )
        window.setTitle_("LinearTodo, mode d'emploi et réglages")
        window.setReleasedWhenClosed_(False)
        window.setMinSize_(NSMakeSize(FORM_WIDTH + 320, 420))
        window.setDelegate_(self)

        content = NSView.alloc().initWithFrame_(frame)
        width, height = frame.size.width, frame.size.height
        bar = NSView.alloc().initWithFrame_(NSMakeRect(0, height - BAR_HEIGHT, width, BAR_HEIGHT))
        bar.setAutoresizingMask_(NSViewWidthSizable | NSViewMinYMargin)
        where = settings._label(
            str(CONFIG_PATH),
            NSMakeRect(BAR_INSET, 9.0, width - 2 * BAR_INSET - 40.0, 16.0),
            10.0,
            NSFontWeightRegular,
            NSColor.tertiaryLabelColor(),
        )
        where.setFont_(NSFont.monospacedSystemFontOfSize_weight_(9.5, NSFontWeightRegular))
        where.setFrame_(NSMakeRect(BAR_INSET, 9.0, 300.0, 16.0))
        # Largeur figée : sans cela le chemin s'étire avec la fenêtre et passe sous le message.
        where.setAutoresizingMask_(0)
        bar.addSubview_(where)
        self.status = settings._label(
            "",
            NSMakeRect(BAR_INSET + 310.0, 9.0, width - BAR_INSET * 2 - 310.0, 16.0),
            10.5,
            NSFontWeightSemibold,
            _identity(),
        )
        bar.addSubview_(self.status)
        content.addSubview_(bar)
        content.addSubview_(
            _rule(NSMakeRect(0, height - BAR_HEIGHT, width, 1.0), NSViewWidthSizable | NSViewMinYMargin)
        )

        body_height = height - BAR_HEIGHT
        left = _scroller(NSMakeRect(0, 0, FORM_WIDTH, body_height))
        left.setAutoresizingMask_(NSViewHeightSizable | NSViewMaxXMargin)
        left.setDocumentView_(self.form.build(FORM_WIDTH - 15.0))
        content.addSubview_(left)

        doc = NSTextView.alloc().initWithFrame_(NSMakeRect(0, 0, width - FORM_WIDTH, body_height))
        doc.setEditable_(False)
        doc.setSelectable_(True)
        doc.setDrawsBackground_(False)
        doc.setTextContainerInset_(NSMakeSize(22.0, 22.0))
        doc.setHorizontallyResizable_(False)
        doc.setAutoresizingMask_(NSViewWidthSizable)
        doc.textContainer().setWidthTracksTextView_(True)
        doc.textStorage().setAttributedString_(render(document(context)))
        right = _scroller(NSMakeRect(FORM_WIDTH, 0, width - FORM_WIDTH, body_height))
        right.setAutoresizingMask_(NSViewWidthSizable | NSViewHeightSizable)
        right.setDocumentView_(doc)
        content.addSubview_(right)
        content.addSubview_(
            _rule(NSMakeRect(FORM_WIDTH - 1, 0, 1.0, body_height), NSViewHeightSizable | NSViewMaxXMargin)
        )

        window.setContentView_(content)
        window.center()
        return window


def _rule(box, mask):
    """Filet de séparation : sans lui, les deux volets et le bandeau flottent sans limite."""
    line = NSBox.alloc().initWithFrame_(box)
    line.setBoxType_(NSBoxSeparator)
    line.setAutoresizingMask_(mask)
    return line


def _scroller(box):
    scroll = NSScrollView.alloc().initWithFrame_(box)
    scroll.setHasVerticalScroller_(True)
    scroll.setAutohidesScrollers_(True)
    scroll.setDrawsBackground_(False)
    return scroll


# Le contrôleur doit survivre à l'appel : sans cette référence, il serait ramassé et les boutons
# n'auraient plus de cible.
_ALIVE: dict = {}


def panel(context: dict):
    """Fenêtre du mode d'emploi et des réglages, créée à la demande, relue à chaque ouverture."""
    live = _ALIVE.get("panel")
    if live is None:
        live = Panel.alloc().initWithContext_(context)
        _ALIVE["panel"] = live
    else:
        live.refresh(context)
    return live
