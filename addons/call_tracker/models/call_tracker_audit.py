# -*- coding: utf-8 -*-
import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class CallTrackerAudit(models.Model):
    _name = 'call.tracker.audit'
    _description = "Journal d'audit du Call Tracker"
    _order = 'create_date desc, id desc'
    _rec_name = 'phone_number'

    # ⚠️ Les LECTURES sont tracées autant que les écritures, et c'est le point
    # de ce journal. Une écriture laisse une trace visible — l'appel apparaît
    # dans la liste. Une lecture ne laisse rien : sans ce modèle, un jeton volé
    # pourrait interroger le carnet d'adresses numéro par numéro sans qu'aucune
    # trace n'en subsiste nulle part.
    action = fields.Selection(
        [
            ('log_call', "Journalisation d'appel"),
            ('contact_lookup', "Consultation de contact"),
            ('contact_search', "Recherche de contacts"),
            ('activity_list', "Appels à passer"),
            ('activity_done', "Clôture d'activité"),
        ],
        required=True,
        index=True,
    )
    result = fields.Selection(
        [
            ('ok', "Accepté"),
            ('duplicate', "Déjà reçu"),
            ('not_found', "Sans correspondance"),
            ('invalid', "Charge utile refusée"),
            ('too_short', "Refusé — fragment trop court"),
            ('unauthorized', "Refusé — jeton"),
        ],
        required=True,
        index=True,
    )

    # Vide en cas de refus : le jeton présenté ne désignait aucun appareil.
    # C'est précisément la ligne qu'on veut pouvoir compter.
    device_id = fields.Many2one('call.tracker.device', ondelete='set null', index=True)
    user_id = fields.Many2one('res.users', string="Commercial", ondelete='set null')

    phone_number = fields.Char(string="Numéro")
    ip_address = fields.Char(string="Adresse IP")
    detail = fields.Char()
    linked_record = fields.Char(string="Enregistrement lié")

    @api.model
    def tracer(self, action, result, appareil=None, numero=None,
               detail=None, linked_record=None, ip=None):
        """Écrit une ligne d'audit sans jamais faire échouer l'appel en cours.

        Un journal d'audit qui casse la fonctionnalité qu'il observe est pire
        que pas de journal : on le désactive au premier incident, et il n'y en
        a plus du tout. Toute erreur est donc avalée et signalée dans les logs
        du serveur.
        """
        try:
            return self.sudo().create({
                'action': action,
                'result': result,
                'device_id': appareil.id if appareil else False,
                'user_id': appareil.user_id.id if appareil else False,
                # Tronqué : un numéro fait vingt caractères, au-delà c'est une
                # tentative d'injection ou une erreur d'app, pas un numéro.
                'phone_number': (numero or '')[:32] or False,
                'ip_address': (ip or '')[:64] or False,
                'detail': (detail or '')[:200] or False,
                'linked_record': linked_record,
            })
        except Exception:
            _logger.exception("Call Tracker : ecriture du journal d'audit impossible")
            return self.browse()
