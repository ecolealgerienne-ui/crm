# -*- coding: utf-8 -*-
from odoo.tests import HttpCase, tagged

from .common import BancCallTracker, ChargeUtile


@tagged('post_install', '-at_install')
class TestAudit(HttpCase, BancCallTracker):
    """Journal d'audit : écritures ET lectures (spec §7)."""

    def setUp(self):
        super().setUp()
        self.appareil = self.creer_appareil()
        self.Trace = self.env['call.tracker.audit']
        self.Trace.search([]).unlink()
        self.env['res.partner'].create({
            'name': 'Contact audité', 'phone': '+213555700001',
        })

    def dernier(self):
        return self.Trace.search([], order='id desc', limit=1)

    # ── Écritures ────────────────────────────────────────────────────────────

    def test_journalisation_tracee(self):
        self.poster(ChargeUtile.valide(client_event_id='evt-audit-1'))
        trace = self.dernier()
        self.assertEqual(trace.action, 'log_call')
        self.assertEqual(trace.result, 'ok')
        self.assertEqual(trace.device_id, self.appareil)
        self.assertEqual(trace.user_id, self.appareil.user_id)
        self.assertTrue(trace.ip_address)

    def test_rejeu_trace_comme_tel(self):
        charge = ChargeUtile.valide(client_event_id='evt-audit-rejeu')
        self.poster(charge)
        self.poster(charge)
        self.assertEqual(self.dernier().result, 'duplicate')

    def test_charge_invalide_tracee_avec_son_motif(self):
        self.poster(ChargeUtile.valide(direction='video'))
        trace = self.dernier()
        self.assertEqual(trace.result, 'invalid')
        self.assertIn('direction', trace.detail)

    # ── Lectures ─────────────────────────────────────────────────────────────

    def test_consultation_tracee(self):
        """Le cœur du dispositif.

        Une écriture laisse une trace visible — l'appel apparaît dans la liste.
        Une consultation ne laisse rien : sans ce journal, un jeton volé
        pourrait parcourir le carnet d'adresses numéro par numéro sans qu'il en
        subsiste la moindre trace.
        """
        self.url_open(
            '/call_tracker/contact/+213555700001',
            headers={'Authorization': f'Bearer {self.JETON}'},
        )
        trace = self.dernier()
        self.assertEqual(trace.action, 'contact_lookup')
        self.assertEqual(trace.result, 'ok')
        self.assertEqual(trace.phone_number, '+213555700001')

    def test_consultation_infructueuse_tracee(self):
        self.url_open(
            '/call_tracker/contact/+213555999000',
            headers={'Authorization': f'Bearer {self.JETON}'},
        )
        self.assertEqual(self.dernier().result, 'not_found')

    def test_balayage_du_carnet_visible_dans_le_journal(self):
        """Ce que le journal doit rendre constatable : une énumération."""
        for i in range(5):
            self.url_open(
                f'/call_tracker/contact/+21355570{i:04d}',
                headers={'Authorization': f'Bearer {self.JETON}'},
            )
        self.assertEqual(
            self.Trace.search_count([('action', '=', 'contact_lookup')]), 5
        )

    # ── Refus ────────────────────────────────────────────────────────────────

    def test_jeton_refuse_trace_sans_appareil(self):
        """La ligne qu'on veut pouvoir compter : un jeton révoqué resté dans un
        téléphone, ou quelqu'un qui tâtonne."""
        self.poster(ChargeUtile.valide(), jeton='pas-le-bon')
        trace = self.dernier()
        self.assertEqual(trace.result, 'unauthorized')
        self.assertFalse(trace.device_id)

    def test_consultation_refusee_tracee(self):
        self.url_open(
            '/call_tracker/contact/+213555700001',
            headers={'Authorization': 'Bearer faux'},
        )
        trace = self.dernier()
        self.assertEqual(trace.action, 'contact_lookup')
        self.assertEqual(trace.result, 'unauthorized')

    # ── Robustesse ───────────────────────────────────────────────────────────

    def test_un_audit_en_echec_ne_casse_pas_l_appel(self):
        """Un journal d'audit qui fait tomber la fonctionnalité qu'il observe
        est pire que pas de journal : on le désactive au premier incident."""
        charge = ChargeUtile.valide(client_event_id='evt-audit-robuste')
        # Numéro absurdement long : le modèle tronque, mais même une écriture
        # qui échouerait ne doit pas empêcher l'appel d'être journalisé.
        charge['phone_number'] = '+' + '9' * 500
        reponse = self.poster(charge)
        self.assertEqual(reponse.status_code, 201)
