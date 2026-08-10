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

    call_note_count = fields.Integer(
        # « Notes » tout court entre en collision avec le champ natif
        # `comment` de res.partner, qui porte la même étiquette — Odoo le
        # signale au chargement, et deux colonnes homonymes dans un sélecteur
        # de champs ne se distinguent pas.
        string="Notes du suivi",
        compute='_compute_call_note_count',
    )

    def _domaine_notes(self):
        """Toutes les notes internes du COMPTE : la société, ses contacts, ses pistes.

        **Pourquoi ce périmètre.** Une note vit dans le fil de la piste quand
        l'appel en avait une, sinon dans celui du contact — la piste l'emporte.
        Sur des données réelles, sept notes sur huit se retrouvaient donc sur
        des pistes, et la fiche du client n'en montrait qu'une. L'historique
        est éclaté par construction, et il l'est de plus en plus à mesure
        qu'un client accumule des affaires.

        Le compte, et non le contact seul : les appels sont journalisés au nom
        de l'interlocuteur qu'on a eu au téléphone. Ouvrir « Acme Corporation »
        doit montrer ce qui s'est dit avec Floyd comme avec ses collègues,
        sinon il faut ouvrir cinq fiches pour reconstituer une conversation.

        **Interroge `mail.message`, pas une vue SQL.** Les messages portent des
        règles d'accès fines dans Odoo ; une vue les contournerait et rendrait
        visibles des notes de pistes qu'on n'a pas le droit de voir. Passer
        par le modèle laisse Odoo faire ce filtrage, gratuitement et
        correctement.
        """
        self.ensure_one()
        contacts = self.search([('id', 'child_of', self.commercial_partner_id.id)])
        pistes = self.env['crm.lead'].search([('partner_id', 'in', contacts.ids)])
        return [
            # `mt_note` = note INTERNE. Écarte au passage tout le bruit
            # automatique d'Odoo — « Opportunity Created », « Stage Changed » —
            # qui porte ses propres sous-types.
            ('subtype_id', '=', self.env.ref('mail.mt_note').id),
            # `comment` = une note écrite par un humain, `notification` = la
            # trace d'un appel muet. Écarte `user_notification`, qui est une
            # mécanique interne d'Odoo et n'a rien à dire du client.
            ('message_type', 'in', ['comment', 'notification']),
            # Odoo écrit des messages de SUIVI au corps vide, qui ne portent
            # qu'un changement de champ. Ils comptent dans le compteur et
            # occupent une ligne pour ne rien dire.
            ('body', '!=', ''),
            '|',
            '&', ('model', '=', 'res.partner'), ('res_id', 'in', contacts.ids),
            '&', ('model', '=', 'crm.lead'), ('res_id', 'in', pistes.ids),
        ]

    def _compute_call_note_count(self):
        Message = self.env['mail.message']
        for contact in self:
            # `search_count` et non un `_read_group` : le domaine dépend du
            # compte de chaque fiche et ne se factorise pas. Une fiche à la
            # fois, sur un écran qui en affiche une.
            contact.call_note_count = (
                Message.search_count(contact._domaine_notes()) if contact.id else 0
            )

    def action_voir_notes(self):
        """Toutes les notes du compte, du plus récent au plus ancien."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _("Notes — %s", self.commercial_partner_id.display_name),
            'res_model': 'mail.message',
            'view_mode': 'list',
            'views': [(self.env.ref('call_tracker.view_call_tracker_notes_list').id, 'list')],
            'domain': self._domaine_notes(),
            'context': {'create': False, 'edit': False},
        }

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
