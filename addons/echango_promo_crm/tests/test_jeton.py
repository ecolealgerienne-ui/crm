# -*- coding: utf-8 -*-
"""Le jeton : jamais en clair, et sa revocation est immediate."""
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestJeton(TransactionCase):

    def test_le_jeton_n_est_jamais_stocke_en_clair(self):
        source = self.env['echango.promo.source'].create({'name': "S"})
        source.action_generer_jeton()
        assistant = self.env['echango.promo.token.wizard'].search(
            [('source_id', '=', source.id)], limit=1)
        self.assertTrue(assistant.token)
        # ⚠️ L'empreinte, jamais la valeur : un jeton relisible en base est un
        # jeton qui part dans les sauvegardes.
        self.assertNotEqual(source.sudo().token_hash, assistant.token)
        self.assertEqual(source.sudo().token_hash,
                         source.empreinte(assistant.token))

    def test_regenerer_revoque_l_ancien(self):
        source = self.env['echango.promo.source'].create({'name': "S"})
        source.action_generer_jeton()
        premier = source.sudo().token_hash
        source.action_generer_jeton()
        self.assertNotEqual(source.sudo().token_hash, premier)

    def test_une_source_sans_lot_est_silencieuse(self):
        """⚠️ Jamais recu de lot n'est PAS « neuve » : c'est l'enrolement qui
        n'a jamais abouti, et c'est celui qu'on decouvre le plus tard."""
        source = self.env['echango.promo.source'].create({'name': "S"})
        self.assertTrue(source.silencieux)

    def test_l_assistant_est_transitoire_et_court(self):
        modele = self.env['echango.promo.token.wizard']
        self.assertTrue(modele._transient)
        # Un transient est une VRAIE ligne en base : six minutes suffisent a
        # copier un jeton, et limitent ce qui traine dans les sauvegardes.
        self.assertLessEqual(modele._transient_max_hours, 0.2)
