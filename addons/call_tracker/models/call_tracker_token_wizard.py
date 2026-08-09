# -*- coding: utf-8 -*-
from odoo import fields, models


class CallTrackerTokenWizard(models.TransientModel):
    _name = 'call.tracker.token.wizard'
    _description = "Affichage unique du jeton d'un appareil"

    # Six minutes au lieu de l'heure par défaut des modèles transitoires.
    # Un enregistrement transitoire est une VRAIE ligne en base jusqu'à ce que
    # le ramasse-miettes d'Odoo la retire : ce champ porte un secret en clair,
    # et la fenêtre pendant laquelle il traîne dans les sauvegardes et les
    # journaux de réplication n'a aucune raison de durer une heure. Le temps
    # de copier un jeton se compte en secondes.
    _transient_max_hours = 0.1

    device_id = fields.Many2one('call.tracker.device', readonly=True)
    # Le jeton en clair n'existe QUE dans cet enregistrement transitoire, que
    # le garbage collector d'Odoo purge. L'appareil, lui, ne garde que
    # l'empreinte : une fois cette fenêtre fermée, plus personne — pas même un
    # administrateur — ne peut relire le jeton. En cas de perte, on en génère
    # un nouveau, ce qui révoque l'ancien.
    token_clear = fields.Char(string="Jeton", readonly=True)
