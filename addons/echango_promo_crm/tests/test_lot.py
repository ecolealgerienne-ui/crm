# -*- coding: utf-8 -*-
"""Le lot : ce qui est pris, ce qui est refusé, et ce qui autorise l'archivage.

⚠️ **Autant de cas qui doivent ÉCHOUER que de cas qui passent.** Un contrôleur
qu'on n'a vu que dire oui n'a montré que sa capacité à dire oui.
"""
import hashlib
import json

from odoo.tests import HttpCase, tagged

JETON = 'jeton-de-test-echango-promo'


@tagged('post_install', '-at_install')
class TestLot(HttpCase):

    def setUp(self):
        super().setUp()
        self.source = self.env['echango.promo.source'].create({
            'name': "Source de test",
            'token_hash': hashlib.sha256(JETON.encode()).hexdigest(),
        })
        self.env.cr.flush()

    def _poster(self, chemin, charge, jeton=JETON):
        return self.url_open(
            chemin, data=json.dumps(charge).encode(),
            headers={'Content-Type': 'application/json',
                     'X-Echango-Token': jeton})

    def _fiche(self, uuid, **extra):
        base = {
            'promo_uuid': uuid,
            'nom': "Commerce %s" % uuid[:4],
            'telephone_e164': '+21360000%s' % uuid[:4],
            'pays': 'DZ',
        }
        base.update(extra)
        return base

    # ── Ce qui doit passer ──────────────────────────────────────────────────

    def test_une_fiche_cree_un_partenaire_et_un_suivi(self):
        reponse = self._poster('/echango_promo/merchants/sync', {
            'lot': 'lot-1', 'items': [self._fiche('aaaa1111')]})
        self.assertEqual(reponse.status_code, 200)
        self.assertEqual(reponse.json()['prises'], 1)

        compte = self.env['echango.promo.account'].search(
            [('promo_uuid', '=', 'aaaa1111')])
        self.assertEqual(len(compte), 1)
        # ⚠️ `is_company` garantit `commercial_partner_id = self`, donc une ligne
        # par commerce dans la Couverture du portefeuille du Call Tracker.
        self.assertTrue(compte.partner_id.is_company)
        self.assertEqual(compte.partner_id.phone, compte.telephone_e164)
        self.assertEqual(compte.partner_id.country_id.code, 'DZ')

    def test_rejouer_le_meme_lot_ne_duplique_rien(self):
        for _ in range(2):
            self._poster('/echango_promo/merchants/sync', {
                'lot': 'lot-2', 'items': [self._fiche('bbbb2222')]})
        self.assertEqual(self.env['echango.promo.account'].search_count(
            [('promo_uuid', '=', 'bbbb2222')]), 1)

    # ── Ce qui doit ÊTRE REFUSÉ ─────────────────────────────────────────────

    def test_sans_jeton(self):
        r = self._poster('/echango_promo/merchants/sync',
                         {'lot': 'x', 'items': []}, jeton='')
        self.assertEqual(r.status_code, 401)

    def test_jeton_revoque(self):
        self.source.active = False
        self.env.cr.flush()
        r = self._poster('/echango_promo/merchants/sync',
                         {'lot': 'x', 'items': []})
        # ⚠️ La révocation est immédiate : `active` est revérifié à chaque
        # requête, il n'y a aucun cache.
        self.assertEqual(r.status_code, 401)

    def test_champ_de_lot_inconnu(self):
        r = self._poster('/echango_promo/merchants/sync',
                         {'lot': 'x', 'items': [], 'surprise': 1})
        self.assertEqual(r.status_code, 400)

    def test_date_dans_le_futur(self):
        r = self._poster('/echango_promo/merchants/sync', {
            'lot': 'x', 'items': [], 'genere_le': '2999-01-01T00:00:00Z'})
        self.assertEqual(r.status_code, 400)

    def test_une_fiche_fautive_ne_perd_pas_les_autres(self):
        """⚠️ Le savepoint : sur 200 objets, un seul invalide ne doit ni perdre
        le lot, ni passer inaperçu."""
        r = self._poster('/echango_promo/merchants/sync', {
            'lot': 'lot-3',
            'items': [self._fiche('cccc3333'),
                      self._fiche('dddd4444', champ_inconnu=42)]})
        corps = r.json()
        self.assertEqual(corps['prises'], 1)
        self.assertEqual(corps['refusees'], 1)
        self.assertTrue(self.env['echango.promo.account'].search_count(
            [('promo_uuid', '=', 'cccc3333')]))
        self.assertFalse(self.env['echango.promo.account'].search_count(
            [('promo_uuid', '=', 'dddd4444')]))

    # ── L'acquittement, qui seul autorise l'archivage ───────────────────────

    def test_acquittement_incomplet_n_archive_rien(self):
        """⚠️ Sans ce refus, un export interrompu à la page 3 archiverait tout
        le reste du parc — l'absence serait lue comme une disparition."""
        self._poster('/echango_promo/merchants/sync', {
            'lot': 'lot-4', 'items': [self._fiche('eeee5555')]})
        r = self._poster('/echango_promo/merchants/ack', {
            'lot': 'lot-4', 'total_envoye': 1, 'total_attendu': 99})
        self.assertEqual(r.json()['archives'], 0)
        compte = self.env['echango.promo.account'].search(
            [('promo_uuid', '=', 'eeee5555')])
        self.assertTrue(compte.partner_id.active)

    def test_acquittement_complet_archive_les_absents(self):
        self._poster('/echango_promo/merchants/sync', {
            'lot': 'lot-5', 'items': [self._fiche('ffff6666')]})
        # Un second lot qui ne contient PLUS la première fiche.
        self._poster('/echango_promo/merchants/sync', {
            'lot': 'lot-6', 'items': [self._fiche('gggg7777')]})
        self._poster('/echango_promo/merchants/ack', {
            'lot': 'lot-6', 'total_envoye': 1, 'total_attendu': 1})
        absent = self.env['echango.promo.account'].search(
            [('promo_uuid', '=', 'ffff6666')])
        self.assertFalse(absent.partner_id.active)
