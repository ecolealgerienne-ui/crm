# -*- coding: utf-8 -*-
from odoo import fields, models


class CallTrackerCoverage(models.Model):
    """Couverture du portefeuille : qui a été appelé, et qui ne l'a pas été.

    L'indicateur le plus révélateur pour un manager — un commercial peut
    passer beaucoup d'appels et toujours aux cinq mêmes clients. Le volume
    d'appels ne le dit pas ; celui-ci, si.

    **Une vue SQL, pas un modèle ordinaire.** Le dénominateur — le portefeuille
    assigné — n'est pas dans `call.tracker.log` : il vit sur `res.partner`. Un
    champ calculé ne permettrait ni de filtrer ni de regrouper dessus, et un
    modèle stocké devrait être tenu à jour à chaque affectation de client. Une
    vue reflète l'état réel à chaque lecture, sans rien à synchroniser.

    Une ligne par **compte assigné**, pas par contact : un appel passé à
    l'interlocuteur d'une société compte pour la société. Compter au niveau du
    contact ferait apparaître comme « jamais appelée » une entreprise qu'on
    appelle toutes les semaines.
    """

    _name = 'call.tracker.coverage'
    _description = "Couverture du portefeuille"
    _auto = False
    _rec_name = 'partner_id'
    _order = 'last_call_date asc nulls first'

    partner_id = fields.Many2one('res.partner', string="Compte", readonly=True)
    user_id = fields.Many2one('res.users', string="Commercial", readonly=True)
    last_call_date = fields.Datetime(string="Dernier appel", readonly=True)
    call_count = fields.Integer(string="Appels", readonly=True)
    days_since_last_call = fields.Integer(
        string="Jours depuis le dernier appel", readonly=True,
        help="Vide si le compte n'a jamais été appelé.",
    )
    never_called = fields.Boolean(string="Jamais appelé", readonly=True)

    def _search(self, *args, **kwargs):
        """Écrit en base ce qui est encore en cache avant d'interroger la vue.

        ⚠️ Le piège des modèles ``_auto = False``. L'ORM vide son cache avant
        une requête **sur les modèles qu'il connaît** ; il n'a aucun moyen de
        savoir qu'une vue SQL lit `res_partner` et `call_tracker_log`. Sans ce
        vidage, un client créé puis consulté dans la même transaction reste
        invisible : la vue interroge la base, où il n'est pas encore écrit.

        Le défaut ne se voit pas en usage courant — l'écran est ouvert bien
        après — mais il rend le modèle faux dès qu'une écriture précède une
        lecture. Constaté d'abord par les tests, où tout se passe dans une
        seule transaction.
        """
        self.env['res.partner'].flush_model()
        self.env['call.tracker.log'].flush_model()
        return super()._search(*args, **kwargs)

    def init(self):
        self.env.cr.execute("DROP VIEW IF EXISTS call_tracker_coverage")
        self.env.cr.execute("""
            CREATE VIEW call_tracker_coverage AS
            SELECT
                compte.id                          AS id,
                compte.id                          AS partner_id,
                compte.user_id                     AS user_id,
                MAX(appel.started_at)              AS last_call_date,
                COUNT(appel.id)                    AS call_count,
                (MAX(appel.started_at) IS NULL)    AS never_called,
                -- NULL plutôt que 0 quand il n'y a jamais eu d'appel : zéro
                -- jour signifierait « appelé aujourd'hui », l'exact inverse.
                CASE WHEN MAX(appel.started_at) IS NULL THEN NULL
                     ELSE (CURRENT_DATE - MAX(appel.started_at)::date)
                END                                AS days_since_last_call
            FROM res_partner compte
            -- Les contacts rattachés au compte, le compte lui-même inclus :
            -- c'est ce qui fait remonter au niveau de la société un appel
            -- passé à son interlocuteur.
            LEFT JOIN res_partner rattache
                   ON rattache.commercial_partner_id = compte.id
            LEFT JOIN call_tracker_log appel
                   ON appel.partner_id = rattache.id
            WHERE compte.user_id IS NOT NULL
              AND compte.active
              -- Un seul niveau : les comptes, pas leurs contacts. Sans cela
              -- chaque interlocuteur compterait comme une ligne de
              -- portefeuille et diluerait le taux.
              AND compte.id = compte.commercial_partner_id
            GROUP BY compte.id, compte.user_id
        """)
