# -*- coding: utf-8 -*-
import logging
import os
from datetime import timedelta

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class EchangoPromoAudit(models.Model):
    """Ce que le contrôleur a reçu, **accepté comme refusé**.

    ⚠️ **Un refus qui ne laisse pas de trace est invisible en production.** Le
    banc peut prouver qu'un lot malformé est rejeté ; sans ce journal, personne
    ne peut constater qu'un rejet a eu lieu la nuit dernière — et un export
    silencieusement refusé ressemble trait pour trait à un export qui n'est
    jamais parti.
    """

    _name = 'echango.promo.audit'
    _description = "echango Promo — journal des lots"
    _order = 'create_date desc'

    source_id = fields.Many2one('echango.promo.source', string="Source",
                                readonly=True, ondelete='set null')
    batch = fields.Char(string="Lot", readonly=True, index=True)
    route = fields.Char(string="Route", readonly=True)
    accepte = fields.Boolean(string="Accepté", readonly=True)
    detail = fields.Char(string="Détail", readonly=True)
    fiches = fields.Integer(string="Fiches", readonly=True, aggregator='sum')
    refusees = fields.Integer(string="Refusées", readonly=True, aggregator='sum')
    ip = fields.Char(string="Adresse IP", readonly=True)

    @api.model
    def _purger(self):
        """Purge le journal au-delà de la rétention.

        ⚠️ **Repli sur « aucune purge », journalisé.** Une variable absente ou
        illisible ne doit pas faire disparaître des données — et l'absence de
        purge doit rester discernable d'une purge qui n'a rien trouvé. Même
        doctrine que `CALL_TRACKER_RETENTION_DAYS` chez le voisin.
        """
        brut = os.environ.get('ECHANGO_PROMO_RETENTION_DAYS', '')
        try:
            jours = int(brut)
        except (TypeError, ValueError):
            jours = 0
        if jours <= 0:
            _logger.info(
                "echango_promo_crm : aucune retention configuree "
                "(ECHANGO_PROMO_RETENTION_DAYS=%r) — rien a purger", brut)
            return 0
        limite = fields.Datetime.now() - timedelta(days=jours)
        vieux = self.sudo().search([('create_date', '<', limite)])
        nombre = len(vieux)
        vieux.unlink()
        _logger.info("echango_promo_crm : %d ligne(s) de journal purgee(s) "
                     "au-dela de %d jours", nombre, jours)
        return nombre

    @classmethod
    def tracer(cls, env, **valeurs):
        """Écrit une ligne d'audit **sans jamais faire échouer l'appel**.

        ⚠️ Un journal qui casse la requête qu'il observe transforme un incident
        de traçabilité en panne de service. On journalise l'échec du
        journal — c'est tout ce qu'on peut faire d'honnête.
        """
        try:
            env['echango.promo.audit'].sudo().create(valeurs)
        except Exception as erreur:  # noqa: BLE001 — voir la docstring
            _logger.warning("echango_promo_crm : audit non écrit (%s)", erreur)
