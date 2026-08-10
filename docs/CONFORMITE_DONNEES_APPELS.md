# Données d'appel — traitement, conservation, conformité

Ce que le Call Tracker collecte, où ça vit, combien de temps, et ce qui reste
à décider. Rédigé au regard de la **loi 18-07** relative à la protection des
personnes physiques dans le traitement des données à caractère personnel
(Algérie).

> ⚠️ **Ce document décrit un dispositif technique, il ne vaut pas avis
> juridique.** Les qualifications ci-dessous sont celles que l'équipe retient
> ; elles doivent être validées par un conseil avant tout usage hors de
> l'entreprise, et **impérativement** avant de vendre le produit à un tiers.

---

## 1. Ce qui est collecté

| Donnée | Origine | Justification |
|---|---|---|
| Numéro de téléphone du correspondant | journal d'appels du téléphone | rattacher l'appel au bon client |
| Sens de l'appel (entrant, sortant, manqué) | journal d'appels | mesurer l'activité commerciale |
| Durée | journal d'appels | distinguer une conversation d'un appel non abouti |
| Horodatage de début | journal d'appels | chronologie du suivi |
| Commercial | jeton de l'appareil | attribuer l'appel |
| Note libre | saisie du commercial | contexte du suivi |

**Ce qui n'est PAS collecté**, et ne doit pas le devenir sans reprendre ce
document : le contenu des conversations (aucun enregistrement audio, hors
scope explicite de la spec §4.3), le carnet de contacts du téléphone, la
position, et les appels hors plage horaire configurée.

⚠️ **Le correspondant n'est pas l'utilisateur de l'application.** C'est le
point qui distingue ce traitement d'un simple outil interne : les données
portent sur des tiers — clients, prospects, mais aussi toute personne qui
appelle le commercial — qui n'ont pas installé l'application et n'en
connaissent pas l'existence.

---

## 2. Le passé n'est jamais collecté

**Le suivi démarre à l'activation de la capture.** Le journal d'appels du
téléphone est antérieur à l'installation ; il n'est pas remonté. Le curseur de
balayage est posé à l'instant de l'activation, et l'application ne lit que
ce qui vient après.

Sans cette règle, la première activation verserait dans le CRM des **années**
d'appels privés. Mesuré le 2026-08-10 sur le premier téléphone réel branché :
**3000 appels** dans son journal, tous candidats au départ. Le défaut était
invisible sur émulateur, dont le journal est vide.

Ce n'est pas seulement de l'hygiène. L'avis affiché au commercial dit que
« l'application transmet vos appels professionnels », **au présent** ; une
collecte rétroactive de cette ampleur contredirait l'information donnée et ne
serait pas proportionnée à la finalité poursuivie.

Deux barrières redondantes côté application, décrites dans
`apps/mobile/README.md` — la seconde tient l'invariant là où il est consommé,
pour qu'aucun chemin détourné (restauration de sauvegarde, provisionnement
automatisé) ne le contourne en silence.

---

## 3. Les trois filtres à la source

La meilleure protection reste de ne pas collecter. Trois limites sont en
place, et ce sont les seules que l'application applique :

1. **Plage horaire** (réglage `fromHour` / `toHour`, 8 h – 19 h par défaut) :
   hors de cette plage, l'appel n'est pas capturé du tout — pas capturé puis
   filtré, jamais lu.
2. **Interrupteur de capture** : le commercial peut suspendre toute capture.
3. **Types ignorés** : messagerie vocale, transferts et refus externes ne sont
   pas journalisés.

**Pas de marquage « appel privé »** — décision du 2026-08-09. La ligne est
professionnelle : tous les appels qui y transitent le sont par définition, et
il n'y a pas de vie privée du salarié à protéger dans ce flux. La spec §4.1 le
prévoyait ; l'item est retiré.

⚠️ **Ce que cette décision ne règle pas.** Le CORRESPONDANT, lui, peut être un
particulier appelant depuis son mobile personnel. Ce n'est plus une question de
vie privée du salarié, c'est celle de la conservation et de l'effacement —
traitée au §4 et au §5.

---

## 4. Où vivent les données, et combien de temps

| Emplacement | Contenu | Durée |
|---|---|---|
| Téléphone — file locale SQLite | appels non encore remis | jusqu'à remise, puis conservés en base locale sans purge |
| Téléphone — cache de fiches | nom, société, étape, dernière note | 30 minutes |
| Odoo — `call.tracker.log` | l'appel et sa note | `CALL_TRACKER_RETENTION_DAYS` |
| Odoo — `call.tracker.audit` | accès en lecture et en écriture | `CALL_TRACKER_RETENTION_DAYS` |
| Odoo — fil de discussion CRM | la note, recopiée | **indéfinie** |
| Odoo — pistes qualifiées à la main | numéro et intitulé | **indéfinie** |

### Ce qui n'est pas purgé, et pourquoi

**Aucune piste n'est plus créée automatiquement** (décision du 2026-08-09) : un
numéro inconnu n'entre dans le CRM que si un commercial le qualifie
délibérément. Le volume de données personnelles conservées indéfiniment s'en
trouve considérablement réduit — c'est le principal effet de cette décision au
regard de la 18-07, au-delà de la propreté du pipeline.

Restent hors purge : les **pistes qualifiées à la main**, et les **notes
recopiées dans le fil CRM**. Ce n'est pas un oubli — ce sont des données
commerciales, pas des traces techniques, et les effacer supprimerait
l'historique d'une affaire en cours.

Une demande d'effacement portant sur un correspondant impose donc **une
intervention manuelle** sur trois modèles : `call.tracker.log`, `crm.lead`, et
le fil `mail.message` associé.

**La file locale du téléphone n'est jamais purgée non plus.** Les appels déjà
remis y restent indéfiniment, en état `sent` — une copie des mêmes données, sur
un appareil qui se perd et se revend. Voir §8.

---

## 5. Le réglage de rétention

`CALL_TRACKER_RETENTION_DAYS`, dans `.env.production` du serveur. Une tâche
planifiée quotidienne supprime au-delà.

**Durée retenue le 2026-08-09 : 1095 jours, soit trois ans.** C'est la durée
habituellement admise pour des données de prospection commerciale : elle couvre
les cycles de renouvellement et la comparaison d'une année sur l'autre, tout en
restant proportionnée à la finalité — ce qu'exige la 18-07. Elle est inscrite
dans `.env.production.example`.

> ⚠️ **Si la variable est absente, la purge ne s'exécute pas.** Le repli
> technique est `0`, c'est-à-dire conservation indéfinie : un fichier
> d'environnement mal renseigné ne doit pas faire disparaître des données. La
> conséquence est qu'une instance déployée sans cette variable n'a **aucune**
> politique de rétention, sans que rien ne le signale. La tâche planifiée le
> journalise à chaque passage : « aucune retention configuree, rien a purger ».

---

## 6. Qui accède à quoi

| Rôle | Appels | Journal d'audit | Jetons |
|---|---|---|---|
| Utilisateur interne | lecture | — | — |
| Responsable des ventes | lecture, modification, suppression | — | — |
| Administrateur | tout | lecture | tout |

Le **jeton d'appareil** n'ouvre aucun accès Odoo : il désigne un appareil, et
le contrôleur décide seul de ce qui est écrit et de ce qui est renvoyé. La
route de lecture ne renvoie que quatre champs — nom, société, étape, dernière
note — jamais le courriel, l'adresse ni aucune donnée financière.

Tout accès, en lecture comme en écriture, laisse une trace dans
`call.tracker.audit`, y compris les tentatives refusées, avec l'adresse IP.

### Révoquer un appareil perdu ou volé

*CRM > Call Tracker > Appareils* → décocher **Actif**, ou **Générer un jeton**
(l'ancien cesse aussitôt de valoir).

**L'effet est immédiat.** `_authentifier` revérifie `active` à chaque requête
et il n'y a aucun cache côté serveur : la requête suivante du téléphone est
refusée. Les appels déjà journalisés ne bougent pas, et le compte du
commercial n'est pas touché.

**Ce que la révocation ne récupère pas** — à savoir avant de décider si elle
suffit :

| Reste sur l'appareil | Portée |
|---|---|
| Cache des fiches contact | Nom, société, étape et dernière note des numéros consultés dans les **30 dernières minutes** |
| File locale des appels | Les appels capturés, y compris déjà remis — numéros, durées, notes |
| Jeton | Inutilisable, mais toujours présent dans le stockage de l'app |

**Le risque réel, dans l'ordre.** Le jeton ne porte aucun droit Odoo : il ne
peut ni lire une fiche complète, ni écrire ailleurs que dans
`call.tracker.log`. Restent donc, par ordre de gravité :

1. **La lecture du carnet** par `/contacts/<fragment>` — la seule route qui
   parcourt. C'est ce que `CALL_TRACKER_SEARCH_SCOPE=own` réduit, et la raison
   pour laquelle ce réglage existe.
2. **L'injection de faux appels**, qui fausse les indicateurs sans exposer de
   donnée.
3. Le cache local, borné à 30 minutes et à ce qui a déjà été consulté.

**Le journal d'audit dit ce qui a été fait avec le jeton** avant la
révocation : chaque lecture y figure, avec le numéro, l'adresse IP et
l'horodatage. C'est là qu'on regarde pour décider s'il faut prévenir qui que
ce soit.

⚠️ Effacer l'appareil à distance n'est pas possible depuis Odoo. Sur un
téléphone d'entreprise géré, c'est le MDM qui le fait ; sinon, la révocation
plus l'expiration du cache sont tout ce dont on dispose.

### ⚠️ L'asymétrie entre le CRM et le téléphone

**Dans Odoo, tout est cloisonné** : un commercial ne voit que ses appels, sa
couverture, ses affaires — les règles d'enregistrement le garantissent.

**Depuis le téléphone, non.** Les routes tournent en `sudo()` par conception :
le jeton d'appareil ne porte aucun droit Odoo, et c'est le contrôleur qui
décide de tout. Vérifié le 2026-08-10 : un appareil retrouvait le client d'un
autre commercial, sur la recherche comme sur la fiche.

`CALL_TRACKER_SEARCH_SCOPE` permet désormais de cloisonner la **recherche**
(`own`) ou de la laisser ouverte (`all`, défaut). **Décision du 2026-08-10 :
ouvert**, l'équipe étant petite et chacun couvrant les clients des autres.
À revoir dès que l'effectif grandit — c'est le réglage qui divise le dégât
d'un téléphone volé par le nombre de commerciaux.

La fiche affichée à la sonnerie reste ouverte dans tous les cas : ne pas
savoir qui appelle ferait décrocher à l'aveugle.

---

## 7. L'information des commerciaux — fait

Un écran d'avis s'ouvre au **premier lancement** de l'application et barre
l'accès aux onglets tant qu'il n'a pas été lu. Il dit, dans cet ordre : ce qui
est enregistré, **ce qui ne l'est pas**, qui peut le lire, combien de temps,
et à qui s'adresser. Il reste consultable à tout moment depuis
*Réglages > Information*.

C'était le dernier maillon manquant : toute la chaîne technique fonctionnait
sans que la personne enregistrée en soit informée.

### Trois choix qui font la différence entre informer et faire signer

**« Ce qui n'est pas enregistré » vient en deuxième, pas en dernier.** Le
contenu des conversations, les messages, les contacts personnels, la
position : c'est la question que se pose réellement quelqu'un à qui on annonce
que ses appels sont suivis. La repousser en bas de page laisse la crainte
s'installer pendant toute la lecture.

**Le sélecteur de langue est sur l'écran lui-même.** En porte, c'est le seul
écran accessible. Un avis rédigé dans une langue que le lecteur ne pratique
pas n'est pas une information, et l'accusé de lecture qui suit ne vaudrait
rien. Français, anglais, arabe.

**L'accusé de lecture porte un numéro de version, pas un booléen.** Le jour où
l'entreprise se met à capturer autre chose, `noticeVersion` est incrémenté et
chacun revoit l'avis. Avec un simple « déjà vu », le premier accord serait
définitif et porterait sur un texte qui n'existe plus — un défaut totalement
silencieux. Un test le verrouille.

### La durée affichée vient du serveur

L'écran n'annonce pas une durée codée en dur : le serveur renvoie
`retention_days` à chaque appel accepté, l'application le retient et l'affiche.
Une valeur recopiée dans le téléphone finirait par annoncer trois ans quand le
serveur en garde cinq — et un avis faux est pire que pas d'avis.

Trois états, distingués à l'écran parce qu'ils disent des choses différentes :

| État | Ce que voit le commercial |
|---|---|
| Durée connue, > 0 | « effacés au bout de 1 095 jours — soit environ 3 ans » |
| Durée connue, = 0 | « aucune suppression automatique n'est configurée » |
| Pas encore reçue | « fixée par votre employeur ; s'affichera au premier appel transmis » |

Le rejeu d'un appel déjà remis porte la durée lui aussi : sans cela, un
téléphone à jour ne recevrait plus que des `duplicate` et n'apprendrait jamais
la politique de l'instance.

### ⚠️ Ce que l'écran ne peut pas garantir

La capture vit côté natif et ne dépend pas de l'application Flutter. **Un
téléphone configuré par quelqu'un d'autre puis remis en main propre capture dès
le premier appel, que le titulaire ait vu cet écran ou non.** Aucun code ne
peut distinguer qui tient le téléphone.

La remise en main propre reste donc une étape humaine : faire ouvrir
l'application devant la personne, la laisser lire, et seulement ensuite activer
la capture dans les réglages.

---

## 8. Ce qui reste à faire

Par ordre de ce qui bloquerait un usage réel :

1. **Procédure d'effacement**, aujourd'hui manuelle et sur trois modèles.
2. **Purge de la file locale** des appels déjà remis, côté téléphone.
3. **Qualification en cas de vente à un tiers** : l'éditeur deviendrait
   sous-traitant, ce qui appelle un contrat de sous-traitance et une revue
   juridique complète. Hors sujet tant que l'usage reste interne, bloquant dès
   le premier client.

**Réglé depuis la première version de ce document** : l'information des
commerciaux (§7), la durée de rétention (1095 jours), la suppression de la
création automatique de pistes, et le marquage « appel privé », écarté parce
que la ligne est professionnelle.
