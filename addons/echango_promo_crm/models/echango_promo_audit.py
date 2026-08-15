# -*- coding: utf-8 -*-
import logging
import os
from datetime import timedelta

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class EchangoPromoAudit(models.Model):
    """Ce que le contrôleur a reçu, **accepté comme refusé**.

    ── À quoi ce journal sert, exactement ──────────────────────────────────

    À répondre à une seule question, celle qu'on se pose quand un chiffre
    paraît faux : **« qu'est-ce qui est arrivé cette nuit, et qu'est-ce qui a
    été refusé ? »**

    ⚠️ **Un refus qui ne laisse pas de trace est invisible en production.** Un
    banc peut prouver qu'un lot malformé est rejeté ; sans ce journal, personne
    ne peut constater qu'un rejet a eu lieu la nuit dernière — et un export
    silencieusement refusé ressemble trait pour trait à un export qui n'est
    jamais parti. C'est le pendant de la source « silencieuse » : celle-ci dit
    que rien n'arrive, celui-là dit ce qui est arrivé.

    ── ⚠️ Une ligne par LOT, pas par page ──────────────────────────────────

    Une ligne par page rendait le journal illisible à mesure que le parc
    grandit : 280 commerçants font 3 pages, mais 10 000 en font 50 — soit 51
    lignes par nuit, près de 19 000 par an, pour une information qu'on consulte
    rarement et qui tient en une ligne.

    Les pages d'un même lot sont donc **cumulées** sur une seule ligne. Ce qui
    garde sa ligne propre, ce sont les **refus** : un lot rejeté pour jeton
    invalide ou charge malformée porte son message, et c'est précisément ce
    qu'on vient chercher.
    """

    _name = 'echango.promo.audit'
    _description = "echango Promo — journal des lots"
    _order = 'create_date desc'

    source_id = fields.Many2one('echango.promo.source', string="Source",
                                readonly=True, ondelete='set null')
    batch = fields.Char(string="Lot", readonly=True, index=True)
    pages = fields.Integer(string="Pages", readonly=True, aggregator='sum')
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

    @classmethod
    def cumuler(cls, env, batch, route, fiches, refusees, detail, **valeurs):
        """Cumule une page dans la ligne du lot, ou la crée.

        ⚠️ **`accepte` ne se recalcule pas à la hausse.** Une page refusée dans
        un lot par ailleurs sain doit laisser le lot marqué comme non
        entièrement accepté : remonter le drapeau à la page suivante effacerait
        la seule trace du problème.
        """
        try:
            Audit = env['echango.promo.audit'].sudo()
            ligne = Audit.search([('batch', '=', batch), ('route', '=', route)],
                                 limit=1)
            if not ligne:
                return Audit.create(dict(
                    valeurs, batch=batch, route=route, fiches=fiches,
                    refusees=refusees, detail=detail,
                    accepte=refusees == 0))
            details = [d for d in (ligne.detail, detail)
                       if d and d not in ('ok', '')]
            return ligne.write({
                # Le compteur de pages se cumule comme le reste : sans ça il
                # resterait à 1 et le journal annoncerait un lot d'une page là
                # où il y en a eu cinquante.
                'pages': ligne.pages + valeurs.get('pages', 1),
                'fiches': ligne.fiches + fiches,
                'refusees': ligne.refusees + refusees,
                'accepte': ligne.accepte and refusees == 0,
                'detail': ('; '.join(details) or 'ok')[:300],
            })
        except Exception as erreur:  # noqa: BLE001 — même raison que `tracer`
            _logger.warning("echango_promo_crm : audit non cumulé (%s)", erreur)
