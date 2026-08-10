# -*- coding: utf-8 -*-
import os
from unittest.mock import patch

from odoo.tests import HttpCase, new_test_user, tagged

from .common import BancCallTracker


@tagged('post_install', '-at_install')
class TestPerimetreRecherche(HttpCase, BancCallTracker):
    """Jusqu'où va la recherche depuis l'application.

    Constaté le 2026-08-10 : un appareil retrouvait le client d'un autre
    commercial, sur les deux routes. Ce n'était pas un oubli — les routes
    tournent en `sudo()` par conception, le jeton d'appareil ne portant aucun
    droit Odoo — mais rien ne permettait de choisir.

    Le réglage vit dans le `.env` du serveur, au même endroit que la durée de
    rétention.
    """

    def setUp(self):
        super().setUp()
        self.appareil = self.creer_appareil()
        self.Appel = self.env['call.tracker.log']
        self.mien = self.appareil.user_id

        self.autre = new_test_user(
            self.env, login='perimetre_collegue',
            groups='sales_team.group_sale_salesman',
        )
        self.client_a_moi = self.env['res.partner'].create({
            'name': 'Client à moi', 'phone': '+213555330011',
            'user_id': self.mien.id,
        })
        self.client_du_collegue = self.env['res.partner'].create({
            'name': 'Client du collègue', 'phone': '+213555330022',
            'user_id': self.autre.id,
        })

    def chercher(self, fragment='55533'):
        return self.url_open(
            '/call_tracker/contacts/%s' % fragment,
            headers={'Authorization': 'Bearer %s' % self.JETON},
        ).json()

    def noms(self, fragment='55533'):
        return [r['name'] for r in self.chercher(fragment).get('results', [])]

    # ── Le réglage lui-même ──────────────────────────────────────────────────

    def test_absent_vaut_tout_le_carnet(self):
        """Ne rien configurer est une situation normale.

        Changer le comportement sous les pieds d'un exploitant qui n'a rien
        demandé serait pire que de le laisser tel quel.
        """
        sauvegarde = os.environ.pop('CALL_TRACKER_SEARCH_SCOPE', None)
        try:
            self.assertEqual(self.Appel._perimetre_recherche(), 'all')
        finally:
            if sauvegarde is not None:
                os.environ['CALL_TRACKER_SEARCH_SCOPE'] = sauvegarde

    def test_une_valeur_illisible_restreint(self):
        """Le repli va dans l'autre sens que celui d'une variable absente.

        Une faute de frappe ne doit pas ouvrir le carnet d'adresses en
        silence. Restreindre à tort se remarque en une heure — un commercial
        ne retrouve plus ses clients ; ouvrir à tort ne se remarque jamais.
        """
        for valeur in ('onw', 'oui', 'tout', '1'):
            with patch.dict('os.environ', {'CALL_TRACKER_SEARCH_SCOPE': valeur}):
                self.assertEqual(self.Appel._perimetre_recherche(), 'own',
                                 "valeur %r" % valeur)

    def test_les_deux_valeurs_reconnues(self):
        for valeur, attendu in (('all', 'all'), ('own', 'own'),
                                (' ALL ', 'all'), ('Own', 'own')):
            with patch.dict('os.environ', {'CALL_TRACKER_SEARCH_SCOPE': valeur}):
                self.assertEqual(self.Appel._perimetre_recherche(), attendu)

    # ── Ouvert ───────────────────────────────────────────────────────────────

    def test_ouvert_le_client_du_collegue_remonte(self):
        with patch.dict('os.environ', {'CALL_TRACKER_SEARCH_SCOPE': 'all'}):
            noms = self.noms()
        self.assertIn('Client à moi', noms)
        self.assertIn('Client du collègue', noms)

    # ── Cloisonné ────────────────────────────────────────────────────────────

    def test_cloisonne_le_client_du_collegue_disparait(self):
        with patch.dict('os.environ', {'CALL_TRACKER_SEARCH_SCOPE': 'own'}):
            noms = self.noms()
        self.assertIn('Client à moi', noms)
        self.assertNotIn('Client du collègue', noms)

    def test_cloisonne_un_interlocuteur_de_ma_societe_reste_visible(self):
        """Un contact rattaché n'a presque jamais de commercial propre.

        Sans la remontée à la société, cloisonner rendrait invisibles tous les
        interlocuteurs — c'est-à-dire les gens qu'on appelle réellement.
        """
        societe = self.env['res.partner'].create({
            'name': 'Ma société', 'is_company': True, 'user_id': self.mien.id,
        })
        self.env['res.partner'].create({
            'name': 'Interlocuteur', 'parent_id': societe.id,
            'phone': '+213555330033',
        })
        with patch.dict('os.environ', {'CALL_TRACKER_SEARCH_SCOPE': 'own'}):
            self.assertIn('Interlocuteur', self.noms('55533'))

    def test_cloisonne_un_prospect_de_mon_affaire_reste_visible(self):
        """Un prospect n'a souvent aucun commercial sur sa fiche, seulement
        sur sa piste. L'oublier rendrait la recherche aveugle là où elle sert
        le plus : sur les affaires en cours."""
        prospect = self.env['res.partner'].create({
            'name': 'Prospect sans commercial', 'phone': '+213555330044',
        })
        self.env['crm.lead'].create({
            'name': 'Mon affaire', 'partner_id': prospect.id,
            'user_id': self.mien.id,
        })
        with patch.dict('os.environ', {'CALL_TRACKER_SEARCH_SCOPE': 'own'}):
            self.assertIn('Prospect sans commercial', self.noms('55533'))

    # ── Ce que le réglage ne touche PAS ──────────────────────────────────────

    def test_la_fiche_a_la_sonnerie_reste_ouverte(self):
        """Quand le téléphone sonne, il faut savoir qui appelle — même si la
        fiche appartient à un collègue en congé. Afficher « inconnu » ferait
        décrocher à l'aveugle, ce qui est pire que de ne rien afficher.
        """
        with patch.dict('os.environ', {'CALL_TRACKER_SEARCH_SCOPE': 'own'}):
            reponse = self.url_open(
                '/call_tracker/contact/%2B213555330022',
                headers={'Authorization': 'Bearer %s' % self.JETON},
            )
        self.assertEqual(reponse.status_code, 200)
        self.assertEqual(reponse.json()['name'], 'Client du collègue')

    # ── La trace ─────────────────────────────────────────────────────────────

    def test_le_perimetre_applique_est_journalise(self):
        """« Aucun résultat » ne dit pas si le client n'existe pas ou s'il
        appartient à un collègue. Sans le périmètre dans la trace, le premier
        réflexe serait de soupçonner une panne."""
        with patch.dict('os.environ', {'CALL_TRACKER_SEARCH_SCOPE': 'own'}):
            self.chercher()
        trace = self.env['call.tracker.audit'].search(
            [('action', '=', 'contact_search')], order='id desc', limit=1,
        )
        self.assertIn('perimetre own', trace.detail)
