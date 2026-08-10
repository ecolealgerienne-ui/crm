# Call Tracker — addon Odoo

Reçoit les appels capturés par l'application mobile et les journalise dans
`call.tracker.log`, rattachés au contact ou à la piste correspondant au numéro.

## Pourquoi un module, et pas l'API générique d'Odoo

Une clé API Odoo hérite des **droits complets** de l'utilisateur associé : il
n'existe aucun moyen natif de restreindre un accès externe à « écrire un
journal d'appel et rien d'autre ». Ce module expose ses propres routes, avec
son propre jeton, révocable sans toucher à aucun compte.

Le jeton ne porte **aucun droit Odoo** : il désigne un appareil, rien de plus.
Ce qui est écrit et ce qui est renvoyé est décidé dans `controllers/main.py`,
jamais par les ACL d'un compte.

## Contrat de l'API

### `POST /call_tracker/log_call`

```
Authorization: Bearer <jeton de l'appareil>
Content-Type: application/json
```

```json
{
  "client_event_id": "uuid-genere-par-l-app",
  "phone_number": "+213555000000",
  "direction": "outbound",
  "duration_seconds": 142,
  "started_at": "2026-08-09T14:32:00Z"
}
```

Tous les champs sont obligatoires sauf `duration_seconds` (défaut 0).
**Un champ non listé fait rejeter la requête** — il signale un désaccord de
version entre l'app et le serveur, et l'ignorer ferait journaliser des appels
amputés sans que personne ne le remarque.

`started_at` doit porter un fuseau (`Z` ou `+HH:MM`). Un horodatage nu est
refusé : le téléphone peut être sur n'importe quel fuseau, et le supposer UTC
décalerait les appels de plusieurs heures en silence.

Pas de `rep_external_id`, contrairement à la spec : le jeton identifie
l'appareil, et l'appareil porte le commercial.

| Réponse | Code | Sens |
|---|---|---|
| `{"status":"logged","call_id":1,"linked_record":"crm.lead,26","retention_days":1095}` | 201 | appel journalisé |
| `{"status":"duplicate","call_id":1,...,"retention_days":1095}` | 200 | déjà reçu — voir ci-dessous |
| `{"status":"unauthorized"}` | 401 | jeton absent, inconnu ou révoqué |
| `{"status":"invalid","detail":"..."}` | 400 | charge utile refusée |

`linked_record` vaut `null` si le numéro ne correspond à rien.

`retention_days` est la politique de conservation de l'instance, telle que la
lit le serveur dans son `.env`. Elle est renvoyée pour que l'application
mobile puisse l'annoncer sur son écran d'information : une durée recopiée en
dur dans le téléphone finirait par afficher trois ans quand le serveur en
garde cinq. Le **rejeu** la porte aussi, sinon un téléphone déjà à jour ne
recevrait plus que des `duplicate` et n'apprendrait jamais la politique. Ce
n'est pas une donnée personnelle : c'est ce que la personne enregistrée a le
droit de savoir.

### `GET /call_tracker/contact/<numero>`

Fiche minimale pour l'affichage à la sonnerie (Caller ID). Même
authentification.

```json
{ "status": "found", "name": "Ahmed Benali", "company": "Marché Central",
  "last_notes": "Relance prévue vendredi", "crm_stage": "Négociation" }
```

`404 {"status":"not_found"}` si le numéro ne correspond à rien — et non un
objet vide : l'app doit distinguer « inconnu au CRM » de « connu mais sans
information », qui s'affichent différemment.

⚠️ **La liste blanche des quatre champs est écrite en dur dans
`models/call_tracker_log.py`, et nulle part ailleurs.** Le contrôleur travaille
en `sudo()` : il a accès à tout le contact. Rien dans les droits d'Odoo
n'empêchera courriel, adresse ou chiffre d'affaires de sortir — c'est ce code
seul qui les retient. Un test vérifie sur la réponse brute qu'aucun d'eux
n'apparaît.

`last_notes` est le dernier message de type `comment` du fil, converti en texte
et tronqué à 200 caractères. Les notifications automatiques (changement
d'étape, courriel envoyé) sont écartées : elles noieraient la vraie note sous
du bruit à chaque sonnerie.

### `GET /call_tracker/activities` — les appels a passer

Les activites de type appel programmees dans le CRM pour le commercial de
l'appareil, echeance la plus ancienne d'abord.

```json
{"status":"found","count":2,"results":[
  {"id":17,"client":"Relance Acme","phone":"+213555123456",
   "deadline":"2026-08-08","state":"overdue",
   "summary":"Relancer sur le devis","note":""}]}
```

**La seule route qui rende quelque chose au commercial au lieu de lui
prendre.** Tout le reste du dispositif est retrospectif ; celle-ci est la
raison d'ouvrir l'application. Ce n'est pas qu'une question d'adoption : on a
mesure sur un OnePlus que la surcouche gele l'app ecran eteint, et que la
tache d'envoi ne tourne qu'au reveil. **Une application qu'on n'ouvre jamais
est une application dont la file d'envoi ne se vide pas.**

⚠️ **Le filtre porte sur `activity_type_id.category == 'phonecall'`, pas sur
le nom du type.** « Call » est un libelle : il se traduit, il se renomme. Une
instance en francais l'appellerait « Appel » et un filtre sur le nom rendrait
une liste vide sans que rien ne le signale. Un test le verrouille en renommant
le type.

⚠️ **Aucun reglage de perimetre ici.** Une activite est assignee a un
utilisateur et le jeton designe l'appareil donc le commercial : le
cloisonnement est dans la donnee. Contrairement a la recherche de contacts, il
n'y a rien a debattre.

`state` — `overdue` / `today` / `planned` — est **calcule par Odoo**, dans le
fuseau de l'utilisateur. Le recalculer cote telephone donnerait deux verites
pour la meme echeance, qui divergeraient au passage de minuit.

Une activite **sans numero** est renvoyee quand meme : la masquer ferait
perdre une tache reelle pour un champ manquant. L'application l'affiche sans
bouton d'appel.

### `POST /call_tracker/activity/<id>/done`

⚠️ **L'appartenance est reverifiee cote serveur.** Rien n'empeche un jeton
vole d'envoyer des identifiants au hasard — et une tache qui disparait de la
liste d'un collegue ne se remarque pas, elle s'oublie.

`404` aussi bien pour « inexistante » que pour « pas la votre » : les
distinguer renseignerait sur le portefeuille des autres.

⚠️ **Odoo 19 ne supprime plus une activite close, il la desactive.** Le
filtre `active` implicite l'ecarte donc des recherches suivantes — mais un
test ecrit pour une version anterieure, qui verifierait la disparition de la
ligne en base, passerait a cote. Ce qui compte est qu'elle ne revienne plus
sur le telephone.

### `GET /call_tracker/contacts/<fragment>`

Contacts dont le numéro **contient** ce fragment de chiffres. Sert la
recherche manuelle de l'application ; la route précédente sert la sonnerie.

| Réponse | Code |
|---|---|
| `{"status":"found","count":2,"results":[{"name","company","phone","crm_stage"}]}` | 200 |
| `{"status":"not_found","count":0,"results":[]}` | 200 |
| `{"status":"too_short","min_digits":4}` | 400 |
| `{"status":"unauthorized"}` | 401 |

⚠️ **C'est la route la plus sensible du module.** Un fragment court interroge
tout le carnet d'adresses, alors que l'authentification ne repose que sur un
jeton d'appareil, sans droits Odoo. Trois bornes, chacune pour un scénario
précis :

- `FRAGMENT_MIN = 4` — sans minimum, `0` rendrait un échantillon de tout ;
- `RESULTATS_MAX = 10` — un téléphone perdu ne doit pas vider le carnet en
  quelques requêtes ;
- **trace d'audit avec le fragment ET le nombre de résultats** — une
  énumération se reconnaît à sa forme : des recherches courtes en rafale,
  chacune rendant le maximum. Sans le compte, la trace ne dit pas si le
  carnet a été effleuré ou vidé. Le refus « trop court » est journalisé lui
  aussi, et c'est le cas qui compte le plus.

Elles limitent le débit, **elles n'empêchent pas** une énumération patiente.
Ce qui réduit vraiment le dégât, c'est le périmètre — voir ci-dessous.

### Le périmètre de recherche

`CALL_TRACKER_SEARCH_SCOPE`, dans le `.env` du serveur, au même endroit que la
durée de rétention.

| Valeur | Effet |
|---|---|
| `all` | Tout le carnet d'adresses. **Défaut**, et comportement historique |
| `own` | Les clients du commercial de l'appareil, ceux de ses sociétés, et ceux des affaires qui lui sont assignées |

Être « à moi » se décline en trois, et il faut les trois : la fiche m'est
assignée, la **société** dont elle dépend m'est assignée — un interlocuteur
n'a presque jamais de commercial propre —, ou une **affaire** à mon nom la
désigne : un prospect n'a souvent aucun commercial sur sa fiche, seulement sur
sa piste. En oublier un rendrait la recherche aveugle là où elle sert le plus.

⚠️ **Les deux replis ne vont pas dans le même sens, et c'est voulu.** Une
variable *absente* rend `all` : ne rien configurer est normal, et changer le
comportement sous les pieds d'un exploitant qui n'a rien demandé serait pire.
Une valeur *illisible* rend `own` : c'est une erreur, et une faute de frappe
ne doit pas ouvrir le carnet d'adresses en silence. Restreindre à tort se
remarque en une heure — un commercial ne retrouve plus ses clients ; ouvrir à
tort ne se remarque jamais.

⚠️ **La fiche à la sonnerie n'est PAS concernée.** Elle reste ouverte quel que
soit ce réglage : quand le téléphone sonne, il faut savoir qui appelle, même
si la fiche appartient à un collègue en congé. Afficher « inconnu » ferait
décrocher à l'aveugle, ce qui est pire que de ne rien afficher.

Le périmètre appliqué accompagne le nombre de résultats dans la trace
d'audit : sans lui, « aucun résultat » ne dit pas si le client n'existe pas ou
s'il appartient à un collègue, et le premier réflexe serait de soupçonner une
panne.

`400` et non une liste vide sur un fragment trop court : « trop court » et
« aucun résultat » appellent deux messages différents à l'écran, et l'app ne
peut pas les distinguer si le serveur répond la même chose.

### L'idempotence, et pourquoi elle renvoie 200

L'app garde une file locale persistante et réémet ce qu'elle n'a pas pu
livrer : **les réessais sont certains, pas hypothétiques.** Un
`client_event_id` déjà reçu renvoie donc `200 duplicate` et non une erreur —
un 4xx ferait réessayer l'app indéfiniment dans le seul cas où tout va bien.

Deux garde-fous, parce qu'un seul ne suffit pas : une recherche préalable, et
un index unique SQL qui tranche si deux réessais se croisent.

## Le jeton

Généré depuis *CRM > Call Tracker > Appareils*, bouton **Générer un jeton**.
Affiché **une seule fois** : seule son empreinte SHA-256 est conservée.

Un SHA-256 nu suffit, et ce n'est pas un raccourci — les fonctions lentes
(bcrypt, pbkdf2) servent à rendre coûteuse l'énumération de secrets à faible
entropie, c'est-à-dire de mots de passe humains. Un jeton de 256 bits d'aléa
n'a rien à énumérer.

Régénérer un jeton **révoque l'ancien**. Décocher *Actif* révoque l'appareil
sans toucher au compte du commercial ni aux appels déjà journalisés.

## Rapprochement des numéros

Comparaison sur les **9 derniers chiffres**, parce qu'un mobile algérien
s'écrit indifféremment `0555000000`, `+213555000000` ou `00213555000000`.
Un numéro de moins de 9 chiffres n'est rapproché de rien — mieux vaut aucun
rattachement qu'un rattachement au hasard.

Les colonnes interrogées sont **détectées à l'exécution** et non écrites en
dur : `mobile` a disparu de `res.partner` et de `crm.lead` en Odoo 19, et une
requête sur une colonne absente échoue au lieu de ne rien trouver. Le champ
`phone_sanitized` (normalisation E.164 d'Odoo) est interrogé en plus de
`phone`, car il est NULL quand Odoo n'a pas su déduire le pays.

Aucun index ne couvre cette expression SQL. Sans conséquence sur le carnet
d'adresses d'une PME, mais **c'est le premier endroit à revoir si le
rapprochement ralentit**.

## Éprouver le module

```bash
wsl -e bash -lc "cd /mnt/c/Users/amar/Desktop/shope/echangoCrm && \
  docker compose run --rm -T odoo odoo -d echango_crm -u call_tracker --stop-after-init && \
  docker compose restart odoo"
```

Puis, avec un jeton généré dans l'interface :

```bash
curl -i -X POST http://localhost:8169/call_tracker/log_call \
  -H "Authorization: Bearer <jeton>" -H "Content-Type: application/json" \
  -d '{"client_event_id":"essai-1","phone_number":"+213555000000",
       "direction":"outbound","duration_seconds":42,
       "started_at":"2026-08-09T14:32:00Z"}'
```

## Depuis une fiche client, voir ses appels

Le rattachement `partner_id` / `lead_id` existait depuis le début, mais
seulement en base. Un bouton sur la fiche contact et sur la piste ouvre
désormais la liste de leurs appels.

Sur une **société**, le compteur additionne les appels de ses contacts
rattachés (`child_of`) : les appels sont journalisés au nom de
l'interlocuteur, et un compteur limité à la société elle-même afficherait zéro
là où il y a le plus à voir.

## Trace au fil, et note prise après l'appel

**Tout appel rattaché est publié dans le fil** de la piste — ou à défaut du
contact — entrant comme sortant, avec ou sans note. Ouvrir une fiche client
suffit à voir qu'on l'a appelé mardi. Sous-type `mail.mt_note` dans tous les
cas : une note interne, jamais un message envoyé au client.

Le champ `note` reste facultatif dans la charge utile de `log_call`, plafonné
à 1000 caractères.

⚠️ **Deux types de message, et la distinction est structurante.** Ce même fil
est relu par `fiche_contact` pour alimenter le Caller ID, qui affiche le
dernier `comment`.

| Appel | Type | Corps | Vu au Caller ID |
|---|---|---|---|
| avec note | `comment` | en-tête + note | oui |
| sans note | `notification` | en-tête + « 45 s · répondu » | non |

Sans cette distinction, chaque appel muet écraserait au Caller ID la dernière
note utile par un « Appel sortant — +213… » qui n'apprend rien. La fiche
resterait pleine et deviendrait inutile, sans la moindre erreur pour le
signaler. Élargir le filtre de `_derniere_note` au-delà de `comment` rouvre
exactement ce défaut ; deux tests le verrouillent.

Le report referme une boucle : la note écrite après un appel s'affiche au
suivant.

⚠️ Sous-type `mt_note` et non un commentaire public : se tromper ici
enverrait la note au client par courriel.

## L'historique des notes, rassemblé sur le compte

Bouton **Notes** sur la fiche contact : toutes les notes internes du **compte**
— la société, ses contacts rattachés et toutes ses pistes — du plus récent au
plus ancien.

**Le problème que cet écran résout.** `_publier_note` publie sur
`lead_id` **ou** `partner_id` : la piste l'emporte. Mesuré sur des données
réelles avant ce chantier :

```
Appels avec note          : 8
  publiés sur une PISTE   : 7
  publiés sur une FICHE   : 1
```

Sept notes sur huit vivaient dans le fil d'une piste, et la fiche du client
n'en montrait qu'une. L'historique est éclaté **par construction**, et il
l'est de plus en plus à mesure qu'un client accumule des affaires.

**Le compte, pas le contact seul.** Les appels sont journalisés au nom de
l'interlocuteur qu'on a eu au téléphone ; ouvrir « Acme Corporation » doit
montrer ce qui s'est dit avec Floyd comme avec ses collègues, sinon il faut
ouvrir cinq fiches pour reconstituer une conversation. Même raisonnement que
l'écran de couverture.

⚠️ **Interroge `mail.message`, pas une vue SQL.** Les messages portent des
règles d'accès fines dans Odoo ; une vue les contournerait et rendrait
visibles des notes de pistes qu'on n'a pas le droit de voir. Passer par le
modèle laisse Odoo faire ce filtrage, gratuitement et correctement.

Le domaine retient les notes **internes** et écarte trois sortes de bruit :

| Écarté | Pourquoi |
|---|---|
| Sous-types `Opportunity Created`, `Stage Changed` | Du mouvement de pipeline, pas ce qui s'est dit |
| `user_notification` | Mécanique interne d'Odoo ; porte le même sous-type qu'une note |
| Sous-type `Discussions` | Un courriel ou un SMS **envoyé au client** — le relire à la sonnerie ferait redire au commercial ce que le client a déjà lu |
| Corps vide | Messages de suivi ne portant qu'un changement de champ |

## Enrichir depuis le CRM — et pourquoi l'appel reste figé

**L'appel est en lecture seule, définitivement.** Ses faits — numéro, sens,
durée, horodatage, appareil, commercial — sont le socle du reporting. Une
durée corrigeable rendrait chaque chiffre négociable en réunion, et
`delivery_lag_minutes`, qui doit précéder tout classement entre commerciaux,
ne vaudrait plus rien.

**Ce qui s'ajoute après coup va au fil du client.** L'appel est le compte
rendu d'un *événement*, figé par nature ; le fil est l'histoire de la
*relation*, cumulative par nature. Une note mal dictée dans la voiture ne se
réécrit donc pas — on écrit la bonne en dessous.

Et cette boucle **existait déjà sans que rien ne le signale** :
`_derniere_note` lit le dernier commentaire du fil de la piste ou du contact.
Tout ce qu'un responsable, une assistante ou le commercial lui-même écrit dans
ce fil **s'affiche sur le téléphone à la sonnerie suivante**.

Trois ajouts pour rendre ce chemin visible, sur la fiche d'un appel :

| | |
|---|---|
| **Compléter la note** | Ouvre un assistant qui publie dans le fil du client. Un geste au lieu de trois — ouvrir la fiche, trouver le fil, cliquer « Log note » |
| **Ouvrir la fiche client** | La piste, ou à défaut le contact |
| Champ `last_note` | Ce que le téléphone affichera au prochain appel, lisible sans naviguer |

⚠️ **Le complément est publié sans en-tête**, contrairement à la trace d'un
appel. C'est ce même message que `_derniere_note` renvoie au Caller ID,
tronqué à 200 caractères : un « Appel sortant — +213… » en mangerait la moitié
pour redire ce que le fil affiche déjà à côté.

⚠️ **Pas de `sudo()` dans l'assistant.** Publier au nom de l'utilisateur réel
fait jouer les droits d'Odoo : personne ne doit pouvoir écrire dans le fil
d'une piste qu'il n'a pas le droit de voir, par le détour d'un appel. Le
contrôleur, lui, passe en sudo — il n'a justement aucun utilisateur derrière.

`last_note` n'est **pas stocké** : le fil grossit après l'appel, et une copie
figée dirait « dernière note » en montrant l'avant-dernière.

## Numéro inconnu — qualification manuelle

**Aucune piste n'est créée automatiquement.** Décision du 2026-08-09, qui
revient sur le premier choix : une création automatique remplit le pipeline de
taxis, de fournisseurs et de faux numéros, les rapports deviennent faux, et un
pipeline qu'on ne croit plus, personne ne le regarde.

Un appel sans correspondance rejoint la file **CRM > Call Tracker > Appels à
qualifier**. Le bouton *Créer une piste* — dans la liste comme sur la fiche —
en crée une, attribuée au commercial qui a passé ou reçu l'appel, et l'ouvre.

Deux choix qui font que la file se vide vraiment :

- **c'est un menu, pas un filtre.** Le risque de ne rien créer est de perdre un
  prospect entrant, qui ne peut pas avoir été créé à l'avance. Ce risque se
  traite par la visibilité de cette file — un filtre qu'il faut penser à cocher
  ne serait regardé par personne ;
- **qualifier un appel qualifie tous ceux du même numéro.** Sans cela, un
  prospect qui a rappelé trois fois laisserait deux appels derrière lui, et il
  faudrait recommencer le geste pour chacun.

Le type créé (`lead` ou `opportunity`) suit la configuration CRM du commercial
de l'appel — pas de celui qui clique. Créer un `lead` sur une base où l'étape
de qualification est désactivée le rendrait **invisible** : le menu
correspondant est masqué.

## Rétention

`CALL_TRACKER_RETENTION_DAYS`, lue dans l'environnement du serveur (injectée
par docker-compose depuis `.env.production`). Une tâche planifiée quotidienne
purge les appels **et** leurs traces d'audit au-delà.

Valeur retenue : **1095 jours (trois ans)**, durée habituellement admise pour
des données de prospection commerciale — elle couvre les cycles de
renouvellement et la comparaison d'une année sur l'autre, tout en restant
proportionnée à la finalité.

⚠️ **`0`, absente ou illisible = aucune purge.** Le sens de l'erreur est
choisi : un fichier d'environnement mal renseigné ne doit pas faire disparaître
des données. Mais tant que la valeur vaut 0, il n'y a pas de politique de
rétention — il y a une absence de politique, ce qui ne tient pas au regard de
la loi 18-07.

La limite se compte sur la **date de l'appel**, pas sur celle de son
enregistrement : un appel remonté avec trois semaines de retard, parce que le
téléphone est resté hors réseau, doit être daté de l'appel.

La durée est **annoncée à l'application mobile** dans la réponse de
`log_call`, qui l'affiche sur son écran d'information. Changer
`CALL_TRACKER_RETENTION_DAYS` change donc aussi ce que lisent les commerciaux,
sans rien à redéployer côté téléphone.

## Journal d'audit

`call.tracker.audit` — *CRM > Call Tracker > Journal d'audit*, réservé aux
administrateurs. Chaque journalisation d'appel **et chaque consultation de
contact** y laisse une ligne, y compris les tentatives refusées, avec l'IP
d'origine.

Les **lectures** sont le vrai sujet. Une écriture laisse une trace visible :
l'appel apparaît dans la liste. Une consultation ne laisse rien — sans ce
journal, un jeton volé pourrait parcourir le carnet d'adresses numéro par
numéro sans qu'il en subsiste la moindre trace. Le filtre *Refusés* fait
apparaître d'un coup d'œil un jeton révoqué resté dans un téléphone, ou
quelqu'un qui tâtonne.

L'écriture d'une trace ne peut jamais faire échouer l'appel qu'elle observe :
un journal d'audit qui casse la fonctionnalité est désactivé au premier
incident, et il n'y en a alors plus du tout.

## Tableau de bord

*CRM > Call Tracker > Activité téléphonique* — vues graphe et tableau croisé
sur le même modèle, ouvertes sur les sept derniers jours et groupées par
commercial.

La spec (§4.2) envisageait un tableau de bord dans l'application. Le faire ici
coûte deux vues et donne mieux : filtres, regroupements et export d'Odoo, et
chacun peut enregistrer sa propre lecture. Un écran natif en aurait figé une
seule.

La mesure par défaut est la **durée**, pas le nombre d'appels : dix appels de
cinq secondes ne valent pas dix conversations.

## Qui voit quoi

Deux niveaux, en un seul choix dans la fiche utilisateur (privilège
« Call Tracker ») :

| Niveau | Voit | Attribué à |
|---|---|---|
| Utilisateur | ses propres appels | tout commercial (`sales_team.group_sale_salesman`) |
| Responsable | tous les appels | responsable des ventes (`sales_team.group_sale_manager`) |

Le cloisonnement passe par deux règles d'enregistrement **non globales** :
Odoo les combine par OU entre groupes, donc le responsable bénéficie de la
règle large. Rendre la règle « utilisateur » globale l'écraserait par ET.

⚠️ Deux pièges qui ont coûté du temps, notés dans les fichiers concernés :

- **`res.groups.category_id` n'existe plus en Odoo 19**, remplacé par
  `privilege_id` vers un `res.groups.privilege`. L'ancien champ fait échouer
  l'installation, pas seulement l'affichage.
- **Les blocs `noupdate="1"` ne s'appliquent qu'à l'installation.** Les
  greffes sur les groupes de vente y étaient : les tests passaient (base
  neuve) et l'instance réelle, déjà installée, n'a jamais reçu les droits —
  plus personne ne voyait les appels, sans message.

Le compteur d'appels sur les fiches contact vérifie l'accès avant de compter :
sans cela, un comptable ouvrant une fiche verrait la **page entière** échouer
à cause d'un bouton qui ne le concerne pas.

## Indicateurs

Trois champs dérivés, stockés pour servir de colonnes de regroupement :

| Champ | Pourquoi |
|---|---|
| `outcome` | Un sortant sans réponse est journalisé `outbound` avec une durée nulle, **pas** `missed`. Sans ce champ, le taux de décroché est faux sur tout le sortant |
| `hour_of_day` | Le regroupement natif par heure donne « 9 août 14 h », pas « 14 h toutes dates confondues ». Calculé dans le fuseau du **commercial** |
| `delivery_lag_minutes` | Écart entre l'appel et son arrivée dans Odoo |

**Pas de champ « numéro de semaine »** : Odoo groupe déjà par semaine dans le
fuseau de l'utilisateur, un champ stocké serait en UTC, et un appel du dimanche
soir tomberait dans la mauvaise semaine.

Le **délai de remise** est la mesure à regarder avant tout classement entre
commerciaux. Quand une surcouche constructeur suspend l'application, rien ne
remonte — mais le journal du téléphone continue d'être écrit et le balayage
rattrape au réveil suivant. Le risque n'est donc pas la perte, c'est le
retard : un total mensuel reste juste, un chiffre journalier non. Voir
[docs/REPORTING_KPI.md](../../docs/REPORTING_KPI.md).

## Couverture du portefeuille

*CRM > Call Tracker > Couverture du portefeuille* — une ligne par compte
assigné, triée du plus délaissé au plus suivi. Le seul écran qui montre ce qui
ne s'est **pas** passé : un client jamais appelé n'apparaît dans aucune liste
d'appels.

Modèle `call.tracker.coverage`, une **vue SQL** (`_auto = False`) : le
dénominateur vit sur `res.partner`, et un modèle stocké devrait être réécrit à
chaque affectation de client.

⚠️ Deux pièges, commentés dans le modèle :

- **L'ORM ne vide pas son cache avant d'interroger une vue SQL** — il n'a aucun
  moyen de savoir de quelles tables elle dépend. Un client créé puis consulté
  dans la même transaction reste invisible. `_search` force le vidage de
  `res.partner` et `call.tracker.log`.
- **`days_since_last_call` est vide, pas zéro**, quand il n'y a jamais eu
  d'appel : zéro voudrait dire « appelé aujourd'hui », et un tri placerait les
  comptes délaissés en tête des mieux suivis.

Le portefeuille, c'est le champ *Commercial* de la fiche client. Non renseigné,
l'écran est vide — c'est un préalable humain, pas technique.

## Relance des affaires

*CRM > Call Tracker > Relance des affaires* — chaque affaire ouverte, avec la
date du dernier appel **rattaché à elle**, les plus délaissées en tête. Le
tableau croisé étape × jamais appelée montre où le pipeline stagne.

Modèle `call.tracker.lead.activity`, vue SQL comme la couverture.

⚠️ **Ce n'est pas un taux de conversion, et il n'y a volontairement aucun champ
de ce nom** — un test le vérifie. Le croisement est un instantané, pas un suivi
de cohorte : on ne sait pas si l'affaire a avancé *après* l'appel, et le biais
va dans un sens connu (on appelle d'abord ce qui paraît prometteur). Le publier
sous ce nom ferait conclure que téléphoner fait gagner des affaires — c'est
peut-être vrai, ce chiffre ne le démontre pas.

Seuls les appels rattachés à l'affaire comptent, pas ceux de son contact :
sinon une entreprise à plusieurs dossiers verrait tous ses dossiers marqués
relancés par un seul appel.

## Tests

197 tests couvrant le contrat HTTP des deux routes, l'idempotence, la
révocation, le rapprochement téléphonique, la qualification manuelle,
la note post-appel, les liens depuis les fiches CRM, la rétention, le
journal d'audit, les champs dérivés, le cloisonnement, la
couverture du portefeuille et la relance des affaires.

```bash
docker compose run --rm -T odoo odoo \
  --database=call_tracker_test --init=call_tracker \
  --test-enable --test-tags=/call_tracker --stop-after-init \
  --log-level=warn --log-handler=odoo.tests:INFO
```

⚠️ **`--test-tags=/call_tracker` n'est pas optionnel.** Sans lui,
`--test-enable` lance les 2296 tests de tous les modules installés, dont des
parcours navigateur qui échouent dans un conteneur sans `websocket-client` :
on croit alors avoir cassé quelque chose.

⚠️ **`--log-level=warn` seul ne montre RIEN**, pas même le succès : les
résultats sont journalisés en INFO. D'où `--log-handler=odoo.tests:INFO`.

## Limitation de débit

Posée côté Traefik, pas dans l'addon : voir le routeur `echangocrm-api` et le
middleware `echangocrm-api-limite` dans `docker-compose.crm.yml`. Les valeurs
sont hautes délibérément — les opérateurs mobiles algériens font du NAT à
grande échelle, et l'app vide sa file d'un trait au retour du réseau.

## Portée de version

**Odoo 19 uniquement**, décision du 2026-08-09. La spec §3.2 demandait 16 à 19 ;
le module utilise `_read_group(aggregates=…)`, les vues `<list>` et un
`post_init_hook(env)`, tous introduits en Odoo 17. Il tournerait probablement
en 17 et 18, mais ce n'est ni visé ni éprouvé.

## Pas encore fait

- **Purge des notes recopiées dans le fil de discussion** : la rétention
  supprime les appels et les traces, pas la note reportée sur la piste.
  Volontaire — c'est devenu une donnée commerciale — mais à connaître pour
  répondre à une demande d'effacement. Voir
  [docs/CONFORMITE_DONNEES_APPELS.md](../../docs/CONFORMITE_DONNEES_APPELS.md).
- **Écran d'information au premier lancement** de l'application.
