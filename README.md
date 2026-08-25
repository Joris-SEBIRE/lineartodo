# LinearTodo

Ce qu'il te reste à faire sur Linear, dans la barre des menus macOS.

Dans la barre : ta photo, et deux comptes qui disent l'état de ta boîte de réception Linear —
une pastille **rouge** pour ce qui n'a pas encore été vu, une **bleue** pour ce qui a été vu
et attend toujours d'être traité. Un clic ouvre le détail, regroupé par nature. Un clic sur une
ligne ouvre le ticket au bon endroit.

L'inbox de Linear *est* la liste des choses à faire : non lue, c'est chaud ; lue mais toujours
dans la boîte, c'est à faire sans urgence ; rangée, c'est fait.

L'app ne fait que lire. Elle n'écrit jamais rien sur Linear.

```
  4 (photo) 9        ← 9 non lues à droite, 4 lues à traiter à gauche
  ┌────────────────────────────────────────────────────────────────┐
  │ ✉  ON ATTEND MA RÉPONSE (6)                                    │
  │      Relancer l'export des factures                            │
  │      ENG-142 · @alice · depuis 45 min · En cours    ✉ 4        │  ← rouge
  │      Revoir le mapping des champs                              │
  │      ENG-097 · @bob · depuis 2 j · En cours         ✉ 2        │  ← bleu
  │ @  ON M'A NOMMÉ (1)                                            │
  │      Migrer les webhooks                                       │
  │      en retard  ENG-158 · @carol · depuis 20 min    @ 1        │
  │ ⚠  ALERTES (3)                                                 │
  │ ────────────────────────────────────────────────────────────── │
  │ ⌇  MESSAGES RESTÉS SANS RÉPONSE (2)                            │
  │ ⌛  EN COURS SANS ACTIVITÉ (1)                                 │
  │ ↻  OÙ JE SUIS INTERVENU RÉCEMMENT · 7 j (6)                    │
  │ ✉  HISTORIQUE DES NOTIFICATIONS · 7 j (11)                     │
  │ ⚑  MES TICKETS RÉCEMMENT CLÔTURÉS · 2 sem (4)                  │
  │ ────────────────────────────────────────────────────────────── │
  │ ↻  Actualiser  prochaine dans 14 s · 9 non-lue(s), 4 à traiter │
  │ ◉  Voir en tant que ▸                                          │
  │ ⚙  Réglages et mode d'emploi                                   │
  └────────────────────────────────────────────────────────────────┘
```

C'est le pendant de [GitTodo](https://github.com/Joris-SEBIRE/gittodo) : même structure, même vocabulaire, même façon de
compter. Les deux icônes cohabitent dans la barre.

## Prérequis

- macOS 13 ou plus récent.
- Les outils de développement en ligne de commande : `xcode-select --install`. Sans eux, `make`
  n'est qu'un stub qui affiche une invite d'installation.
- Python 3.12 ou 3.13 installé par Homebrew (`brew install python@3.13`). PyObjC a besoin d'une
  installation *framework*, ce que fournit Homebrew.
- Une clé d'API Linear personnelle, créée sur
  [linear.app/settings/account/security](https://linear.app/settings/account/security).
- Un compte administrateur, parce que l'installation écrit dans `/Applications`.

Le `Makefile` cible `/opt/homebrew/bin/python3.13` par défaut. Sur une machine Intel, ou avec un
autre interpréteur, passe le chemin : `make install PYTHON=/usr/local/bin/python3.13`.

## Installation

```bash
# 1. la clé, dans le trousseau macOS. Sans valeur après -w, `security` la demande
#    et la confirme sans l'écrire dans l'historique du shell.
security add-generic-password -a "$USER" -s lineartodo -w

# 2. l'app
make install
```

La cible construit `build/LinearTodo.app`, le recopie dans `/Applications` et le lance. Le bundle
embarque ses dépendances Python et ne dépend plus du dépôt une fois installé, mais son
interpréteur reste lié au framework Homebrew qui l'a construit, par un chemin qui contient le
numéro de version exact. Un `brew upgrade python@3.13` suivi d'un `brew cleanup` casse donc l'app
installée : refais `make install` après une montée de version de Python.

Pour que l'app démarre avec la session : menu **Lancer au démarrage**, qui écrit
`~/Library/LaunchAgents/fr.jsebire.lineartodo.plist`.

Autres cibles du `Makefile` :

- `make print` : affiche en texte ce que le menu contiendrait, sans lancer d'interface.
- `make run` : lance depuis les sources, sans construire de bundle.
- `make restart`, `make stop` : relance ou arrête toute instance.
- `make uninstall` : retire l'app, le LaunchAgent, l'état local et le cache des visages.
- `make clean` : supprime `build/` et `.venv/`.

## La clé

Aucune clé n'est stockée par l'app. Elle en cherche une dans cet ordre, et s'arrête à la première
trouvée :

- le réglage `api_key_command`, une commande qui imprime une clé sur sa sortie standard ;
- le trousseau macOS, service `lineartodo` ;
- le fichier `~/.config/lineartodo/token` ;
- la variable d'environnement `LINEAR_API_KEY`, sinon `LINEAR_TOKEN`.

La clé porte tes droits, ni plus ni moins : un ticket d'une équipe privée que tu ne vois pas
n'existe pas pour l'app. Attention quand même, une clé personnelle Linear vaut ton compte : elle
donne aussi le droit d'écrire, que cette app n'utilise pas. Garde-la comme un mot de passe, et
révoque-la depuis la même page si elle a traîné ailleurs.

Au premier accès au trousseau, macOS demande l'autorisation pour `/usr/bin/security`, l'outil
d'Apple par lequel passe la lecture. « Toujours autoriser » évite la question aux lancements
suivants.

## Utilisation

- Clic sur une ligne : ouvre le ticket, le message ou le projet dans Linear.
- **⌥** maintenu : la ligne devient « Masquer », et l'élément disparaît jusqu'à sa prochaine
  activité. Le masquage est local, rien n'est écrit sur Linear.
- **⌘** maintenu : « Copier le lien ». **⌃** maintenu : « Copier l'identifiant » (`ENG-142`), de
  quoi nommer une branche.
- **⌘R** : actualise tout de suite.
- Le point ● marque ce qui est arrivé depuis la dernière ouverture du menu.
- Un compte suivi d'un `+` est un plancher : la liste est écrêtée, ou Linear annonce plus de
  non-lues que la boîte n'en a servi.
- Lire n'est pas traiter : ouvrir une notification la fait passer du rouge au bleu, elle reste
  à faire. C'est **ranger** la notification dans Linear qui l'éteint — l'app ne le fait jamais à
  ta place, elle le lit au cycle suivant.
- Une notification rangée rejoint l'**Historique des notifications**, groupé par ticket, qu'elle
  ait été ouverte ou non.
- Une notification remise à plus tard par Linear ne compte dans aucune pastille : elle attend
  dans **En sommeil**, avec l'heure de son réveil.
- Le délai « depuis X » et les pastilles chiffrées prennent la couleur de la pastille de la
  ligne : rouge pour ce qui n'a pas encore été vu, bleu pour ce qui attend d'être traité, gris
  quand la ligne ne compte rien. Les drapeaux d'état restent gris, ils ne comptent rien.
- Un anneau se remplit autour de la photo, dans le sens horaire, jusqu'au prochain cycle.
- Dans une section, la ligne chaude passe devant la tiède : un même ticket peut avoir les deux.

Le menu se met à jour pendant qu'il est ouvert, sans qu'il faille le refermer.

Une seule instance tourne à la fois, garantie par un verrou sur
`~/Library/Application Support/LinearTodo/lineartodo.lock`.

## Ce que l'app déduit, en plus de la boîte de réception

La boîte de réception oublie une notification dès qu'elle est rangée, même si la question qu'elle
portait n'a jamais eu de réponse. Les sections du bas rattrapent ce que la boîte laisse tomber, en
relisant tes tickets. Elles informent : elles ne comptent dans aucune pastille.

- **Messages restés sans réponse** : un fil où tu n'es pas le dernier à parler, un message qui te
  nomme et que tu n'as ni cité ni acquitté d'un 👍 — sur des tickets dont la boîte a déjà rangé
  les notifications.
- **Échéance dépassée**, **Échéances proches**, **En cours sans activité** : le travail engagé qui
  dérive.
- **Mes tickets bloqués** et **Mes tickets qui en bloquent d'autres** : les relations `blocks`,
  lues dans les deux sens.
- **Créés par moi, chez quelqu'un d'autre** : ce que tu attends des autres.
- **Où je suis intervenu récemment** : les tickets où tu as parlé, ou que tu suis, et qui ont
  bougé.
- **Mes tickets récemment clôturés** : l'histoire, avec la main qui a clôturé.
- **File de triage** : facultative, à régler par clé d'équipe.

Un ticket n'apparaît qu'une fois : dans la section qui dit ce qui le retient, et jamais plus bas
si une notification l'attend déjà.

## La couleur de l'app

LinearTodo est bleu, [GitTodo](https://github.com/Joris-SEBIRE/gittodo) est violet. La couleur porte l'anneau du prochain
cycle, le compteur animé qui le remplace pendant une lecture, le compte secondaire, les titres de
section — icône et texte — et les titres de la fenêtre de réglages. Le rouge reste réservé à
l'urgence, et la section des pannes garde la couleur de son niveau : là, l'alerte passe devant
l'identité.

## Réglages

Menu **Réglages et mode d'emploi**. La fenêtre contient les deux : à gauche un formulaire pour
tous les réglages, à droite le mode d'emploi complet, alimenté par les valeurs de ton
installation.

Les réglages sont écrits dans `~/.config/lineartodo/config.json`, relu à chaud. Le fichier se
complète seul quand une option apparaît.

## Voir en tant que

Sous-menu **Voir en tant que** : les membres du workspace, les plus récemment vus en tête.

La boîte de réception est celle de ta clé : **elle n'existe pas pour un collègue**, et Linear n'a
aucune API pour la lire à sa place. Le menu le dit alors, les deux pastilles tombent à zéro, et ce
qui reste est tout ce qui se déduit de ses tickets. C'est la réponse à « où en est un collègue »,
pas à « qu'a-t-il à lire ».

## Ce que l'app écrit sur ta machine

- `~/.config/lineartodo/config.json` : tes réglages.
- `~/Library/Application Support/LinearTodo/state.json` : éléments masqués et éléments déjà vus.
- `~/Library/Application Support/LinearTodo/status.json` : ce que la barre affiche, utile au
  diagnostic.
- `~/Library/Application Support/LinearTodo/errors.log` : les pannes et leur pile.
- `~/Library/Caches/LinearTodo/avatars/` : les photos de profil, gardées quatorze jours.
- `~/Library/LaunchAgents/fr.jsebire.lineartodo.plist`, seulement si tu actives le lancement au
  démarrage.

`make uninstall` retire tout cela, sauf `~/.config/lineartodo/`, pour ne pas perdre tes réglages.

## À qui l'app parle

- `api.linear.app`, avec ta clé : c'est la seule destination qui la reçoit.
- les hôtes d'images de Linear, sans clé, pour les photos de profil.

Aucune mutation GraphQL n'est émise : les seules requêtes sont la boîte de réception, des
recherches de tickets et l'annuaire du workspace. Ouvrir un ticket depuis le menu marque sa
notification lue côté Linear, parce que c'est ton navigateur qui la charge.

## Prudence avec une configuration reçue de quelqu'un d'autre

Un réglage fait exécuter un programme : `api_key_command`. N'importe quoi placé là sera exécuté
avec tes droits. Ne recopie pas un `config.json` venu d'ailleurs sans avoir lu ce champ.

## Quand ça va mal

- Un triangle d'avertissement apparaît en haut à gauche de la photo dès qu'une source ne répond
  plus, dans le coin que les deux comptes n'occupent pas : il ne masque donc jamais un nombre, il
  dit que ces nombres datent. Le menu ouvre
  alors une section qui nomme la source, l'erreur, depuis quand, et ce que cela fausse. Trois
  niveaux : jaune quand rien n'est cassé chez Linear mais que l'app ne peut plus tout lire, orange
  quand une source auxiliaire échoue, rouge quand la boîte de réception elle-même échoue. Linear
  ne publie pas d'API d'état : `linearstatus.com` tranche.
- `make print` reproduit le contenu du menu en texte, sans interface.
- `PYTHONPATH=src .venv/bin/python -m lineartodo --print --as <personne>` montre ce que verrait un
  collègue.
- `errors.log` et `status.json` disent le reste. Ils contiennent les titres de tes tickets et ton
  handle Linear : relis-les avant de les joindre à une issue publique.

Si l'icône disparaît de la barre alors que l'app tourne, c'est que macOS l'a reléguée hors écran
faute de place. Réduis sa largeur avec le réglage *Format de l'élément*, ou ⌘-glisse l'icône vers
la droite.

## Architecture

- `src/lineartodo/app.py` : élément de barre, menu, minuteries, rendu.
- `src/lineartodo/engine.py` : règles de déduction, à partir des notifications et des tickets.
- `src/lineartodo/linear.py` et `queries.py` : appels Linear et documents GraphQL.
- `src/lineartodo/models.py` : types, sections, ordre d'affichage, table des natures de
  notification.
- `src/lineartodo/settings.py` et `help.py` : formulaire des réglages et mode d'emploi.
- `src/lineartodo/state.py`, `config.py`, `avatars.py`, `formatting.py`, `launchagent.py` : état
  local, réglages, visages, mise en forme des durées, lancement au démarrage.

`engine.py` ne connaît ni AppKit ni le réseau : il transforme des notifications et des tickets en
lignes à afficher, ce qui permet de le vérifier avec `make print`.

## Support

Version 1.0.0. Interface en français uniquement. Le bundle n'est ni signé ni notarisé : il est
construit sur ta machine, donc macOS ne le met pas en quarantaine, mais il ne se distribue pas tel
quel.

## Marques

Projet personnel, sans aucun lien avec l'éditeur de Linear ni son approbation. « Linear » et son
logo appartiennent à leur propriétaire ; ce dépôt n'utilise que son API publique, en lecture.

## Licence

MIT, voir `LICENSE`.
