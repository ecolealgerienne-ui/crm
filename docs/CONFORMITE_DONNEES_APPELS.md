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

## 2. Les trois filtres à la source

La meilleure protection reste de ne pas collecter. Trois limites sont en
place, et ce sont les seules que l'application applique :

1. **Plage horaire** (réglage `fromHour` / `toHour`, 8 h – 19 h par défaut) :
   hors de cette plage, l'appel n'est pas capturé du tout — pas capturé puis
   filtré, jamais lu.
2. **Interrupteur de capture** : le commercial peut suspendre toute capture.
3. **Types ignorés** : messagerie vocale, transferts et refus externes ne sont
   pas journalisés.

⚠️ **Ce que ces filtres ne couvrent pas.** Un appel personnel reçu à 15 h est
capturé comme les autres. La plage horaire est un instrument grossier ; elle
protège la soirée, pas la vie privée dans la journée de travail. Si cela pose
problème, la parade est un interrupteur « appel privé » avant ou pendant
l'appel — **non implémenté à ce jour**, alors que la spec §4.1 le prévoyait.

---

## 3. Où vivent les données, et combien de temps

| Emplacement | Contenu | Durée |
|---|---|---|
| Téléphone — file locale SQLite | appels non encore remis | jusqu'à remise, puis conservés en base locale sans purge |
| Téléphone — cache de fiches | nom, société, étape, dernière note | 30 minutes |
| Odoo — `call.tracker.log` | l'appel et sa note | `CALL_TRACKER_RETENTION_DAYS` |
| Odoo — `call.tracker.audit` | accès en lecture et en écriture | `CALL_TRACKER_RETENTION_DAYS` |
| Odoo — fil de discussion CRM | la note, recopiée | **indéfinie** |
| Odoo — pistes créées automatiquement | numéro et intitulé | **indéfinie** |

### Ce qui n'est pas purgé, et pourquoi

**Les notes recopiées dans le fil CRM et les pistes créées automatiquement
survivent à la purge.** Ce n'est pas un oubli : une piste est une donnée
commerciale, pas une trace technique, et l'effacer supprimerait l'historique
d'une affaire en cours. Mais la conséquence doit être vue en face — **un
numéro appelé une seule fois laisse une piste dans le CRM pour toujours**, et
la note qui l'accompagne aussi.

Une demande d'effacement portant sur un correspondant impose donc aujourd'hui
**une intervention manuelle** sur trois modèles : `call.tracker.log`,
`crm.lead`, et le fil `mail.message` associé.

**La file locale du téléphone n'est jamais purgée non plus.** Les appels
remis y restent, en état `sent`. C'est le second manque connu.

---

## 4. Le réglage de rétention

`CALL_TRACKER_RETENTION_DAYS`, dans `.env.production` du serveur. Une tâche
planifiée quotidienne supprime au-delà.

> ⚠️ **La valeur par défaut est `0`, c'est-à-dire AUCUNE purge.** Ce défaut est
> délibéré côté technique — un fichier d'environnement mal renseigné ne doit
> pas faire disparaître des données — mais il est **inacceptable en
> exploitation** : tant qu'il vaut 0, il n'y a pas de politique de rétention,
> il y a une absence de politique.
>
> **Renseigner une durée fait partie de la mise en production**, au même titre
> que le mot de passe de la base.

Ordres de grandeur discutés : 365 jours pour conserver un exercice commercial
complet, 90 jours pour un simple suivi d'activité. **Aucune valeur n'a été
arrêtée à ce jour.**

---

## 5. Qui accède à quoi

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

---

## 6. Ce qui reste à faire

Par ordre de ce qui bloquerait un usage réel :

1. **Fixer `CALL_TRACKER_RETENTION_DAYS`.** Sans cela, rien de ce document ne
   tient.
2. **Informer les personnes concernées.** Les commerciaux doivent savoir que
   leurs appels sont journalisés ; c'est un point de droit du travail autant
   que de protection des données. Rien n'est prévu à ce jour — ni écran
   d'information au premier lancement, ni mention.
3. **Procédure d'effacement**, aujourd'hui manuelle et sur trois modèles.
4. **Marquage « appel privé »** (spec §4.1), qui manque.
5. **Purge de la file locale** des appels déjà remis.
6. **Qualification en cas de vente à un tiers** : l'éditeur deviendrait
   sous-traitant, ce qui appelle un contrat de sous-traitance et une revue
   juridique complète. Hors sujet tant que l'usage reste interne, bloquant dès
   le premier client.
