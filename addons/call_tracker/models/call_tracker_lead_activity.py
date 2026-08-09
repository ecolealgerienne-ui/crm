# -*- coding: utf-8 -*-
from odoo import fields, models


class CallTrackerLeadActivity(models.Model):
    """Relance téléphonique des affaires : où en est le pipeline côté appels.

    Répond à deux questions distinctes, et il faut les garder distinctes :

    1. **« Quelles affaires stagnent faute de relance ? »** — actionnable, sans
       interprétation. C'est la raison d'être de cet écran.
    2. **« Les affaires appelées avancent-elles mieux ? »** — la comparaison
       appelé / jamais appelé. Lisible ici, mais voir l'avertissement plus bas.

    ⚠️ **Ce modèle ne mesure PAS un effet causal.** La comparaison entre
    affaires appelées et jamais appelées est un instantané, pas un suivi de
    cohorte : on ne sait pas si l'affaire a avancé *après* l'appel. Et le biais
    est massif dans un sens connu — un commercial appelle en priorité ce qui
    lui paraît prometteur. Les affaires appelées gagnent donc davantage même si
    l'appel n'y est pour rien.

    Un vrai taux de conversion demanderait de dater chaque changement d'étape
    et de le corréler à la date d'appel. `date_last_stage_update` ne donne que
    le dernier ; l'historique complet vit dans le fil de suivi. C'est un
    chantier à part, délibérément non entrepris — mieux vaut un chiffre absent
    qu'un chiffre qu'on croira causal.
    """

    _name = 'call.tracker.lead.activity'
    _description = "Relance téléphonique des affaires"
    _auto = False
    _rec_name = 'lead_id'
    _order = 'days_since_last_call desc nulls first'

    lead_id = fields.Many2one('crm.lead', string="Affaire", readonly=True)
    user_id = fields.Many2one('res.users', string="Commercial", readonly=True)
    team_id = fields.Many2one('crm.team', string="Équipe", readonly=True)
    stage_id = fields.Many2one('crm.stage', string="Étape", readonly=True)
    partner_id = fields.Many2one('res.partner', string="Contact", readonly=True)
    lead_type = fields.Selection(
        [('lead', "Piste"), ('opportunity', "Opportunité")],
        string="Nature", readonly=True,
    )
    expected_revenue = fields.Monetary(
        string="Revenu attendu", readonly=True, currency_field='currency_id',
    )
    currency_id = fields.Many2one('res.currency', readonly=True)

    last_call_date = fields.Datetime(string="Dernier appel", readonly=True)
    call_count = fields.Integer(string="Appels", readonly=True)
    never_called = fields.Boolean(string="Jamais appelée", readonly=True)
    days_since_last_call = fields.Integer(
        string="Jours depuis le dernier appel", readonly=True,
        help="Vide si l'affaire n'a jamais été appelée.",
    )
    is_won = fields.Boolean(string="Étape gagnée", readonly=True)

    def _search(self, *args, **kwargs):
        """Vide le cache de l'ORM avant d'interroger la vue.

        Même raison que pour `call.tracker.coverage` : l'ORM ne sait pas de
        quelles tables une vue SQL dépend, et une affaire créée puis consultée
        dans la même transaction resterait invisible.
        """
        self.env['crm.lead'].flush_model()
        self.env['call.tracker.log'].flush_model()
        return super()._search(*args, **kwargs)

    def init(self):
        self.env.cr.execute("DROP VIEW IF EXISTS call_tracker_lead_activity")
        self.env.cr.execute("""
            CREATE VIEW call_tracker_lead_activity AS
            SELECT
                affaire.id                        AS id,
                affaire.id                        AS lead_id,
                affaire.user_id                   AS user_id,
                affaire.team_id                   AS team_id,
                affaire.stage_id                  AS stage_id,
                affaire.partner_id                AS partner_id,
                affaire.type                      AS lead_type,
                affaire.expected_revenue          AS expected_revenue,
                -- ⚠️ Pas `affaire.company_currency` : c'est un champ related
                -- NON STOCKÉ, donc aucune colonne SQL. La vue échouerait à la
                -- création, à l'installation du module. La devise se prend sur
                -- la société.
                societe.currency_id               AS currency_id,
                COALESCE(etape.is_won, FALSE)     AS is_won,
                MAX(appel.started_at)             AS last_call_date,
                COUNT(appel.id)                   AS call_count,
                (MAX(appel.started_at) IS NULL)   AS never_called,
                CASE WHEN MAX(appel.started_at) IS NULL THEN NULL
                     ELSE (CURRENT_DATE - MAX(appel.started_at)::date)
                END                               AS days_since_last_call
            FROM crm_lead affaire
            LEFT JOIN crm_stage etape ON etape.id = affaire.stage_id
            LEFT JOIN res_company societe ON societe.id = affaire.company_id
            -- Les appels RATTACHÉS à l'affaire, pas ceux du contact : une
            -- affaire n'est relancée que par les appels qui la concernent.
            LEFT JOIN call_tracker_log appel ON appel.lead_id = affaire.id
            WHERE affaire.active
            GROUP BY affaire.id, etape.is_won, societe.currency_id
        """)
