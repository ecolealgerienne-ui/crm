# -*- coding: utf-8 -*-
"""Le géocodage inverse ARRIVE désormais par l'instantané, il ne se calcule plus.

Depuis la bascule du 2026-09-05, echango Promo résout la position en
`ville`/`wilaya` à la pose et transmet le résultat dans le lot nocturne
(`controllers/main.py`). Ce banc éprouve les deux gestes que le contrôleur
fait de ces trois champs :

1. `CHAMPS_FICHE` les accepte — une fiche qui les porte n'est PAS rejetée.
   C'est le point dont dépend tout l'ordre de déploiement du runbook
   (`MIGRATION_CONSOMMATEURS.md` §2) : si l'ancien module rejetait la fiche,
   la synchro de 04:00 qui suit le passage du backend promo refuserait le
   parc entier, en silence.
2. `_appliquer_lieu` reporte `ville`/`wilaya` sur la fiche client Odoo —
   **et seulement quand le géocodage a abouti** : `a_faire`, `erreur` et
   `sans_resultat` n'ont pas de ville fiable, et écraser `city` avec du vide
   effacerait une saisie manuelle du commercial.

⚠️ **Autant de cas qui doivent ÉCHOUER que de cas qui passent** (règle #28) :
un report qui écrirait toujours `city` effacerait des corrections manuelles à
chaque nuit, et personne ne le verrait — l'écran afficherait juste « autre
chose ».
"""
import hashlib
import json

from odoo.tests import HttpCase, tagged

JETON = 'jeton-de-test-echango-promo'


@tagged('post_install', '-at_install')
class TestGeocodageSynchro(HttpCase):

    def setUp(self):
        super().setUp()
        self.source = self.env['echango.promo.source'].create({
            'name': "Source de test géo",
            'token_hash': hashlib.sha256(JETON.encode()).hexdigest(),
        })
        self.env.cr.flush()

    # ── Outils ─────────────────────────────────────────────────────────────

    def _poster(self, charge):
        return self.url_open(
            '/echango_promo/merchants/sync',
            data=json.dumps(charge).encode(),
            headers={'Content-Type': 'application/json',
                     'X-Echango-Token': JETON})

    def _fiche(self, uuid, **extra):
        base = {
            'promo_uuid': uuid,
            'nom': "Commerce %s" % uuid[:4],
            'telephone_e164': '+21360000%s' % uuid[:4],
            'pays': 'DZ',
            'latitude': 36.75, 'longitude': 3.06,
        }
        base.update(extra)
        return base

    def _synchro(self, uuid, lot='lot-geo', **geo):
        """Pousse une fiche et rend le compte fraîchement relu."""
        reponse = self._poster({'lot': lot, 'items': [self._fiche(uuid, **geo)]})
        self.assertEqual(reponse.status_code, 200)
        self.env.invalidate_all()
        return self.env['echango.promo.account'].search(
            [('promo_uuid', '=', uuid)])

    # ── Le contrat élargi n'exclut plus la fiche ───────────────────────────

    def test_les_trois_champs_geo_ne_font_PAS_rejeter_la_fiche(self):
        """⚠️ Le défaut que ce test ferme est celui du runbook §2 : l'ancien
        `CHAMPS_FICHE` rejetait toute fiche portant un champ inconnu. Déployer
        le backend promo avant ce module aurait fait refuser TOUT le parc à la
        synchro de 04:00."""
        reponse = self._poster({'lot': 'lot-neuf', 'items': [self._fiche(
            'geoc0001', ville="Alger", wilaya="Alger",
            geocodage_statut='fait')]})
        corps = reponse.json()
        self.assertEqual(corps['prises'], 1)
        self.assertEqual(corps['refusees'], 0)

    def test_un_champ_geo_INVENTÉ_fait_toujours_rejeter_la_fiche(self):
        """⚠️ Le contre-cas : la liste blanche s'est élargie de trois champs
        NOMMÉS, pas ouverte. `ville_geocodee` (le nom interne, pas celui du
        contrat) ou une faute de frappe doivent toujours signaler le
        désaccord de version, pas passer inaperçus."""
        reponse = self._poster({'lot': 'lot-faute', 'items': [self._fiche(
            'geoc0002', ville_geocodee="Alger")]})
        corps = reponse.json()
        self.assertEqual(corps['prises'], 0)
        self.assertEqual(corps['refusees'], 1)
        self.assertFalse(self.env['echango.promo.account'].search_count(
            [('promo_uuid', '=', 'geoc0002')]))

    # ── Ce qui doit être reporté sur la fiche client ───────────────────────

    def test_statut_fait_reporte_ville_et_etat_natif(self):
        compte = self._synchro('geoa0001', ville="Alger", wilaya="Alger",
                               geocodage_statut='fait')
        self.assertEqual(compte.ville_geocodee, "Alger")
        self.assertEqual(compte.wilaya_geocodee, "Alger")
        self.assertEqual(compte.geocodage_statut, 'fait')
        # Reporté sur le partenaire : la ville en texte, l'État par appariement.
        self.assertEqual(compte.partner_id.city, "Alger")
        self.assertEqual(compte.partner_id.state_id.code, '16')

    def test_la_wilaya_passe_encore_par_l_appariement_Odoo(self):
        """⚠️ echango-geo rend un NOM de wilaya, jamais un id de
        `res.country.state` (§4 de ses specs). L'alias « Algiers » → « Alger »
        est donc résolu ici, à la réception, pas à la source."""
        compte = self._synchro('geoa0002', ville="Alger", wilaya="Algiers",
                               geocodage_statut='fait')
        self.assertEqual(compte.partner_id.state_id.code, '16')

    def test_wilaya_sans_correspondance_laisse_l_etat_VIDE(self):
        """⚠️ Pas d'invention : une wilaya que l'appariement ne reconnaît pas
        reste dans `wilaya_geocodee`, mais `state_id` demeure vide. Le décor de
        démo pose quatre commerces à « Mountain View, Californie » — la
        position par défaut de l'émulateur Android ; leur faire porter une
        wilaya au hasard serait une donnée fausse et crédible."""
        compte = self._synchro('geoa0003', ville="Mountain View",
                               wilaya="Californie", geocodage_statut='fait')
        self.assertEqual(compte.wilaya_geocodee, "Californie")
        self.assertEqual(compte.partner_id.city, "Mountain View")
        self.assertFalse(compte.partner_id.state_id)

    def test_la_mise_a_jour_reporte_AUSSI(self):
        """⚠️ Le témoin de la branche `existant.write(...)` : un commerçant
        d'abord reçu sans ville résolue, puis re-reçu `fait` la nuit suivante,
        doit voir sa ville apparaître. Sans l'appel dans la branche de mise à
        jour, seules les fiches NEUVES seraient géolocalisées."""
        self._synchro('geoa0004', lot='lot-j1', geocodage_statut='a_faire')
        compte = self._synchro('geoa0004', lot='lot-j2', ville="Oran",
                               wilaya="Oran", geocodage_statut='fait')
        self.assertEqual(compte.geocodage_statut, 'fait')
        self.assertEqual(compte.partner_id.city, "Oran")
        self.assertEqual(compte.partner_id.state_id.code, '31')

    # ── Ce qui ne doit RIEN écraser ───────────────────────────────────────

    def test_statut_a_faire_n_ecrase_pas_une_saisie_manuelle(self):
        """⚠️ Le cœur du garde-fou. `a_faire` = position posée, pas encore
        résolue : `ville` est `null`. Reporter ce `null` sur `city` effacerait
        la ville qu'un commercial a saisie à la main entre deux nuits."""
        compte = self._synchro('geoa0005', lot='lot-a', ville="Alger",
                               wilaya="Alger", geocodage_statut='fait')
        compte.partner_id.city = "Saisie du commercial"
        compte.partner_id.flush_recordset()

        compte = self._synchro('geoa0005', lot='lot-b',
                               geocodage_statut='a_faire')
        self.assertEqual(compte.geocodage_statut, 'a_faire')
        self.assertEqual(compte.partner_id.city, "Saisie du commercial")

    def test_statut_sans_resultat_ne_touche_pas_la_ville(self):
        """⚠️ `sans_resultat` est TERMINAL (point non cartographié — en mer,
        en plein désert), pas transitoire. Mais il n'a pas de ville pour
        autant : `city` ne doit pas être écrit, et surtout pas vidé."""
        compte = self._synchro('geoa0006', lot='lot-c', ville="Alger",
                               wilaya="Alger", geocodage_statut='fait')
        compte.partner_id.city = "Ville connue avant"
        compte.partner_id.flush_recordset()

        compte = self._synchro('geoa0006', lot='lot-d',
                               geocodage_statut='sans_resultat')
        self.assertEqual(compte.geocodage_statut, 'sans_resultat')
        self.assertEqual(compte.partner_id.city, "Ville connue avant")

    # ── Le champ absent : un défaut, pas une erreur ────────────────────────

    def test_geocodage_statut_absent_vaut_sans_position(self):
        """Un émetteur qui ne connaît pas encore le champ (ou une fiche sans
        position du tout) : le contrôleur retient `sans_position`, il ne
        plante pas et ne rejette pas la fiche."""
        compte = self._synchro('geoa0007')
        self.assertEqual(compte.geocodage_statut, 'sans_position')
        self.assertFalse(compte.partner_id.city)
