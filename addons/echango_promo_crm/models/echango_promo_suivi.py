# -*- coding: utf-8 -*-
from odoo import fields, models


class EchangoPromoSuivi(models.Model):
    """Le suivi commercial : des FAITS dérivés, pas des états figés.

    ⚠️ **Une vue SQL, pas un modèle stocké.** Les jours écoulés depuis la
    dernière publication dépendent d'aujourd'hui : un champ calculé et stocké
    serait juste le jour de son écriture et faux le lendemain, sans que rien ne
    le dise. Une vue les recalcule à chaque lecture — même raisonnement que la
    Couverture du portefeuille du Call Tracker.

    ⚠️ **Les six états ne sont PAS une colonne.** Ils vivent dans les filtres de
    recherche, pour que changer un seuil (7 j, 21 j) ne demande pas de remonter
    le module. Une version antérieure de la spécification promettait les deux à
    la fois — des seuils réglables sans redéploiement ET un `CASE` dans la
    vue — ce qui ne peut pas être vrai en même temps.
    """

    _name = 'echango.promo.suivi'
    _description = "echango Promo — suivi des commerçants"
    _auto = False
    _rec_name = 'partner_id'
    _order = 'date_derniere_publication asc nulls first'

    partner_id = fields.Many2one('res.partner', string="Client", readonly=True)
    account_id = fields.Many2one('echango.promo.account', string="Fiche Promo",
                                 readonly=True)
    user_id = fields.Many2one('res.users', string="Commercial", readonly=True)
    city = fields.Char(string="Ville", readonly=True)
    wilaya = fields.Char(string="Wilaya", readonly=True)
    #: ⚠️ Affiché à côté de la ville : une ville vide ne dit pas POURQUOI elle
    #: l'est, et les trois raisons appellent trois gestes différents.
    geocodage_statut = fields.Selection(
        [('sans_position', "Sans position GPS"),
         ('a_faire', "À géocoder"),
         ('fait', "Géocodé"),
         ('sans_resultat', "Géocodé, sans résultat"),
         ('erreur', "Échec du géocodage")],
        string="Géocodage", readonly=True)

    date_derniere_publication = fields.Datetime(string="Dernière publication",
                                                readonly=True)
    #: ⚠️ **Vide, pas zéro, quand il n'a jamais publié.** Zéro signifierait
    #: « publié aujourd'hui », et un tri sur cette colonne placerait les
    #: commerçants les plus délaissés en tête des plus actifs. Le module voisin
    #: a posé exactement cette règle sur `days_since_last_call`.
    jours_depuis_publication = fields.Integer(
        string="Jours depuis la dernière publication", readonly=True,
        aggregator='avg')
    jamais_publie = fields.Boolean(string="N'a jamais publié", readonly=True)

    promos_en_ligne = fields.Integer(string="En ligne", readonly=True,
                                     aggregator='sum')
    promos_visibles = fields.Integer(string="Visibles", readonly=True,
                                     aggregator='sum')
    peut_publier = fields.Boolean(string="Peut publier", readonly=True)
    motif_blocage = fields.Char(string="Motif de blocage", readonly=True)
    signalements_90j = fields.Integer(string="Signalements (90 j)",
                                      readonly=True, aggregator='sum')
    nouveaux_visiteurs_promos_30j = fields.Integer(
        string="Nouveaux visiteurs (30 j)", readonly=True, aggregator='sum')
    derniere_synchro = fields.Datetime(string="Reçu le", readonly=True)

    def action_ouvrir_client(self):
        """Ouvre la **fiche client**, pas la ligne de suivi.

        ⚠️ **Un clic sur une ligne de liste ouvre le formulaire du modèle de la
        liste** — ici, une ligne de vue SQL, qui n'a rien à montrer de plus que
        la ligne elle-même. Ce que l'équipe veut atteindre, c'est le client :
        ses appels, ses notes, ses activités, son commercial. D'où cette action,
        posée en première colonne pour être à un seul clic.
        """
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'res.partner',
            'res_id': self.partner_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def get_formview_action(self, access_uid=None):
        """Tout lien vers une ligne de suivi mène au CLIENT.

        C'est le second chemin, celui qu'emprunte Odoo quand on clique un
        many2one pointant vers ce modèle : sans cette redirection, il ouvrirait
        un formulaire de vue SQL — techniquement valide, commercialement vide.
        """
        self.ensure_one()
        return self.partner_id.get_formview_action(access_uid=access_uid)

    def _search(self, *args, **kwargs):
        """Écrit en base ce qui est encore en cache avant d'interroger la vue.

        ⚠️ **Le piège des modèles `_auto = False`.** L'ORM vide son cache avant
        une requête sur les modèles qu'il connaît ; il n'a aucun moyen de savoir
        qu'une vue SQL lit `echango_promo_account` et `res_partner`. Sans ce
        vidage, une fiche créée puis consultée dans la même transaction reste
        invisible — défaut qui ne se voit qu'en test, où tout se passe dans une
        seule transaction.

        ⚠️ Et ce sont bien les modèles SOURCES qu'on vide, pas celui-ci : lui
        n'a rien à écrire, un `self.flush_model()` serait un correctif
        inopérant.
        """
        self.env['echango.promo.account'].flush_model()
        self.env['res.partner'].flush_model()
        return super()._search(*args, **kwargs)

    def init(self):
        self.env.cr.execute("DROP VIEW IF EXISTS echango_promo_suivi")
        self.env.cr.execute("""
            CREATE VIEW echango_promo_suivi AS
            SELECT c.id                              AS id,
                   c.id                              AS account_id,
                   c.partner_id                      AS partner_id,
                   p.user_id                         AS user_id,
                   COALESCE(c.ville_geocodee, p.city) AS city,
                   c.wilaya_geocodee                  AS wilaya,
                   c.geocodage_statut                 AS geocodage_statut,
                   c.date_derniere_publication       AS date_derniere_publication,
                   (c.date_derniere_publication IS NULL) AS jamais_publie,
                   CASE WHEN c.date_derniere_publication IS NULL THEN NULL
                        ELSE (CURRENT_DATE - c.date_derniere_publication::date)
                   END                               AS jours_depuis_publication,
                   c.promos_en_ligne                 AS promos_en_ligne,
                   c.promos_visibles                 AS promos_visibles,
                   c.peut_publier                    AS peut_publier,
                   c.motif_blocage                   AS motif_blocage,
                   c.signalements_90j                AS signalements_90j,
                   c.nouveaux_visiteurs_promos_30j   AS nouveaux_visiteurs_promos_30j,
                   c.derniere_synchro                AS derniere_synchro
              FROM echango_promo_account c
              JOIN res_partner p ON p.id = c.partner_id
             WHERE p.active
               AND c.supprime_le IS NULL
        """)
