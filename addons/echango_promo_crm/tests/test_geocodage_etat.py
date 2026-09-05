# -*- coding: utf-8 -*-
"""L'appariement d'un nom d'etat rendu par Nominatim vers `res.country.state`.

Ce banc porte autant de cas qui doivent ECHOUER que de cas qui doivent passer
(regle #28) : un rapprochement qui dirait toujours oui rattacherait les quatre
commerces poses a « Mountain View, Californie » — la position par defaut de
l'emulateur Android — a une wilaya algerienne au hasard, et personne ne le
verrait, puisque l'ecran afficherait enfin quelque chose.
"""
from odoo.tests import TransactionCase, tagged

from ..models.echango_promo_geocodage import normaliser_nom_etat


@tagged('post_install', '-at_install')
class TestNormalisationNomEtat(TransactionCase):
    """La fonction pure, sans base ni reseau."""

    def test_accents_et_casse_disparaissent(self):
        self.assertEqual(normaliser_nom_etat("Béjaïa"), "bejaia")
        self.assertEqual(normaliser_nom_etat("BEJAIA"), "bejaia")

    def test_separateurs_disparaissent(self):
        """Les graphies divergent surtout sur les separateurs."""
        for graphie in ("M'Sila", "M Sila", "Msila", "M-Sila"):
            self.assertEqual(normaliser_nom_etat(graphie), "msila", graphie)

    def test_affixes_administratifs_disparaissent(self):
        self.assertEqual(normaliser_nom_etat("Emirate of Dubai"), "dubai")
        self.assertEqual(normaliser_nom_etat("Dubai Emirate"), "dubai")
        self.assertEqual(normaliser_nom_etat("Wilaya de Djelfa"), "djelfa")

    def test_un_vide_reste_vide_et_ne_leve_pas(self):
        """⚠️ Rendre `None` ferait planter la comparaison au lieu de ne rien
        apparier — et un plantage dans un lot de geocodage perd les fiches
        suivantes, pas seulement celle-ci."""
        self.assertEqual(normaliser_nom_etat(None), '')
        self.assertEqual(normaliser_nom_etat(''), '')
        self.assertEqual(normaliser_nom_etat('   '), '')

    def test_deux_etats_distincts_ne_se_confondent_pas(self):
        """La tolerance ne doit pas aller jusqu'a fusionner deux wilayas."""
        self.assertNotEqual(normaliser_nom_etat("Alger"),
                            normaliser_nom_etat("Algerie"))
        self.assertNotEqual(normaliser_nom_etat("Oran"),
                            normaliser_nom_etat("Ouargla"))


@tagged('post_install', '-at_install')
class TestEtatCorrespondant(TransactionCase):
    """Le rapprochement reel, contre les donnees de reference du module."""

    def _compte(self, code_pays, uuid='g1'):
        pays = self.env['res.country'].search([('code', '=', code_pays)])
        self.assertTrue(pays, "res.country doit connaitre %s" % code_pays)
        partenaire = self.env['res.partner'].create({
            'name': "Commerce %s" % uuid, 'is_company': True,
            'country_id': pays.id})
        return self.env['echango.promo.account'].create({
            'partner_id': partenaire.id, 'promo_uuid': uuid,
            'nom_promo': "Commerce %s" % uuid,
            'telephone_e164': '+21360000099', 'pays': code_pays,
        })

    # ── Les donnees de reference existent bien ────────────────────────────

    def test_les_58_wilayas_sont_chargees(self):
        """⚠️ Odoo n'en livre AUCUNE. Sans ce compte, une regression du
        manifeste rendrait tous les tests suivants verts pour une mauvaise
        raison : « rien ne matche » passerait pour « rien a matcher »."""
        wilayas = self.env['res.country.state'].search(
            [('country_id.code', '=', 'DZ')])
        self.assertEqual(len(wilayas), 58)

    def test_les_7_emirats_sont_charges(self):
        """⚠️ Ceux-la, Odoo les livre lui-meme — a l'inverse des wilayas. Ce
        module N'A PAS de fichier de reference pour `AE` : en poser un violait
        `res_country_state_name_code_uniq` et empechait l'installation. Le
        test reste parce que la dependance est reelle : si une version d'Odoo
        cessait de les livrer, l'appariement emirati tomberait en silence."""
        emirats = self.env['res.country.state'].search(
            [('country_id.code', '=', 'AE')])
        self.assertEqual(len(emirats), 7)
        self.assertEqual(
            sorted(emirats.mapped('code')),
            ['AJ', 'AZ', 'DU', 'FU', 'RK', 'SH', 'UQ'])

    # ── Ce qui doit apparier ──────────────────────────────────────────────

    def test_wilaya_rendue_telle_quelle(self):
        compte = self._compte('DZ')
        self.assertEqual(compte._etat_correspondant("Djelfa").code, '17')

    def test_wilaya_sans_accent(self):
        """Nominatim n'est pas garanti de rendre la forme accentuee."""
        compte = self._compte('DZ')
        self.assertEqual(compte._etat_correspondant("Bejaia").code, '06')

    def test_wilaya_par_alias_anglais(self):
        compte = self._compte('DZ')
        self.assertEqual(compte._etat_correspondant("Algiers").code, '16')

    def test_emirat_en_anglais_comme_Odoo_le_stocke(self):
        compte = self._compte('AE')
        self.assertEqual(compte._etat_correspondant("Abu Dhabi").code, 'AZ')
        self.assertEqual(compte._etat_correspondant("Sharjah").code, 'SH')

    def test_emirat_en_anglais_avec_UNE_AUTRE_ponctuation(self):
        """Odoo stocke « Ras al-Khaimah » ; Nominatim ecrit volontiers
        « Ras Al Khaimah ». Le tiret ne doit pas decider."""
        compte = self._compte('AE')
        self.assertEqual(compte._etat_correspondant("Ras Al Khaimah").code,
                         'RK')
        self.assertEqual(compte._etat_correspondant("Umm Al Quwain").code,
                         'UQ')

    def test_emirat_en_francais_par_alias(self):
        """⚠️ Le cas qui justifie tout ce fichier, et il penche a l'INVERSE
        des wilayas : les emirats sont stockes en anglais par Odoo, alors
        qu'on demande `accept-language=fr` a Nominatim. « Abou Dabi » et
        « Abu Dhabi » divergent des la quatrieme lettre — aucun `=ilike`, ni
        aucun `unaccent`, ne les rapprochera jamais."""
        compte = self._compte('AE')
        self.assertEqual(compte._etat_correspondant("Abou Dabi").code, 'AZ')
        self.assertEqual(compte._etat_correspondant("Charjah").code, 'SH')
        self.assertEqual(compte._etat_correspondant("Ras el Khaïmah").code,
                         'RK')
        self.assertEqual(compte._etat_correspondant("Oumm al Qaïwaïn").code,
                         'UQ')
        self.assertEqual(compte._etat_correspondant("Dubaï").code, 'DU')

    def test_emirat_avec_prefixe_administratif(self):
        compte = self._compte('AE')
        self.assertEqual(compte._etat_correspondant("Emirate of Sharjah").code,
                         'SH')

    # ── Ce qui doit REFUSER ───────────────────────────────────────────────

    def test_un_etat_inconnu_ne_rapproche_rien(self):
        compte = self._compte('DZ')
        self.assertFalse(compte._etat_correspondant("Californie"))
        self.assertFalse(compte._etat_correspondant("Île-de-France"))

    def test_un_etat_du_MAUVAIS_pays_ne_rapproche_rien(self):
        """⚠️ Le cas le plus dangereux : le nom EXISTE dans `res.country.state`,
        mais pour un autre pays. Sans le filtre par pays, un commercant
        emirati se verrait attribuer une wilaya algerienne — une donnee fausse
        et parfaitement credible a l'ecran."""
        compte = self._compte('AE')
        self.assertTrue(self.env['res.country.state'].search(
            [('name', '=', 'Djelfa')]), "Djelfa doit exister, pour AE non")
        self.assertFalse(compte._etat_correspondant("Djelfa"))

    def test_un_alias_ne_traverse_pas_les_frontieres(self):
        """« Sharjah » est un alias, mais un alias DE `AE`."""
        compte = self._compte('DZ')
        self.assertFalse(compte._etat_correspondant("Sharjah"))

    def test_sans_pays_sur_le_partenaire_rien_ne_rapproche(self):
        """⚠️ Deviner le pays depuis le nom d'etat serait exactement le repli
        que la regle #29 interdit : il rendrait indiscernables « ce commercant
        est a Djelfa » et « on ne sait pas ou il est »."""
        compte = self._compte('DZ')
        compte.partner_id.country_id = False
        self.assertFalse(compte._etat_correspondant("Djelfa"))

    def test_un_nom_vide_ne_rapproche_rien(self):
        compte = self._compte('DZ')
        self.assertFalse(compte._etat_correspondant(False))
        self.assertFalse(compte._etat_correspondant("   "))

