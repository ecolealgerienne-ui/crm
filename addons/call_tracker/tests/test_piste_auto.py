# -*- coding: utf-8 -*-
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestPisteAutomatique(TransactionCase):
    """Création d'une piste quand le numéro n'est connu de personne (§10.2)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.commercial = cls.env.ref('base.user_admin')
        cls.appareil = cls.env['call.tracker.device'].create({
            'name': 'Appareil piste auto',
            'user_id': cls.commercial.id,
        })
        cls.Appel = cls.env['call.tracker.log']

    def journaliser(self, numero, identifiant, direction='inbound'):
        return self.Appel.create({
            'client_event_id': identifiant,
            'phone_number': numero,
            'direction': direction,
            'duration_seconds': 12,
            'started_at': '2026-08-09 14:32:00',
            'device_id': self.appareil.id,
            'user_id': self.commercial.id,
        })

    # ── Ce qui doit créer une piste ──────────────────────────────────────────

    def test_numero_totalement_inconnu_cree_une_piste(self):
        appel = self.journaliser('+213555600001', 'evt-auto-1')
        self.assertTrue(appel.lead_id, 'une piste devait être créée')
        self.assertEqual(appel.lead_id.phone, '+213555600001')
        self.assertIn('+213555600001', appel.lead_id.name)

    def test_la_piste_est_attribuee_au_commercial(self):
        # C'est lui qui a le contexte de l'appel, et lui seul saura quoi en
        # faire. Une piste sans responsable finit dans un tas que personne ne
        # regarde.
        appel = self.journaliser('+213555600002', 'evt-auto-2')
        self.assertEqual(appel.lead_id.user_id, self.commercial)

    def test_le_libelle_porte_le_sens_de_l_appel(self):
        for numero, direction, attendu in [
            ('+213555610001', 'inbound', 'Entrant'),
            ('+213555610002', 'outbound', 'Sortant'),
            ('+213555610003', 'missed', 'Manqué'),
        ]:
            with self.subTest(direction=direction):
                appel = self.journaliser(
                    numero, 'evt-libelle-%s' % direction, direction
                )
                self.assertIn(attendu, appel.lead_id.name)

    def test_deuxieme_appel_du_meme_inconnu_reutilise_la_piste(self):
        """Le doublon se règle tout seul : la piste porte le numéro, donc
        l'appel suivant la retrouve. Sans cela, chaque rappel d'un prospect
        créerait une affaire de plus."""
        premier = self.journaliser('+213555600003', 'evt-auto-3a')
        second = self.journaliser('+213555600003', 'evt-auto-3b')
        self.assertEqual(premier.lead_id, second.lead_id)
        self.assertEqual(
            self.env['crm.lead'].search_count([('phone', '=', '+213555600003')]), 1
        )

    # ── Ce qui ne doit PAS créer de piste ────────────────────────────────────

    def test_contact_connu_sans_piste_ne_declenche_rien(self):
        """Un contact connu n'est pas un numéro inconnu.

        Lui créer une piste à chaque appel rouvrirait une affaire à chaque
        échange de suivi — c'est le mode de défaillance le plus probable de
        cette fonctionnalité.
        """
        contact = self.env['res.partner'].create({
            'name': 'Client fidèle', 'phone': '+213555600004',
        })
        appel = self.journaliser('+213555600004', 'evt-auto-4')
        self.assertEqual(appel.partner_id, contact)
        self.assertFalse(appel.lead_id, "aucune piste ne devait être créée")

    def test_piste_existante_est_reutilisee(self):
        piste = self.env['crm.lead'].create({
            'name': 'Affaire en cours', 'phone': '+213555600005',
        })
        appel = self.journaliser('+213555600005', 'evt-auto-5')
        self.assertEqual(appel.lead_id, piste)
        self.assertEqual(
            self.env['crm.lead'].search_count([('phone', '=', '+213555600005')]), 1
        )

    def test_numero_trop_court_ne_cree_rien(self):
        # Sans clé de rapprochement, on ne sait pas à qui on a affaire : créer
        # une piste sur trois chiffres n'aurait aucun sens.
        avant = self.env['crm.lead'].search_count([])
        appel = self.journaliser('123', 'evt-auto-court')
        self.assertFalse(appel.lead_id)
        self.assertEqual(self.env['crm.lead'].search_count([]), avant)
