# Indicateurs et reporting du Call Tracker

Ce que le manager peut mesurer, ce qui est en place, ce qui est volontairement
repoussé, et pourquoi. Décidé le 2026-08-09.

---

## 1. Deux faits vérifiés qui cadrent tout le reste

### Nous sommes en Odoo Community

```
spreadsheet              présent, installable
spreadsheet_dashboard    présent, installable
spreadsheet_edition      ABSENT      ← Enterprise
documents_spreadsheet    ABSENT      ← Enterprise
web_enterprise           ABSENT      → édition Community
```

**Le manager ne peut pas construire un tableau de bord Spreadsheet par
glisser-déposer.** Le moteur d'affichage est disponible, l'éditeur non.

Conséquence : le reporting passe par les **vues pivot et graphe natives**, qui
sont dans le cœur d'Odoo et suffisent largement. Un tableau de bord Spreadsheet
livré en JSON dans l'addon serait *consultable* en Community, mais il faudrait
une instance Enterprise pour le produire, ou l'écrire à la main. Écarté.

### Le croisement avec le CRM est possible

`res.partner.user_id` est stocké, `crm.lead.date_last_stage_update` et
`date_conversion` existent. Le taux de couverture et le lien avec le pipeline
sont donc calculables — ce qui n'était pas acquis. La couverture est faite
(§5), la relance des affaires aussi (§6) — mais sans taux de conversion, et
c'est délibéré.

---

## 2. Le préalable : mesurer le retard avant de comparer les personnes

**Tout indicateur comparatif suppose que la capture est complète et comparable
d'un téléphone à l'autre.** Ce n'est pas vérifié.

### Ce qui se passe réellement quand un téléphone suspend l'application

Le mode de défaillance connu est la mise en veille agressive par les surcouches
constructeur (Samsung, Xiaomi). Il faut être précis sur son effet, parce que
l'intuition est fausse :

- le receveur `PHONE_STATE` n'est plus délivré, les tâches WorkManager sont
  annulées : **rien ne remonte** ;
- mais le journal d'appels du système, lui, continue d'être écrit ;
- et le balayage repart du curseur `lastScanMillis`, qui n'avance que sur ce
  qui a été lu.

Donc **au prochain réveil de l'application, tout est rattrapé**. Le risque
n'est pas la perte, c'est le **retard** — sauf dans un seul cas : un téléphone
dont l'application n'est plus jamais réveillée.

C'est une nuance qui change la conclusion : un chiffre mensuel restera juste,
un chiffre **journalier** et une **alerte de seuil** ne le seront pas.

### Comment on le mesure, sans instrumenter quoi que ce soit

`started_at` porte l'heure de l'appel, `create_date` l'heure d'arrivée dans
Odoo. Leur écart est le **délai de remise**, et il est déjà en base. Rapporté
par appareil, il dit immédiatement quel téléphone décroche du reste.

Rien de nouveau à collecter ; c'est le point à regarder en premier, avant tout
classement.

---

## 3. Lot 1 — ce qui est fait

| | |
|---|---|
| Cloisonnement | Deux groupes, `Call Tracker / Utilisateur` et `Call Tracker / Responsable`, avec des règles d'enregistrement : chacun ses appels, le responsable voit tout |
| `outcome` | Répondu / sans réponse, dérivé de la durée |
| `hour_of_day` | Heure locale de l'appel, pour la répartition horaire |
| `delivery_lag_minutes` | Délai de remise, la mesure du §2 |
| Filtres | Aujourd'hui, cette semaine, mes appels, remise tardive |

### Pourquoi un champ `outcome` et pas seulement la direction

Un appel sortant qui sonne dans le vide est journalisé par Android en
`outbound` avec une durée nulle — **pas** en `missed`, qui ne concerne que les
entrants. Sans champ dérivé, le taux de décroché est donc faux pour toute
l'activité sortante.

Une **sélection** plutôt qu'un booléen : dans un tableau croisé, des colonnes
`Vrai` / `Faux` ne se lisent pas.

### Pourquoi `hour_of_day` mais pas `week_number`

Odoo groupe déjà nativement un champ date par jour, semaine, mois ou trimestre,
**et il le fait dans le fuseau de l'utilisateur**. Un `week_number` stocké
serait calculé en UTC : un appel du dimanche 23 h 30 à Alger tomberait dans la
mauvaise semaine, et on aurait deux façons de compter la même chose qui ne
concordent pas. On ne le fait pas.

`hour_of_day` en revanche est nécessaire, pour une raison différente : le
groupement natif par heure produit « 9 août 14 h », pas « 14 h toutes dates
confondues ». La répartition horaire demande donc bien un champ.

⚠️ **Il est calculé dans le fuseau du commercial** (`res.users.tz`), à défaut
celui de la session, à défaut UTC. C'est l'heure vécue par celui qui passe
l'appel qui a un sens ici. Le champ est figé à la création : un commercial qui
change de fuseau ne réécrit pas son historique.

---

## 4. Ce qui est repoussé, et ce que ça coûte vraiment

### Le classement nominatif et l'alerte de seuil

**Pas avant d'avoir mesuré le délai de remise sur les modèles réellement
déployés.** Si un téléphone remonte ses appels avec six heures de retard :

- le classement compare des réglages de batterie, pas des commerciaux ;
- l'alerte « moins de 15 appels aujourd'hui » se déclenche sur celui dont le
  téléphone a suspendu l'application ;
- et la première réunion où quelqu'un répond « mon téléphone n'avait pas
  encore tout envoyé » abîme durablement la confiance dans l'outil.

Un point pratique en plus, pour le jour où on l'active : une alerte
quotidienne à heure fixe sonnera les congés, les arrêts maladie et les jours
fériés. Une alerte qui a tort une fois sur cinq est désactivée en quinze jours.

Les indicateurs **agrégés** et **personnels** ne posent aucun de ces problèmes
et sont disponibles dès maintenant. C'est la comparaison **entre personnes**
qui attend.

---

## 5. La couverture du portefeuille — fait

*CRM > Call Tracker > Couverture du portefeuille.* Une ligne par compte
assigné, avec la date du dernier appel, l'ancienneté en jours, et le nombre
d'appels.

C'est **le seul écran qui montre ce qui ne s'est pas passé**. Un client jamais
appelé n'apparaît dans aucune liste d'appels ; il n'existe que par différence
avec le portefeuille.

Trois choix de conception :

- **Une vue SQL, pas un modèle stocké.** Le dénominateur vit sur
  `res.partner` ; un modèle stocké devrait être réécrit à chaque affectation
  de client et se désynchroniserait au premier oubli.
- **Une ligne par compte, pas par contact.** Une société à cinq
  interlocuteurs pèserait sinon cinq fois dans le dénominateur.
- **Un appel à l'interlocuteur couvre sa société.** Les appels sont
  journalisés au nom de la personne qu'on a eue au téléphone ; compter au
  niveau du contact ferait apparaître comme « jamais appelée » une entreprise
  qu'on appelle chaque semaine.

`days_since_last_call` est **vide** — pas zéro — quand il n'y a jamais eu
d'appel : zéro signifierait « appelé aujourd'hui », et un tri sur cette
colonne placerait les comptes délaissés en tête des mieux suivis.

⚠️ **Le portefeuille, c'est le champ « Commercial » de la fiche client.** S'il
n'est renseigné nulle part, l'écran est vide et il n'y a pas de couverture à
mesurer. C'est le préalable, et il est humain, pas technique.

---

## 6. La relance des affaires — fait, et ce qu'elle ne dit pas

*CRM > Call Tracker > Relance des affaires.* Chaque affaire ouverte, avec la
date du dernier appel qui lui est rattaché, les plus délaissées en tête.

La demande initiale portait sur un **taux de conversion** : « pistes appelées
passées à l'étape suivante, contre pistes jamais appelées ». Il est livré
autrement, et volontairement.

### Ce qui est livré

Le croisement **étape × jamais appelée**, dans le tableau croisé. C'est ce qui
répond à la vraie question du manager — *où le pipeline stagne-t-il faute de
relance ?* — et c'est actionnable sans interprétation : la liste des affaires
à rappeler.

Seuls comptent les appels **rattachés à l'affaire**, pas ceux de son contact :
sinon une entreprise à plusieurs dossiers verrait tous ses dossiers marqués
relancés par un seul appel.

### Ce qui n'est pas livré, et pourquoi

**Aucun champ nommé « taux de conversion ».** Ce croisement est un instantané,
pas un suivi de cohorte : on ne sait pas si l'affaire a avancé *après* l'appel.
Et le biais va dans un sens connu — un commercial appelle en priorité ce qui
lui paraît prometteur, donc les affaires appelées gagnent davantage même si
l'appel n'y est pour rien.

Publier ce rapport sous le nom « taux de conversion » ferait conclure que
téléphoner fait gagner des affaires. C'est peut-être vrai ; ce chiffre-là ne le
démontre pas.

Le calcul honnête demande de dater **chaque** changement d'étape et de le
corréler à la date d'appel. `date_last_stage_update` ne donne que le dernier ;
l'historique vit dans le fil de suivi. Un test vérifie qu'aucun champ de ce
nom n'apparaît sur le modèle — c'est un garde-fou délibéré, pas un oubli.

---

## 7. Ordre proposé

1. ✅ **Lot 1** — cloisonnement, champs dérivés, filtres, mesure du retard.
2. ✅ **Couverture du portefeuille.**
3. **Mesurer** le délai de remise réel sur les téléphones du terrain, quelques
   semaines.
4. Selon le résultat : classement et alerte de seuil, calibrée sur jours
   ouvrés.
5. ✅ **Relance des affaires** — le croisement étape × relance. Le taux de
   conversion causal reste hors périmètre, voir §6.
