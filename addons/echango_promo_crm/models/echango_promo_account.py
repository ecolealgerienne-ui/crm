# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import AccessError

#: Les champs que **Promo possède**. Écrits par le contrôleur à chaque lot, et
#: par personne d'autre.
#:
#: ⚠️ **La frontière de propriété passe par le MODÈLE, pas par un verrou.** Le
#: verrou `write()` du module voisin teste `if not self.env.su` : `sudo()`
#: passe, délibérément, puisque c'est par là qu'écrit le contrôleur. Transposé
#: seul, il protégerait l'humain et jamais le lot. Ce qui tient la frontière
#: ici, c'est que ces champs vivent sur CE modèle et pas sur `res.partner` : le
#: commercial travaille à côté, sur la fiche client, sans jamais entrer en
#: collision.
CHAMPS_DE_PROMO = (
    'promo_uuid', 'nom_promo', 'adresse_promo', 'categorie', 'telephone_e164',
    'pays', 'latitude', 'longitude', 'origine', 'agent_createur_id',
    'date_creation', 'suspendu_le', 'supprime_le', 'consentement_le',
    'est_active', 'date_derniere_publication', 'promos_sans_publication',
    'promos_deja_publiees', 'promos_en_ligne', 'promos_visibles',
    'promos_publiees_30j', 'promos_masquees', 'signalements_90j',
    'nouveaux_visiteurs_fiche_30j', 'nouveaux_visiteurs_promos_30j',
    'plafond_effectif', 'plafond_propre', 'registre_statut', 'peut_publier',
    'motif_blocage', 'genere_le', 'derniere_synchro', 'source_id',
    'last_batch',
)

MOTIFS = [
    ('compte_supprime', "Compte supprimé"),
    ('compte_suspendu', "Compte suspendu"),
    ('registre_absent', "Registre jamais envoyé"),
    ('registre_en_attente', "Registre en attente de NOTRE validation"),
    ('registre_rejete', "Registre rejeté"),
    ('profil_en_revue', "Profil en attente de validation"),
    ('position_absente', "Position du commerce absente"),
    ('plafond_atteint', "Plafond de promos atteint"),
    ('quota_creation_24h', "Quota de créations sur 24 h atteint"),
]


class EchangoPromoAccount(models.Model):
    """Les faits qu'echango Promo envoie sur un commerçant.

    Un enregistrement par commerçant, rattaché à un `res.partner`. Le partenaire
    porte la relation commerciale (commercial, notes, activités, appels) ; ce
    modèle porte ce que le produit sait.
    """

    _name = 'echango.promo.account'
    _description = "echango Promo — suivi d'un commerçant"
    _order = 'date_derniere_publication desc nulls last'
    _rec_name = 'nom_promo'

    partner_id = fields.Many2one(
        'res.partner', string="Client", required=True, ondelete='cascade',
        index=True,
    )
    source_id = fields.Many2one('echango.promo.source', string="Source",
                                ondelete='set null')

    #: ⚠️ **La clé de rapprochement, et elle est immuable.** Jamais le
    #: téléphone : un numéro recyclé fusionnerait deux commerçants distincts —
    #: le produit a déjà payé ce défaut.
    promo_uuid = fields.Char(string="Identifiant Promo", required=True,
                             index=True, readonly=True)

    nom_promo = fields.Char(string="Nom (Promo)", readonly=True)
    adresse_promo = fields.Char(string="Adresse (Promo)", readonly=True)
    categorie = fields.Char(string="Catégorie", readonly=True)
    telephone_e164 = fields.Char(string="Téléphone", readonly=True)
    pays = fields.Char(string="Pays", readonly=True)
    latitude = fields.Float(string="Latitude", digits=(10, 6), readonly=True,
                            aggregator=False)
    longitude = fields.Float(string="Longitude", digits=(10, 6), readonly=True,
                             aggregator=False)

    origine = fields.Selection(
        [('auto_inscrit', "Auto-inscrit"), ('confirme_agent', "Confirmé par un agent")],
        string="Origine", readonly=True,
    )
    agent_createur_id = fields.Char(string="Agent créateur", readonly=True)
    date_creation = fields.Datetime(string="Créé le", readonly=True)
    suspendu_le = fields.Datetime(string="Suspendu le", readonly=True)
    supprime_le = fields.Datetime(string="Supprimé le", readonly=True)

    #: ⚠️ `null` pour TOUS les comptes créés par un agent, par conception du
    #: produit. Sur le pilote, c'est la majorité des fiches — et c'est le point
    #: qui rend l'extension de finalité visible plutôt que tue (loi 18-07).
    consentement_le = fields.Datetime(string="CGU acceptées le", readonly=True)

    est_active = fields.Boolean(string="A déjà publié", readonly=True)
    date_derniere_publication = fields.Datetime(
        string="Dernière publication", readonly=True, index=True)

    #: ⚠️ **Ce n'est PAS « les brouillons » de l'écran commerçant** : une promo
    #: renvoyée en brouillon par une suspension ou un avertissement garde son
    #: `publishedAt`. Le commerçant peut voir 3 brouillons et ce champ 0.
    promos_sans_publication = fields.Integer(string="Jamais publiées",
                                             readonly=True, aggregator='sum')
    promos_deja_publiees = fields.Integer(string="Déjà publiées",
                                          readonly=True, aggregator='sum')
    promos_en_ligne = fields.Integer(string="En ligne", readonly=True,
                                     aggregator='sum')
    promos_visibles = fields.Integer(string="Visibles du client",
                                     readonly=True, aggregator='sum')
    promos_publiees_30j = fields.Integer(string="Publiées (30 j)",
                                         readonly=True, aggregator='sum')
    promos_masquees = fields.Integer(string="Masquées", readonly=True,
                                     aggregator='sum')
    signalements_90j = fields.Integer(string="Signalements (90 j)",
                                      readonly=True, aggregator='sum')

    #: ⚠️ **Portée, pas trafic.** Une ligne de vue naît à la PREMIÈRE
    #: consultation d'un appareil et jamais ensuite : ce compteur mesure des
    #: appareils nouveaux. Un commerce très connu paraîtra en déclin. Et il est
    #: manipulable — l'en-tête `X-Device-Id` n'est jamais vérifié.
    nouveaux_visiteurs_fiche_30j = fields.Integer(
        string="Nouveaux visiteurs — fiche (30 j)", readonly=True,
        aggregator='sum')
    nouveaux_visiteurs_promos_30j = fields.Integer(
        string="Nouveaux visiteurs — promos (30 j)", readonly=True,
        aggregator='sum')

    #: ⚠️ **Deux champs, pas un.** `plafond_effectif` est ce que le serveur
    #: applique ; `plafond_propre` vaut `null` quand le commerçant suit le
    #: défaut. Les fondre en un seul rendrait une dérogation à 5 indiscernable
    #: du défaut à 5 — exactement l'information qu'on voulait voir.
    plafond_effectif = fields.Integer(string="Plafond appliqué", readonly=True,
                                      aggregator=False)
    plafond_propre = fields.Integer(string="Dérogation", readonly=True,
                                    aggregator=False)

    #: ⚠️ Trois états, trois responsables : `null` = il n'a rien envoyé,
    #: `en_attente` = NOUS n'avons pas traité, `rejete` = il doit renvoyer.
    registre_statut = fields.Selection(
        [('en_attente', "En attente"), ('valide', "Validé"), ('rejete', "Rejeté")],
        string="Registre", readonly=True,
    )

    peut_publier = fields.Boolean(string="Peut publier", readonly=True)
    motif_blocage = fields.Selection(MOTIFS, string="Motif de blocage",
                                     readonly=True)

    #: ⚠️ La fraîcheur est une donnée, pas une intention : sans elle, « ce
    #: commerçant n'a rien publié » et « le lot de cette nuit n'est pas arrivé »
    #: s'affichent pareil.
    genere_le = fields.Datetime(string="Instantané du", readonly=True)
    derniere_synchro = fields.Datetime(string="Reçu le", readonly=True)

    #: ⚠️ **C'est LUI que l'acquittement compare.** Une fiche dont le dernier
    #: lot n'est pas celui qu'on vient de clore n'a pas été envoyée : elle est
    #: candidate à l'archivage. Sans ce champ, « absent du lot » ne serait
    #: calculable qu'en comparant des dates, donc faux dès qu'un lot dure plus
    #: d'une minute.
    last_batch = fields.Char(string="Dernier lot", readonly=True, index=True)

    # ⚠️ **Pas de `_sql_constraints`** : Odoo 19 le refuse — « Model attribute
    # '_sql_constraints' is no longer supported, please define
    # models.Constraint on the model ». Les index uniques sont donc posés en
    # SQL dans `init()`, ce qui ne dépend d'aucune API déclarative — le module
    # voisin avait déjà fait ce choix pour la même raison.
    def init(self):
        """L'unicité en SQL, posée à la main.

        ⚠️ **Pas `_sql_constraints`** : son API déclarative a bougé entre
        versions récentes d'Odoo, et le module voisin a déjà choisi cette voie
        pour la même raison. Un index unique posé ici ne dépend d'aucune API.
        """
        self.env.cr.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS echango_promo_account_uuid_uniq
                ON echango_promo_account (promo_uuid)
        """)
        self.env.cr.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS echango_promo_account_partner_uniq
                ON echango_promo_account (partner_id)
        """)

    def write(self, valeurs):
        """Refuse toute écriture humaine sur les champs de Promo.

        ⚠️ **`readonly=True` ne protège rien** : c'est une consigne d'interface,
        contournable en RPC. Le module voisin l'a appris sur ses appels. Le
        verrou est donc ici — et il laisse passer `sudo()`, par lequel écrit le
        contrôleur. C'est assumé : ce verrou protège d'une modification
        manuelle, pas du lot (voir l'en-tête de `CHAMPS_DE_PROMO`).
        """
        if not self.env.su:
            interdits = sorted(set(valeurs) & set(CHAMPS_DE_PROMO))
            if interdits:
                raise AccessError(_(
                    "Ces champs viennent d'echango Promo et sont réécrits à "
                    "chaque synchronisation : %s. Les corriger ici serait sans "
                    "effet dès la nuit suivante.", ", ".join(interdits)))
        return super().write(valeurs)

    @api.model
    def motifs_a_debloquer(self):
        """Les motifs qu'une action de NOTRE côté peut lever.

        ⚠️ Utilisé par l'écran « À débloquer ». Les autres motifs (position
        absente, plafond) se lèvent chez le commerçant : les y mêler ferait
        appeler des gens à qui l'on n'a rien à demander.
        """
        return ['registre_en_attente', 'profil_en_revue']
