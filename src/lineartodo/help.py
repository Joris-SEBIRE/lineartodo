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
    NSViewMinXMargin,
    NSViewMinYMargin,
    NSViewWidthSizable,
    NSWindow,
    NSWindowStyleMaskClosable,
    NSWindowStyleMaskResizable,
    NSWindowStyleMaskTitled,
)

from . import IDENTITY_TINT, settings
from .config import CONFIG_PATH, STATE_PATH, Config
from .models import GROUPS, ORDER

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
- le trousseau macOS, service `{service}` : \
`security add-generic-password -a "$USER" -s {service} -w '<clé>'`
- le fichier `{key_file}`
- `LINEAR_API_KEY`, sinon `LINEAR_TOKEN`

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
- **Mes tickets** : quatre recherches `issues` dans une requête — ce qui m'est assigné, ce que \
j'ai créé, ce où j'ai parlé ou que je suis, et la file de triage des équipes réglées. Chaque \
ticket remonte son état, son échéance, sa priorité, son cycle, ses relations `blocks` dans les \
deux sens, et ses derniers messages avec leurs réactions
- **Tickets clôturés** : les mêmes tickets une fois `completed` ou `canceled`, avec leur \
historique d'états — c'est la seule façon de savoir *qui* a clôturé, Linear n'exposant pas de \
`completedBy`
- **Annuaire** : `users`, pour le menu « voir en tant que », classé par dernière présence
- **Visages** : la photo de profil quand il y en a une, sinon les initiales sur la couleur que \
Linear attribue au compte. Cache disque de quatorze jours

## Rythme

Linear accorde 2 500 requêtes et 3 000 000 points de complexité par heure et par clé, et l'annonce \
dans ses en-têtes de réponse. Mesuré sur cette installation : 71 points pour la sonde, ~1 500 pour \
la lecture complète de la boîte, ~235 pour mes tickets, ~50 pour les clôturés, ~575 pour \
l'annuaire. Au rythme par défaut, le pire des cas tient autour de 400 requêtes et 300 000 points \
par heure.

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

La boîte de réception **est** la liste de ce qu'il reste à faire, et Linear la range en trois \
états : non lue, c'est chaud ; lue mais toujours dans la boîte, c'est à faire sans urgence ; \
rangée, c'est fait. Les deux premiers comptent, chacun dans sa pastille — **rouge** pour le \
chaud, **bleu** pour le tiède — et la somme des lignes d'une section vaut ce qu'elle porte. \
Les sections suivantes sont déduites de mes tickets : elles informent, elles ne comptent pas.

Une ligne ne mélange jamais les deux chaleurs : un ticket qui a du neuf et du déjà-lu donne deux \
lignes dans sa section, la chaude devant, parce qu'elles ne demandent pas la même chose.

### Boîte de réception

{actions}

### Déduit de mes tickets

{waiting}

## Règles

- une notification de la boîte compte une fois, dans une seule section, dans la pastille de sa \
chaleur. Une nature inconnue de l'app tombe dans « Autres notifications » plutôt que de \
disparaître : le total ne peut pas mentir, même le jour où Linear invente une notification
- **lire n'est pas traiter** : une notification lue reste dans la boîte, donc à faire, et passe \
simplement du rouge au bleu. Ce qui l'éteint, c'est de la ranger dans Linear — l'app ne le \
fait jamais à ta place, elle le lit au cycle suivant
- plusieurs notifications sur le même ticket tiennent sur une ligne, dont la pastille les \
compte. Le survol dit lesquelles
- une notification en sommeil ne compte pas : Linear l'a retirée de la boîte. Elle attend dans \
« En sommeil », avec l'heure de son réveil
- ouvrir une ligne ne marque rien comme lu ici : c'est Linear qui le fait quand la page s'ouvre \
chez lui, et la ligne passe alors du rouge au bleu au cycle suivant. L'app n'écrit jamais
- une notification rangée dans l'inbox de Linear est archivée, pas supprimée : elle quitte les \
deux comptes et reste dans l'historique, y compris si elle n'a jamais été ouverte
- **ce que la boîte oublie** : une notification rangée disparaît des comptes, même si la \
question qu'elle portait n'a jamais eu de réponse. « Messages restés sans réponse » les rattrape \
en relisant les messages des tickets : un fil dont je ne suis pas le dernier à parler, un message \
qui me nomme et que j'ai enjambé. Deux bornes gardent la section utile : la fenêtre \
`pending_days`, parce qu'une question de trois mois que personne n'a relancée n'attend plus rien, \
et le fait que le ticket soit à moi ou qu'un des messages me nomme
- un fil clos est un point traité. Une réaction 👍 ou 👎 posée sur un message vaut réponse : un \
refus est une réponse, et un point acté n'attend plus rien. Pas 👀, qui dit qu'on a vu et non \
qu'on a tranché
- répondre dans un fil répond au fil. En bas d'un ticket, la liste est chronologique : reprendre \
la parole répond à ce qui précède, sauf à un message qui me nomme — celui-là ne s'éteint que par \
une réponse citée ou une réaction
- un ticket n'apparaît qu'une fois dans les sections déduites, dans celle qui dit ce qui le \
retient : échéance dépassée, puis blocage, puis inactivité, puis échéance proche, puis « il en \
bloque d'autres », puis en cours, puis à démarrer
- un ticket dont une notification attend déjà ne réapparaît pas plus bas : la notification dit \
mieux ce qu'on attend
- un compte suivi d'un `+` est un plancher, pas un total : la liste est écrêtée, ou Linear \
annonce plus de non-lues que la boîte n'en a servi. Sans `+`, le compte est exact
- « bloqué » se lit dans les deux sens : le ticket qui me bloque vient des relations inverses, \
celui que je bloque des relations directes. Une relation « doublon » ou « lié » ne contraint \
aucun travail, elle est ignorée

## Une ligne

Visage de la personne concernée, ou l'icône de la section à défaut, surmonté du nombre de \
notifications. Toutes les vignettes font la même largeur, sinon les titres ne s'aligneraient \
plus d'une ligne à l'autre. Puis le titre du ticket. Puis des métadonnées constantes : \
identifiant, personne, délai, état, et un extrait du message. Puis l'équipe, le projet et le \
cycle.

Le délai et les pastilles chiffrées prennent la couleur de la pastille de la ligne — rouge pour \
ce qui n'a pas été vu, bleu pour ce qui attend d'être traité — et restent gris sur une ligne qui \
ne compte rien. Les drapeaux d'état, eux, ne comptent rien et gardent leur gris. Le délai est \
l'information qu'on cherche en premier sur une ligne qui attend ; les pastilles chiffrées disent \
de quoi son compte est fait.

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

DESCRIPTIONS = {
    "answer": "un message est arrivé sur un ticket, et personne n'y a répondu à ta place",
    "replies": "on a répondu dans un fil que tu as ouvert, ou ce fil a été clos",
    "mention": "on t'a nommé, dans un ticket, un message, un projet ou un document",
    "assigned": "un ticket t'a été assigné, ou on t'a confié un projet, un document, un client",
    "triage": "un ticket est arrivé dans une file de triage que tu suis",
    "alert": "échéance atteinte, SLA en danger ou dépassé, passage en urgent, ticket bloquant ; \
urgente, elle passe l'icône de la barre en alerte",
    "pull_request": "l'intégration Git de Linear : review demandée, approuvée, refusée, CI rouge",
    "status": "l'état d'un ticket que tu suis a changé, il a été rouvert ou débloqué",
    "reaction": "quelqu'un a réagi à un de tes tickets ou à un de tes messages",
    "project_news": "un update de projet, d'initiative ou d'équipe, ou une description modifiée",
    "document": "un document que tu suis a changé, bougé, été supprimé ou restauré",
    "customer": "un besoin client est arrivé, a été marqué important, ou résolu",
    "reminder": "un rappel que tu as posé, ou qu'on a posé pour toi",
    "unassigned": "un ticket t'a été retiré, ou tu n'es plus propriétaire d'un document",
    "other": "tout le reste, y compris ce que l'app ne sait pas encore nommer : le compte reste juste",
    "snoozed": "notification remise à plus tard : Linear la cache, elle ne compte dans aucune \
pastille jusqu'à son réveil",
    "pending_reply": "des messages que la boîte a rangés n'ont jamais eu ta réponse",
    "overdue": "ton ticket a dépassé son échéance",
    "blocked": "un ticket encore ouvert bloque le tien",
    "stale": "ton ticket est « en cours » mais rien n'y a bougé depuis le délai réglé",
    "due_soon": "l'échéance de ton ticket arrive dans la fenêtre réglée",
    "blocking": "ton ticket en bloque un autre, encore ouvert : c'est lui qui commande",
    "in_progress": "ton ticket est en cours et rien ne le retient",
    "todo": "ton ticket t'est assigné et n'est pas démarré",
    "triage_queue": "la file de triage des équipes réglées, ce qui n'a pas encore été trié",
    "created_waiting": "tu as créé le ticket, il est chez quelqu'un d'autre ou chez personne",
    "touched": "tu as parlé sur ce ticket, ou tu le suis, et il a bougé récemment",
    "read": "l'histoire de la boîte : ce qui a été rangé dans Linear, groupé par sujet",
    "recent_done": "un de tes tickets est sorti du périmètre ouvert, et par la main de qui",
}


def _sections(action: bool) -> str:
    lines = []
    for kind in ORDER:
        group = GROUPS[kind]
        if group.is_action is action:
            lines.append(f"- **{group.label}** : {DESCRIPTIONS.get(kind.value, '')}")
    return "\n".join(lines)


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
        work=cfg.work_refresh_seconds,
        done=cfg.done_refresh_seconds,
        actions=_sections(True),
        waiting=_sections(False),
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

    Le bouton d'enregistrement n'apparaît qu'une fois quelque chose modifié : tant qu'il est
    absent, il n'y a rien à valider.
    """

    def initWithContext_(self, context):
        self = objc.super(Panel, self).init()
        if self is None:
            return None
        self.form = settings.SettingsForm.alloc().initWithConfig_onDirty_(Config.load(), self.dirty)
        self.window = self._window(context)
        return self

    @objc.python_method
    def dirty(self, changed: bool) -> None:
        self.save.setHidden_(not changed)

    def save_(self, sender):
        self.form.commit()
        self.save.setHidden_(True)

    def windowWillClose_(self, notification):
        # Des modifications en attente survivent à la fermeture : rien ne doit disparaître sans
        # avoir été enregistré ni jeté explicitement.
        if not self.form.changed():
            _ALIVE.pop("panel", None)

    @objc.python_method
    def _window(self, context: dict):
        frame = NSMakeRect(0, 0, FORM_WIDTH + DOC_WIDTH, 760)
        window = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
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
        bar.addSubview_(where)
        self.save = settings.save_button(self, "save:")
        self.save.setFrame_(NSMakeRect(width - BAR_INSET - 30.0, 5.0, 30.0, 24.0))
        self.save.setAutoresizingMask_(NSViewMinXMargin)
        bar.addSubview_(self.save)
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
    """Fenêtre du mode d'emploi et des réglages, créée à la demande."""
    live = _ALIVE.get("panel")
    if live is None:
        live = Panel.alloc().initWithContext_(context)
        _ALIVE["panel"] = live
    return live
