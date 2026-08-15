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


@tagged('post_install', '-at_install')
class TestRepriseDesEchecs(TransactionCase):
    """`erreur` doit etre repris, pas abandonne."""

    def setUp(self):
        super().setUp()
        # ⚠️ Odoo interdit `cr.commit()` dans un `TransactionCase` : il
        # casserait le retour arriere de fin de test. On neutralise LA SEULE
        # ligne concernee — la validation intermediaire — et rien d'autre : la
        # reprise des echecs, l'arret sur quota et l'ecriture des statuts
        # restent exactement le code de production.
        Compte = self.env['echango.promo.account']
        self.patch(type(Compte), '_valider_progression', lambda self: None)
        import odoo.addons.echango_promo_crm.models.echango_promo_geocodage \
            as module
        self.patch(module, 'PAUSE_ENTRE_APPELS', 0)

        # ⚠️ **Un `TransactionCase` VOIT la base reelle**, et elle porte des
        # centaines de fiches `a_faire`. Sans ce nettoyage, un lot de dix
        # partirait geocoder dix vrais commercants et n'atteindrait jamais les
        # fiches du test : le banc rendrait vert sans avoir rien eprouve.
        Compte.search([]).geocodage_statut = 'sans_position'
        self.compteur = 0

    def _compte(self, uuid, statut):
        """Une fiche a une position UNIQUE : c'est par elle qu'on reconnait
        laquelle a ete geocodee. ⚠️ `_interroger_nominatim` est appele sur
        `self` — le recordset vide du modele — et non sur la fiche : elle n'a
        aucun autre moyen de se nommer a l'appelant."""
        self.compteur += 1
        partenaire = self.env['res.partner'].create({
            'name': "Commerce %s" % uuid, 'is_company': True})
        compte = self.env['echango.promo.account'].create({
            'partner_id': partenaire.id, 'promo_uuid': uuid,
            'nom_promo': "Commerce %s" % uuid,
            'telephone_e164': '+21360000%03d' % self.compteur, 'pays': 'DZ',
            'latitude': 34.0 + self.compteur, 'longitude': 3.2630,
        })
        compte.geocodage_statut = statut
        return compte

    def test_une_fiche_en_erreur_est_reprise_par_un_lot_suivant(self):
        """⚠️ Le defaut que ce test ferme : `erreur` etait terminal. Ses causes
        sont pourtant transitoires — un 429, un reseau coupe — et 61 fiches
        reelles y sont restees bloquees sans qu'aucune ne soit reprise. Un
        etat d'echec dont on ne sort jamais est une perte de donnee, pas un
        diagnostic."""
        Compte = self.env['echango.promo.account']
        en_erreur = self._compte('e1', 'erreur')

        appelees = []

        def _faux_appel(lat, lng):
            appelees.append((lat, lng))
            return {'city': "Djelfa", 'state': "Djelfa"}

        self.patch(type(Compte), '_interroger_nominatim',
                   lambda self, lat, lng: _faux_appel(lat, lng))

        Compte._geocoder_lot(10)

        self.assertTrue(appelees, "la fiche en erreur n'a pas ete rappelee")
        self.assertEqual(en_erreur.geocodage_statut, 'fait')
        self.assertEqual(en_erreur.partner_id.city, "Djelfa")

    def test_le_travail_neuf_passe_avant_les_echecs(self):
        """Une panne persistante ne doit pas monopoliser le lot : sinon les
        fiches jamais geocodees attendraient derriere des fiches qui echouent
        a chaque passage."""
        Compte = self.env['echango.promo.account']
        echouee = self._compte('e2', 'erreur')
        neuve = self._compte('n1', 'a_faire')

        vues = []
        self.patch(type(Compte), '_interroger_nominatim',
                   lambda self, lat, lng: (vues.append(lat),
                                           {'city': "Djelfa"})[1])

        Compte._geocoder_lot(1)

        self.assertEqual(vues, [neuve.latitude],
                         "le lot d'une fiche a pris l'echec avant le neuf")
        self.assertEqual(echouee.geocodage_statut, 'erreur')

    def test_un_429_arrete_le_lot_au_lieu_d_insister(self):
        """⚠️ Insister sous 429 change une limitation temporaire en
        bannissement d'IP — decouvert des jours apres. Mesure : le second
        appel ne doit PAS avoir lieu."""
        import urllib.error
        import urllib.request

        Compte = self.env['echango.promo.account']
        q1 = self._compte('q1', 'a_faire')
        self._compte('q2', 'a_faire')

        appels = []

        def _quota(requete, timeout=None):
            appels.append(1)
            raise urllib.error.HTTPError(
                'http://x', 429, 'Too Many Requests', {}, None)

        # ⚠️ On patche la couche RESEAU, pas `_interroger_nominatim` : c'est
        # LUI qui doit traduire le 429 en `QuotaNominatimDepasse`, et c'est
        # cette traduction qu'on eprouve. Patcher au-dessus ferait un test qui
        # verifie la logique qu'il vient d'ecrire lui-meme (regle #28).
        self.patch(urllib.request, 'urlopen', _quota)
        import odoo.addons.echango_promo_crm.models.echango_promo_geocodage \
            as module
        self.patch(module, 'PAUSE_ENTRE_APPELS', 0)

        traitees = Compte._geocoder_lot(10)

        self.assertEqual(len(appels), 1,
                         "le lot a insiste apres un refus de quota")
        self.assertEqual(traitees, 0)
        # ⚠️ Et surtout : la fiche n'est PAS marquee en erreur. Un quota
        # depasse ne dit rien sur elle.
        self.assertEqual(q1.geocodage_statut, 'a_faire')

    def test_un_echec_ORDINAIRE_marque_bien_la_fiche(self):
        """⚠️ Le contre-cas du precedent : si toute panne reseau devenait un
        arret silencieux, `erreur` ne serait plus jamais ecrit et le tableau
        de bord dirait « tout va bien » sur un geocodage a l'arret. Ce test
        est ce qui empeche la correction du 429 d'avaler les autres pannes."""
        import urllib.error
        import urllib.request

        Compte = self.env['echango.promo.account']
        Compte.search([]).geocodage_statut = 'sans_position'
        fiche = self._compte('q3', 'a_faire')

        def _panne(requete, timeout=None):
            raise urllib.error.HTTPError(
                'http://x', 503, 'Service Unavailable', {}, None)

        self.patch(urllib.request, 'urlopen', _panne)
        import odoo.addons.echango_promo_crm.models.echango_promo_geocodage \
            as module
        self.patch(module, 'PAUSE_ENTRE_APPELS', 0)

        traitees = Compte._geocoder_lot(10)

        self.assertEqual(traitees, 1)
        self.assertEqual(fiche.geocodage_statut, 'erreur')
