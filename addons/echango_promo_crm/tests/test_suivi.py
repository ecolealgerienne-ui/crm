# -*- coding: utf-8 -*-
"""La vue de suivi : ce qu'elle montre, et ce qu'elle refuse de montrer."""
from datetime import timedelta

from odoo import fields
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestSuivi(TransactionCase):

    def _compte(self, uuid, **extra):
        partenaire = self.env['res.partner'].create({
            'name': "Commerce %s" % uuid, 'is_company': True})
        valeurs = {
            'partner_id': partenaire.id, 'promo_uuid': uuid,
            'nom_promo': "Commerce %s" % uuid,
            'telephone_e164': '+2136000000' + uuid[-2:], 'pays': 'DZ',
        }
        valeurs.update(extra)
        return self.env['echango.promo.account'].create(valeurs)

    def test_jamais_publie_rend_un_vide_et_non_un_zero(self):
        """Zero signifierait « publie aujourd'hui », et un tri sur cette
        colonne placerait les plus delaisses en tete des plus actifs."""
        compte = self._compte('u1')
        ligne = self.env['echango.promo.suivi'].search(
            [('account_id', '=', compte.id)])
        self.assertTrue(ligne.jamais_publie)
        self.assertFalse(ligne.jours_depuis_publication)

    def test_les_jours_se_comptent_depuis_la_derniere_publication(self):
        hier = fields.Datetime.now() - timedelta(days=10)
        compte = self._compte('u2', date_derniere_publication=hier)
        ligne = self.env['echango.promo.suivi'].search(
            [('account_id', '=', compte.id)])
        self.assertEqual(ligne.jours_depuis_publication, 10)
        self.assertFalse(ligne.jamais_publie)

    def test_un_compte_supprime_sort_du_suivi(self):
        """Il reste envoye 30 jours par Promo, mais il n'a plus rien a suivre."""
        compte = self._compte('u3', supprime_le=fields.Datetime.now())
        self.assertFalse(self.env['echango.promo.suivi'].search(
            [('account_id', '=', compte.id)]))

    def test_la_vue_voit_ce_qui_vient_d_etre_ecrit(self):
        """Le piege des modeles `_auto = False` : l'ORM ne sait pas qu'une vue
        SQL lit `echango_promo_account`, donc sans le vidage explicite une
        fiche creee puis consultee dans la meme transaction reste invisible."""
        compte = self._compte('u4')
        self.assertTrue(self.env['echango.promo.suivi'].search(
            [('account_id', '=', compte.id)]))
