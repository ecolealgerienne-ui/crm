# -*- coding: utf-8 -*-
from odoo import _, fields, models


class CrmLead(models.Model):
    _inherit = 'crm.lead'

    call_tracker_count = fields.Integer(
        string="Appels",
        compute='_compute_call_tracker_count',
    )

    def _compute_call_tracker_count(self):
        # ⚠️ Un utilisateur sans accès aux appels — comptable, magasinier —
        # ouvre lui aussi des fiches contact. Sans cette vérification, le
        # `_read_group` ci-dessous lèverait une erreur d'accès et la FICHE
        # ENTIÈRE deviendrait illisible pour lui, à cause d'un bouton qui ne
        # le concerne pas.
        if not self.env['call.tracker.log'].has_access('read'):
            self.call_tracker_count = 0
            return

        comptes = dict(self.env['call.tracker.log']._read_group(
            [('lead_id', 'in', self.ids)],
            groupby=['lead_id'],
            aggregates=['__count'],
        )) if self.ids else {}
        for piste in self:
            piste.call_tracker_count = comptes.get(piste, 0)

    def action_voir_appels(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _("Appels — %s", self.display_name),
            'res_model': 'call.tracker.log',
            'view_mode': 'list,form',
            'domain': [('lead_id', '=', self.id)],
            'context': {'create': False},
        }
