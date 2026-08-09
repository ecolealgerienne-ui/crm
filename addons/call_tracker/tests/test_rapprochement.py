# -*- coding: utf-8 -*-
from odoo.tests import TransactionCase, tagged

from ..models.call_tracker_log import CHIFFRES_SIGNIFICATIFS, chiffres_significatifs


@tagged('post_install', '-at_install')
class TestRapprochement(TransactionCase):
    """Rattachement d'un appel au contact et à la piste correspondants."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.appareil = cls.env['call.tracker.device'].create({
            'name': 'Appareil de rapprochement',
            'user_id': cls.env.ref('base.user_admin').id,
        })
        cls.Appel = cls.env['call.tracker.log']

    def journaliser(self, numero, identifiant='evt'):
        return self.Appel.create({
            'client_event_id': f'{identifiant}-{numero}',
            'phone_number': numero,
            'direction': 'inbound',
            'duration_seconds': 10,
            'started_at': '2026-08-09 14:32:00',
            'device_id': self.appareil.id,
            'user_id': self.appareil.user_id.id,
        })

    # ── La clé de rapprochement ──────────────────────────────────────────────

    def test_toutes_les_ecritures_d_un_meme_numero_donnent_la_meme_cle(self):
        """Le point qui fait toute l'utilité du rattachement.

        Un mobile algérien s'écrit indifféremment de ces cinq façons, et une
        fiche contact est saisie à la main. Comparer les chaînes brutes ne
        rattacherait presque jamais rien.
        """
        ecritures = [
            '0555000000',
            '+213555000000',
            '00213555000000',
            '05 55 00 00 00',
            '+213 555.00.00.00',
        ]
        cles = {chiffres_significatifs(e) for e in ecritures}
        self.assertEqual(len(cles), 1, f'clés divergentes : {cles}')
        self.assertEqual(cles.pop(), '555000000')

    def test_numero_trop_court_ne_donne_pas_de_cle(self):
        # Mieux vaut aucun rattachement qu'un rattachement au hasard sur trois
        # chiffres : un numéro court rattacherait le premier contact venu.
        for court in ('', '123', '55500', '12345678'):
            with self.subTest(numero=court):
                self.assertEqual(chiffres_significatifs(court), '')

    def test_longueur_de_cle_conforme(self):
        self.assertEqual(
            len(chiffres_significatifs('+213555000000')), CHIFFRES_SIGNIFICATIFS
        )

    # ── Rattachement au contact ──────────────────────────────────────────────

    def test_rattache_au_contact_quel_que_soit_le_format_de_la_fiche(self):
        contact = self.env['res.partner'].create({
            'name': 'Ahmed Market',
            'phone': '05 55 00 00 00',
        })
        appel = self.journaliser('+213555000000', 'evt-format')
        self.assertEqual(appel.partner_id, contact)

    def test_numero_inconnu_ne_trouve_aucun_contact(self):
        # Depuis la décision du 2026-08-09 (§10.2), une piste EST créée pour un
        # numéro inconnu — c'est test_piste_auto.py qui le couvre. Ici on
        # vérifie seulement qu'aucun contact existant n'a été capté au passage :
        # un rapprochement trop large est plus grave qu'une absence de
        # rapprochement, il attribue un appel au mauvais client.
        appel = self.journaliser('+213555999888', 'evt-inconnu')
        self.assertFalse(appel.partner_id)

    def test_numero_trop_court_ne_rattache_rien(self):
        self.env['res.partner'].create({'name': 'Court', 'phone': '123'})
        appel = self.journaliser('123', 'evt-court')
        self.assertFalse(appel.partner_id)

    def test_contact_archive_est_ignore(self):
        self.env['res.partner'].create({
            'name': 'Ancien client',
            'phone': '+213555777666',
            'active': False,
        })
        appel = self.journaliser('+213555777666', 'evt-archive')
        self.assertFalse(
            appel.partner_id,
            "un contact archivé ne doit pas capter les appels",
        )

    # ── Rattachement à la piste ──────────────────────────────────────────────

    def test_rattache_a_la_piste_du_contact(self):
        contact = self.env['res.partner'].create({
            'name': 'Prospect', 'phone': '+213555111000',
        })
        piste = self.env['crm.lead'].create({
            'name': 'Opportunité prospect', 'partner_id': contact.id,
        })
        appel = self.journaliser('+213555111000', 'evt-piste')
        self.assertEqual(appel.partner_id, contact)
        self.assertEqual(appel.lead_id, piste)

    def test_rattache_a_une_piste_sans_contact(self):
        # Une piste peut porter un numéro avant d'être reliée à une fiche
        # contact — c'est même le cas normal d'un prospect entrant.
        piste = self.env['crm.lead'].create({
            'name': 'Piste brute', 'phone': '+213555222000',
        })
        appel = self.journaliser('+213555222000', 'evt-piste-nue')
        self.assertEqual(appel.lead_id, piste)

    def test_piste_archivee_est_ignoree(self):
        archivee = self.env['crm.lead'].create({
            'name': 'Piste perdue', 'phone': '+213555333000', 'active': False,
        })
        appel = self.journaliser('+213555333000', 'evt-piste-archivee')
        # Une affaire perdue ne doit pas se rouvrir toute seule sur un appel :
        # l'appel se rattache à une piste NEUVE, pas à celle qu'on a fermée.
        self.assertNotEqual(appel.lead_id, archivee)
        self.assertTrue(appel.lead_id.active)

    # ── Unicité ──────────────────────────────────────────────────────────────

    def test_client_event_id_est_unique_en_base(self):
        """La contrainte est posée en SQL, pas seulement vérifiée par le
        contrôleur : c'est elle qui tranche quand deux réessais se croisent."""
        from psycopg2 import IntegrityError

        from odoo.tools import mute_logger

        self.journaliser('+213555444000', 'evt-unique')
        with self.assertRaises(IntegrityError), mute_logger('odoo.sql_db'):
            with self.cr.savepoint():
                self.Appel.create({
                    'client_event_id': 'evt-unique-+213555444000',
                    'phone_number': '+213555444111',
                    'direction': 'inbound',
                    'duration_seconds': 1,
                    'started_at': '2026-08-09 15:00:00',
                    'device_id': self.appareil.id,
                    'user_id': self.appareil.user_id.id,
                })
