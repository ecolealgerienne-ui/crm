# -*- coding: utf-8 -*-
import json
from datetime import datetime, timedelta, timezone

from odoo.tests import HttpCase, tagged

from .common import BancCallTracker, ChargeUtile


@tagged('post_install', '-at_install')
class TestHorodatageAberrant(HttpCase, BancCallTracker):
    """Les bornes de ``started_at``, et pourquoi elles refusent au lieu de corriger.

    Une horloge de téléphone fausse est la seule panne du dispositif qui ne
    produise aucun signal : la capture continue, l'écran affiche « tout est
    synchronisé », et personne n'a de raison de regarder. Les deux bornes
    posées ici transforment ce silence en un échec visible — un 400 est classé
    « refus définitif » par l'application, donc l'appel bascule en échec et le
    motif s'affiche.

    Corriger l'horodatage à la place serait pire : on inventerait une heure
    d'appel, et le délai de remise — la mesure sur laquelle repose tout le
    pilotage — deviendrait faux sans que rien ne le dise.
    """

    def setUp(self):
        super().setUp()
        self.appareil = self.creer_appareil()
        self.Appel = self.env['call.tracker.log']

    def poster_a(self, moment, identifiant):
        return self.poster(ChargeUtile.valide(
            client_event_id=identifiant,
            started_at=moment.strftime('%Y-%m-%dT%H:%M:%SZ'),
        ))

    def maintenant(self):
        return datetime.now(timezone.utc).replace(tzinfo=None)

    # ── Ce qui est refusé ────────────────────────────────────────────────────

    def test_un_appel_date_du_futur_est_refuse(self):
        """Le cas qui échappe à la purge pour toujours.

        La rétention se compte sur ``started_at`` : un appel daté de 2999 ne
        serait jamais supprimé, et survivrait à la fermeture du service.
        """
        reponse = self.poster_a(self.maintenant() + timedelta(days=1500), 'evt-h-1')
        self.assertEqual(reponse.status_code, 400)
        self.assertFalse(self.Appel.search([('client_event_id', '=', 'evt-h-1')]))

    def test_un_appel_absurdement_ancien_est_refuse(self):
        """Le cas symétrique : journalisé, puis purgé sans laisser de trace.

        L'appel serait accepté, puis supprimé au passage suivant du cron — sa
        trace d'audit avec, puisqu'elle suit la même durée. Il aurait existé
        sans que rien n'en subsiste nulle part.
        """
        reponse = self.poster_a(datetime(1970, 1, 2, 12, 0, 0), 'evt-h-2')
        self.assertEqual(reponse.status_code, 400)
        self.assertFalse(self.Appel.search([('client_event_id', '=', 'evt-h-2')]))

    def test_le_refus_dit_de_verifier_l_heure_du_telephone(self):
        """Le motif remonte jusqu'à l'écran : autant qu'il soit actionnable."""
        reponse = self.poster_a(self.maintenant() + timedelta(days=3), 'evt-h-3')
        detail = json.loads(reponse.content)['detail']
        self.assertIn('téléphone', detail)

    # ── Ce qui passe, et qui ne doit pas casser ──────────────────────────────

    def test_un_appel_qui_vient_de_finir_passe(self):
        reponse = self.poster_a(self.maintenant() - timedelta(minutes=2), 'evt-h-4')
        self.assertEqual(reponse.status_code, 201)

    def test_une_petite_avance_d_horloge_est_toleree(self):
        """La borne écarte l'aberrant, pas l'ordinaire.

        Un téléphone dont l'horloge avance de quelques minutes est banal ; s'il
        voyait ses appels refusés, on aurait remplacé une perte silencieuse par
        une perte bruyante, ce qui n'est pas mieux.
        """
        reponse = self.poster_a(self.maintenant() + timedelta(minutes=20), 'evt-h-5')
        self.assertEqual(reponse.status_code, 201)

    def test_un_appel_de_la_semaine_derniere_passe(self):
        """Le rattrapage après une longue coupure reste possible.

        C'est le mode de défaillance normal — un téléphone gelé par sa
        surcouche constructeur remonte tout d'un coup au réveil. Le borner
        trop court reviendrait à jeter précisément ce qu'on cherche à sauver.
        """
        reponse = self.poster_a(self.maintenant() - timedelta(days=7), 'evt-h-6')
        self.assertEqual(reponse.status_code, 201)

    def test_la_purge_desactivee_ne_ferme_pas_la_route(self):
        """Le piège qui a cassé les 222 tests d'un coup, figé ici.

        ``_jours_de_retention()`` rend **0** pour dire « aucune purge », et non
        « rétention nulle ». Pris au pied de la lettre, le plancher se posait à
        l'instant présent et refusait tout appel, y compris celui qui venait
        de raccrocher. Le sens choisi là-bas — un défaut de configuration ne
        doit jamais faire disparaître de données — s'inverse ici s'il n'est
        pas retraduit.
        """
        self.assertEqual(
            self.Appel._jours_de_retention(), 0,
            "prérequis : ce banc de test tourne sans rétention configurée",
        )
        reponse = self.poster_a(self.maintenant() - timedelta(days=400), 'evt-h-7')
        self.assertEqual(
            reponse.status_code, 201,
            "sans purge configurée, l'ancienneté ne doit pas fermer la route",
        )
