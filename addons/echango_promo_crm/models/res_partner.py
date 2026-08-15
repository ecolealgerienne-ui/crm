# -*- coding: utf-8 -*-
from odoo import _, fields, models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    echango_promo_account_ids = fields.One2many(
        'echango.promo.account', 'partner_id', string="Suivi echango Promo")

    #: ⚠️ **La provenance ne se lit PAS sur l'équipe de vente.** Une équipe est
    #: commerciale, donc mutable : le jour où un compte change de main, il
    #: sortirait du périmètre « Promo » alors qu'il en vient toujours. Et
    #: `res.partner` n'a de toute façon plus de `team_id` en Odoo 19 — vérifié
    #: sur les sources : `addons/sales_team/models/` ne contient plus de
    #: `res_partner.py`, et ni `crm` ni `sale` ne l'ajoutent.
    est_commercant_promo = fields.Boolean(
        string="Commerçant echango Promo",
        compute='_compute_est_commercant_promo',
        search='_search_est_commercant_promo',
        help="Vient d'echango Promo. C'est l'identifiant technique qui le dit, "
             "pas un champ que l'on peut changer.",
    )

    def _compute_est_commercant_promo(self):
        # `_read_group` plutôt qu'une boucle de `search_count` : une fiche
        # ouverte par un utilisateur sans accès au suivi ne doit ni coûter une
        # requête par ligne, ni lever une erreur d'accès qui rendrait la fiche
        # entière illisible.
        comptes = dict(self.env['echango.promo.account'].sudo()._read_group(
            [('partner_id', 'in', self.ids)],
            groupby=['partner_id'], aggregates=['__count'],
        )) if self.ids else {}
        for partenaire in self:
            partenaire.est_commercant_promo = bool(comptes.get(partenaire))

    def _search_est_commercant_promo(self, operator, value):
        avec = self.env['echango.promo.account'].sudo().search([]).partner_id
        positif = (operator == '=') == bool(value)
        return [('id', 'in' if positif else 'not in', avec.ids)]

    def action_voir_suivi_promo(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _("Suivi echango Promo — %s", self.display_name),
            'res_model': 'echango.promo.account',
            'view_mode': 'form',
            'res_id': self.echango_promo_account_ids[:1].id,
            'context': {'create': False},
        }
