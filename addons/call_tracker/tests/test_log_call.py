# -*- coding: utf-8 -*-
from odoo.tests import HttpCase, tagged

from .common import BancCallTracker, ChargeUtile


@tagged('post_install', '-at_install')
class TestLogCall(HttpCase, BancCallTracker):
    """Contrat HTTP de la route d'écriture.

    `post_install` : la route n'existe qu'une fois le module chargé dans le
    registre des contrôleurs.
    """

    def setUp(self):
        super().setUp()
        self.appareil = self.creer_appareil()
        self.Appel = self.env['call.tracker.log']

    # ── Cas nominal ──────────────────────────────────────────────────────────

    def test_appel_valide_est_journalise(self):
        reponse = self.poster(ChargeUtile.valide())

        self.assertEqual(reponse.status_code, 201)
        corps = reponse.json()
        self.assertEqual(corps['status'], 'logged')

        appel = self.Appel.browse(corps['call_id'])
        self.assertEqual(appel.client_event_id, 'evt-test-1')
        self.assertEqual(appel.direction, 'outbound')
        self.assertEqual(appel.duration_seconds, 42)
        self.assertEqual(
            appel.device_id, self.appareil,
            "l'appel doit rester attribué à l'appareil qui l'a remonté",
        )
        self.assertEqual(appel.user_id, self.appareil.user_id)

    def test_le_fuseau_est_converti_en_utc(self):
        # Le point le plus facile à casser sans s'en apercevoir : Odoo stocke
        # des datetimes naïfs en UTC, et une conversion oubliée décale les
        # appels de plusieurs heures sans lever la moindre erreur.
        self.poster(ChargeUtile.valide(
            client_event_id='evt-fuseau',
            started_at='2026-08-09T15:00:00+01:00',
        ))
        appel = self.Appel.search([('client_event_id', '=', 'evt-fuseau')])
        self.assertEqual(str(appel.started_at), '2026-08-09 14:00:00')

    def test_appareil_marque_comme_vu(self):
        self.assertFalse(self.appareil.last_seen)
        self.poster(ChargeUtile.valide(client_event_id='evt-vu'))
        self.appareil.invalidate_recordset()
        self.assertTrue(self.appareil.last_seen)

    # ── Idempotence ──────────────────────────────────────────────────────────

    def test_rejeu_du_meme_evenement_ne_cree_pas_de_doublon(self):
        """Le cœur du contrat.

        L'app garde une file locale persistante et réémet ce qu'elle n'a pas pu
        livrer : les réessais sont certains, pas hypothétiques. Chaque coupure
        réseau produirait un doublon si cette garantie sautait.
        """
        charge = ChargeUtile.valide(client_event_id='evt-rejeu')

        premiere = self.poster(charge)
        seconde = self.poster(charge)

        self.assertEqual(premiere.status_code, 201)
        self.assertEqual(premiere.json()['status'], 'logged')

        # 200 et non une erreur : un 4xx ferait réessayer l'app indéfiniment
        # dans le seul cas où tout va bien.
        self.assertEqual(seconde.status_code, 200)
        self.assertEqual(seconde.json()['status'], 'duplicate')
        self.assertEqual(seconde.json()['call_id'], premiere.json()['call_id'])

        self.assertEqual(
            self.Appel.search_count([('client_event_id', '=', 'evt-rejeu')]), 1
        )

    # ── Authentification ─────────────────────────────────────────────────────

    def test_sans_jeton(self):
        reponse = self.poster(ChargeUtile.valide(), jeton=None)
        self.assertEqual(reponse.status_code, 401)
        self.assertEqual(self.Appel.search_count([]), 0)

    def test_jeton_inconnu(self):
        reponse = self.poster(ChargeUtile.valide(), jeton='pas-le-bon')
        self.assertEqual(reponse.status_code, 401)

    def test_appareil_revoque(self):
        self.appareil.active = False
        reponse = self.poster(ChargeUtile.valide(client_event_id='evt-revoque'))
        self.assertEqual(reponse.status_code, 401)
        self.assertEqual(
            self.Appel.search_count([('client_event_id', '=', 'evt-revoque')]), 0,
            "révoquer un appareil doit fermer la porte, pas seulement la signaler",
        )

    def test_un_jeton_ne_donne_aucun_droit_odoo(self):
        """Le jeton désigne un appareil, il n'ouvre pas de session.

        C'est la promesse de sécurité qui justifie ce module plutôt que l'API
        générique d'Odoo. Si une session s'ouvrait, le porteur du jeton
        hériterait des droits de l'utilisateur associé.
        """
        reponse = self.poster(ChargeUtile.valide(client_event_id='evt-session'))
        self.assertEqual(reponse.status_code, 201)
        self.assertNotIn('session_id', reponse.cookies)

    # ── Validation stricte de la charge utile ────────────────────────────────

    def test_champ_non_reconnu_est_refuse(self):
        """Refus, et non ignorance silencieuse.

        Un champ inattendu signale un désaccord de version entre l'app et le
        serveur. L'ignorer ferait journaliser des appels amputés sans que
        personne ne le remarque.
        """
        reponse = self.poster(
            ChargeUtile.valide(client_event_id='evt-extra', rep_external_id='amar_001')
        )
        self.assertEqual(reponse.status_code, 400)
        self.assertIn('rep_external_id', reponse.json()['detail'])

    def test_champ_obligatoire_absent(self):
        for champ in ('client_event_id', 'phone_number', 'direction', 'started_at'):
            with self.subTest(champ=champ):
                reponse = self.poster(ChargeUtile.sans(champ))
                self.assertEqual(reponse.status_code, 400)
                self.assertIn(champ, reponse.json()['detail'])

    def test_duration_seconds_est_facultatif(self):
        reponse = self.poster(ChargeUtile.sans('duration_seconds'))
        self.assertEqual(reponse.status_code, 201)
        self.assertEqual(self.Appel.browse(reponse.json()['call_id']).duration_seconds, 0)

    def test_direction_hors_liste(self):
        reponse = self.poster(ChargeUtile.valide(direction='video'))
        self.assertEqual(reponse.status_code, 400)

    def test_horodatage_sans_fuseau_est_refuse(self):
        # Accepter un horodatage nu reviendrait à le supposer UTC : le
        # téléphone d'un commercial peut être sur n'importe quel fuseau.
        reponse = self.poster(ChargeUtile.valide(started_at='2026-08-09T14:32:00'))
        self.assertEqual(reponse.status_code, 400)
        self.assertIn('fuseau', reponse.json()['detail'])

    def test_horodatage_illisible(self):
        reponse = self.poster(ChargeUtile.valide(started_at='hier soir'))
        self.assertEqual(reponse.status_code, 400)

    def test_durees_aberrantes(self):
        for duree in (-5, 86401, 'quarante', True):
            with self.subTest(duree=duree):
                reponse = self.poster(ChargeUtile.valide(duration_seconds=duree))
                self.assertEqual(
                    reponse.status_code, 400,
                    f'{duree!r} devrait être refusé',
                )

    def test_numero_vide(self):
        reponse = self.poster(ChargeUtile.valide(phone_number='   '))
        self.assertEqual(reponse.status_code, 400)

    def test_corps_illisible(self):
        reponse = self.poster(None, brut='ceci nest pas du json')
        self.assertEqual(reponse.status_code, 400)

    def test_corps_json_mais_pas_un_objet(self):
        reponse = self.poster(None, brut='[1, 2, 3]')
        self.assertEqual(reponse.status_code, 400)
