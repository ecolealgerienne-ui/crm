# -*- coding: utf-8 -*-
from odoo import _, fields, models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    call_tracker_count = fields.Integer(
        string="Appels",
        compute='_compute_call_tracker_count',
    )

    def _compute_call_tracker_count(self):
        """Compte les appels du contact ET de ses contacts rattachés.

        `child_of` et non une égalité : sur une société, les appels sont
        souvent journalisés au nom de l'interlocuteur — un contact enfant. Un
        compteur qui n'additionnerait que les appels de la société elle-même
        afficherait zéro sur les fiches où il y a le plus à voir.
        """
        # ⚠️ Un utilisateur sans accès aux appels — comptable, magasinier —
        # ouvre lui aussi des fiches contact. Sans cette vérification, le
        # `_read_group` ci-dessous lèverait une erreur d'accès et la FICHE
        # ENTIÈRE deviendrait illisible pour lui, à cause d'un bouton qui ne
        # le concerne pas.
        if not self.env['call.tracker.log'].has_access('read'):
            self.call_tracker_count = 0
            return

        comptes = dict(self.env['call.tracker.log']._read_group(
            [('partner_id', 'child_of', self.ids)],
            groupby=['partner_id'],
            aggregates=['__count'],
        )) if self.ids else {}

        for contact in self:
            if comptes:
                # Le regroupement rend le contact exact de chaque appel ; il
                # faut donc réagréger sur la descendance de chaque fiche.
                descendance = self.search([('id', 'child_of', contact.id)])
                contact.call_tracker_count = sum(
                    n for p, n in comptes.items() if p in descendance
                )
            else:
                contact.call_tracker_count = 0

    def action_voir_appels(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _("Appels — %s", self.display_name),
            'res_model': 'call.tracker.log',
            'view_mode': 'list,form',
            'domain': [('partner_id', 'child_of', self.id)],
            'context': {'create': False},
        }
