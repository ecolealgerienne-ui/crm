# -*- coding: utf-8 -*-
from odoo.exceptions import UserError
from odoo.tests import TransactionCase, new_test_user, tagged

from ..models.call_tracker_device import hacher_jeton


@tagged('post_install', '-at_install')
class TestAppareil(TransactionCase):
    """Cycle de vie d'un appareil et de son jeton."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Appareil = cls.env['call.tracker.device']
        cls.appareil = cls.Appareil.create({
            'name': 'Téléphone de test',
            'user_id': cls.env.ref('base.user_admin').id,
        })

    def generer(self, appareil=None):
        """Génère un jeton et retourne sa valeur en clair."""
        action = (appareil or self.appareil).action_generer_jeton()
        return self.env['call.tracker.token.wizard'].browse(action['res_id']).token_clear

    # ── Le jeton ─────────────────────────────────────────────────────────────

    def test_le_jeton_en_clair_n_est_pas_stocke_sur_l_appareil(self):
        """La promesse centrale : une fuite de la base ne livre aucun jeton
        utilisable."""
        jeton = self.generer()
        self.assertTrue(jeton)
        self.assertNotEqual(self.appareil.token_hash, jeton)
        self.assertEqual(self.appareil.token_hash, hacher_jeton(jeton))
        self.assertEqual(len(self.appareil.token_hash), 64, 'SHA-256 hexadécimal')

    def test_deux_generations_donnent_deux_jetons_differents(self):
        self.assertNotEqual(self.generer(), self.generer())

    def test_jeton_assez_long_pour_etre_inenumerable(self):
        # 32 octets d'aléa encodés en URL-safe. C'est ce qui rend inutile une
        # fonction de hachage lente : il n'y a rien à énumérer.
        self.assertGreaterEqual(len(self.generer()), 40)

    def test_regenerer_revoque_le_precedent(self):
        ancien = self.generer()
        nouveau = self.generer()

        self.assertFalse(
            self.Appareil._resoudre_par_jeton(ancien),
            "l'ancien jeton doit cesser de désigner l'appareil",
        )
        self.assertEqual(self.Appareil._resoudre_par_jeton(nouveau), self.appareil)

    # ── Résolution ───────────────────────────────────────────────────────────

    def test_resolution_par_jeton(self):
        jeton = self.generer()
        self.assertEqual(self.Appareil._resoudre_par_jeton(jeton), self.appareil)

    def test_resolution_refuse_le_vide(self):
        self.generer()
        for valeur in ('', None):
            with self.subTest(valeur=valeur):
                self.assertFalse(self.Appareil._resoudre_par_jeton(valeur))

    def test_appareil_revoque_n_est_plus_resolu(self):
        jeton = self.generer()
        self.appareil.active = False
        self.assertFalse(
            self.Appareil._resoudre_par_jeton(jeton),
            'un search Odoo écarte déjà les archivés, mais la révocation ne '
            'doit pas dépendre de ce comportement implicite',
        )

    # ── Droits ───────────────────────────────────────────────────────────────

    def test_seul_un_administrateur_genere_un_jeton(self):
        commercial = new_test_user(
            self.env, login='commercial_test', groups='base.group_user'
        )
        with self.assertRaises(UserError):
            self.appareil.with_user(commercial).action_generer_jeton()

    # ── Compteur ─────────────────────────────────────────────────────────────

    def test_compteur_d_appels(self):
        self.assertEqual(self.appareil.log_count, 0)
        for i in range(3):
            self.env['call.tracker.log'].create({
                'client_event_id': f'evt-compteur-{i}',
                'phone_number': '+21355500000%d' % i,
                'direction': 'inbound',
                'duration_seconds': 5,
                'started_at': '2026-08-09 14:32:00',
                'device_id': self.appareil.id,
                'user_id': self.appareil.user_id.id,
            })
        self.appareil.invalidate_recordset()
        self.assertEqual(self.appareil.log_count, 3)
