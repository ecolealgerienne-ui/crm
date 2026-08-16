# -*- coding: utf-8 -*-
"""Les faits de Promo, portes par la fiche client.

⚠️ **Ce fichier a change de sujet le 2026-08-16.** Il eprouvait la vue SQL
`echango.promo.suivi`, supprimee en meme temps que l'ecran « Analyses » qu'elle
servait — celui-ci declarait trois vues, n'en definissait aucune, et son unique
onglet lisible etait le doublon appauvri de l'ecran de suivi.

Deux de ses quatre regles ne tenaient PAS a la vue SQL et lui survivent : elles
sont reecrites ici sur `res.partner`. Supprimer le fichier avec son sujet aurait
fait disparaitre des garde-fous en meme temps que du code mort.
"""
from datetime import timedelta

from odoo import fields
from odoo.tests import TransactionCase, tagged
from odoo.tools.safe_eval import safe_eval


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

    def _vus_par_l_ecran(self):
        action = self.env.ref('echango_promo_crm.action_echango_promo_suivi')
        return self.env['res.partner'].search(safe_eval(action.domain))

    def test_le_zero_de_la_colonne_jours_n_est_jamais_SEUL_a_l_ecran(self):
        """⚠️ **Ici, un commercant qui n'a jamais publie affiche `0` jour.**

        La vue SQL rendait un vide ; `promo_jours_depuis_publication` rend zero,
        et zero se lit « publie aujourd'hui » — exactement l'inverse de la
        verite. Ce n'est tenable que parce que la colonne « Jamais publie » et
        le grise-ligne sont dans la MEME vue : ce sont eux qui disent au lecteur
        que ce zero n'en est pas un.

        D'ou le controle sur l'arch : retirer cette colonne ou cette decoration
        ne casserait aucun code et rendrait le zero mensonger.
        """
        compte = self._compte('u1')
        self.assertTrue(compte.partner_id.promo_jamais_publie)
        self.assertEqual(compte.partner_id.promo_jours_depuis_publication, 0)

        arch = self.env.ref('echango_promo_crm.view_commercant_promo_list').arch
        self.assertIn(
            'promo_jamais_publie', arch,
            "la colonne « Jamais publie » a disparu : le 0 de la colonne "
            "« Jours » se lit desormais « publie aujourd'hui »")
        self.assertIn(
            'decoration-muted="promo_jamais_publie"', arch,
            "le grise-ligne a disparu : plus rien ne distingue a l'oeil un "
            "commercant qui n'a jamais publie")

    def test_les_jours_se_comptent_depuis_la_derniere_publication(self):
        il_y_a_dix_jours = fields.Datetime.now() - timedelta(days=10)
        compte = self._compte('u2',
                              date_derniere_publication=il_y_a_dix_jours)
        self.assertEqual(compte.partner_id.promo_jours_depuis_publication, 10)
        self.assertFalse(compte.partner_id.promo_jamais_publie)

    def test_un_compte_supprime_sort_de_l_ecran(self):
        """Il reste envoye 30 jours par Promo, mais il n'a plus rien a suivre.

        ⚠️ Le controle porte sur le **domaine de l'action**, seul endroit ou
        cette exclusion vit desormais. Le `WHERE` de la vue SQL en portait une
        seconde copie ; deux copies d'une regle divergent au premier changement,
        et c'est un argument de plus pour l'avoir supprimee.
        """
        compte = self._compte('u3', supprime_le=fields.Datetime.now())
        self.assertNotIn(compte.partner_id, self._vus_par_l_ecran())

    def test_un_compte_vivant_est_bien_a_l_ecran(self):
        """⚠️ **Le temoin.** Sans lui, un domaine casse ne rendant RIEN ferait
        passer le test precedent : le silence est aussi ce que rend une chaine
        de mesure qui ne mesure plus."""
        compte = self._compte('u4')
        self.assertIn(compte.partner_id, self._vus_par_l_ecran())
