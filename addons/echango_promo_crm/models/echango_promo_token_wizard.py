# -*- coding: utf-8 -*-
from odoo import fields, models


class EchangoPromoTokenWizard(models.TransientModel):
    """Montre le jeton en clair, **une seule fois**.

    ⚠️ **`_transient_max_hours` très court, et ce n'est pas une coquetterie** :
    un modèle transitoire est une **vraie ligne en base**, donc une ligne qui
    part dans les sauvegardes. Six minutes suffisent à copier un jeton.
    """

    _name = 'echango.promo.token.wizard'
    _description = "echango Promo — jeton généré"
    _transient_max_hours = 0.1

    source_id = fields.Many2one('echango.promo.source', readonly=True)
    token = fields.Char(string="Jeton", readonly=True)
