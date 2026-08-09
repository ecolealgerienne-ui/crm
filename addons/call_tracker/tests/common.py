# -*- coding: utf-8 -*-
import json

from odoo.addons.call_tracker.models.call_tracker_device import hacher_jeton

CHEMIN = '/call_tracker/log_call'


class ChargeUtile:
    """Fabrique de charges utiles valides, qu'un test rend ensuite invalides.

    Écrire chaque corps de requête à la main rendrait les tests de validation
    illisibles : on ne verrait plus ce qui est censé être fautif au milieu des
    quatre champs corrects qui l'entourent.
    """

    BASE = {
        'client_event_id': 'evt-test-1',
        'phone_number': '+213555000000',
        'direction': 'outbound',
        'duration_seconds': 42,
        'started_at': '2026-08-09T14:32:00Z',
    }

    @classmethod
    def valide(cls, **remplacements):
        return {**cls.BASE, **remplacements}

    @classmethod
    def sans(cls, *champs):
        return {c: v for c, v in cls.BASE.items() if c not in champs}


class BancCallTracker:
    """Outils partagés par les cas de test HTTP."""

    JETON = 'jeton-de-test-aaaaaaaaaaaaaaaaaaaaaaaaaaaa'

    def creer_appareil(self, jeton=None, actif=True):
        appareil = self.env['call.tracker.device'].create({
            'name': 'Appareil de test',
            'user_id': self.env.ref('base.user_admin').id,
            'active': actif,
        })
        appareil.sudo().write({'token_hash': hacher_jeton(jeton or self.JETON)})
        return appareil

    def poster(self, charge, jeton=JETON, brut=None):
        entetes = {'Content-Type': 'application/json'}
        if jeton is not None:
            entetes['Authorization'] = f'Bearer {jeton}'
        corps = brut if brut is not None else json.dumps(charge)
        return self.url_open(CHEMIN, data=corps, headers=entetes)
