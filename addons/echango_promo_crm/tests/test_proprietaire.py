# -*- coding: utf-8 -*-
"""Qui possède quel champ — et ce que le verrou protège vraiment."""
from odoo.exceptions import AccessError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestProprietaire(TransactionCase):

    def setUp(self):
        super().setUp()
        self.partenaire = self.env['res.partner'].create({
            'name': "Commerce test", 'is_company': True})
        self.compte = self.env['echango.promo.account'].create({
            'partner_id': self.partenaire.id,
            'promo_uuid': 'uuid-proprietaire',
            'nom_promo': "Commerce test",
            'telephone_e164': '+213600000000',
            'pays': 'DZ',
            'promos_en_ligne': 2,
        })

    def test_un_humain_ne_reecrit_pas_un_champ_de_promo(self):
        """⚠️ `readonly=True` ne protège rien : c'est une consigne d'interface,
        contournable en RPC. Le module voisin l'a appris sur ses appels."""
        humain = self.compte.with_user(self.env.ref('base.user_admin'))
        with self.assertRaises(AccessError):
            humain.write({'promos_en_ligne': 99})

    def test_le_lot_passe_par_sudo_et_ecrit(self):
        """Le pendant du précédent : le contrôleur DOIT pouvoir écrire.

        ⚠️ C'est aussi ce qui dit la limite du verrou — il protège d'une
        modification manuelle, jamais du lot. La frontière de propriété est
        tenue par le MODÈLE (ces champs ne sont pas sur `res.partner`), pas par
        cette garde.
        """
        self.compte.sudo().write({'promos_en_ligne': 7})
        self.assertEqual(self.compte.promos_en_ligne, 7)

    def test_les_champs_commerciaux_restent_libres(self):
        """Le commercial doit pouvoir travailler à côté sans être refusé."""
        # Sur le PARTENAIRE, tout est libre : c'est là que vit la relation.
        # ⚠️ `comment` est un champ HTML — Odoo enveloppe la saisie dans un
        # `<p>`. Comparer la chaîne brute testerait sa mise en forme, pas notre
        # frontière de propriété.
        self.partenaire.with_user(self.env.ref('base.user_admin')).write(
            {'comment': "Rappeler lundi"})
        self.assertIn("Rappeler lundi", str(self.partenaire.comment))

    def test_la_provenance_ne_se_lit_pas_sur_une_etiquette(self):
        """⚠️ L'étiquette est un confort de lecture, pas la provenance.

        Un commercial peut la retirer ; l'identifiant technique, lui, reste.
        Filtrer sur l'étiquette perdrait la fiche.
        """
        self.assertTrue(self.partenaire.est_commercant_promo)
        self.partenaire.category_id = [(5, 0, 0)]
        self.assertTrue(self.partenaire.est_commercant_promo)
