# -*- coding: utf-8 -*-
from datetime import timedelta
from unittest.mock import patch

from odoo import fields
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestRetention(TransactionCase):
    """Purge des appels et des traces au-delà de la durée de conservation."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.appareil = cls.env['call.tracker.device'].create({
            'name': 'Appareil rétention',
            'user_id': cls.env.ref('base.user_admin').id,
        })
        cls.Appel = cls.env['call.tracker.log']
        cls.compteur = 0

    def journaliser(self, jours_avant, identifiant):
        # Numéro dérivé d'un compteur, et non d'un `hash()` : Python randomise
        # le hachage des chaînes à chaque processus, les numéros changeraient
        # donc d'une exécution à l'autre et un échec ne serait pas reproductible.
        type(self).compteur += 1
        return self.Appel.create({
            'client_event_id': identifiant,
            'phone_number': '+21355580%04d' % self.compteur,
            'direction': 'inbound',
            'duration_seconds': 5,
            'started_at': fields.Datetime.now() - timedelta(days=jours_avant),
            'device_id': self.appareil.id,
            'user_id': self.appareil.user_id.id,
        })

    # ── Lecture de la configuration ──────────────────────────────────────────

    def test_valeur_lue_dans_l_environnement(self):
        with patch.dict('os.environ', {'CALL_TRACKER_RETENTION_DAYS': '90'}):
            self.assertEqual(self.Appel._jours_de_retention(), 90)

    def test_absente_vide_ou_illisible_signifie_aucune_purge(self):
        """Le sens de l'erreur est CHOISI : un fichier d'environnement mal
        renseigné ne doit jamais faire disparaître des données."""
        for valeur in ('', '   ', 'trois cents', '-30', '0'):
            with self.subTest(valeur=valeur):
                with patch.dict('os.environ',
                                {'CALL_TRACKER_RETENTION_DAYS': valeur}):
                    self.assertEqual(self.Appel._jours_de_retention(), 0)

        import os
        sauvegarde = os.environ.pop('CALL_TRACKER_RETENTION_DAYS', None)
        try:
            self.assertEqual(self.Appel._jours_de_retention(), 0)
        finally:
            if sauvegarde is not None:
                os.environ['CALL_TRACKER_RETENTION_DAYS'] = sauvegarde

    # ── Purge ────────────────────────────────────────────────────────────────

    def test_sans_retention_rien_n_est_supprime(self):
        vieux = self.journaliser(400, 'evt-ret-garde')
        with patch.dict('os.environ', {'CALL_TRACKER_RETENTION_DAYS': '0'}):
            self.Appel._purger()
        self.assertTrue(vieux.exists(), 'aucune purge ne devait avoir lieu')

    def test_purge_ce_qui_depasse_et_garde_le_reste(self):
        ancien = self.journaliser(100, 'evt-ret-ancien')
        recent = self.journaliser(10, 'evt-ret-recent')

        with patch.dict('os.environ', {'CALL_TRACKER_RETENTION_DAYS': '30'}):
            self.Appel._purger()

        self.assertFalse(ancien.exists(), 'un appel de 100 jours devait partir')
        self.assertTrue(recent.exists(), 'un appel de 10 jours devait rester')

    def test_la_limite_se_compte_sur_la_date_de_l_appel(self):
        # Et non sur la date de création de l'enregistrement : un appel remonté
        # avec trois semaines de retard, parce que le téléphone est resté hors
        # réseau, doit être daté de l'appel.
        limite = self.journaliser(31, 'evt-ret-limite')
        with patch.dict('os.environ', {'CALL_TRACKER_RETENTION_DAYS': '30'}):
            self.Appel._purger()
        self.assertFalse(limite.exists())

    def test_les_traces_d_audit_suivent_la_meme_duree(self):
        """Conserver un journal d'audit plus longtemps que les données qu'il
        décrit produirait des traces orphelines ; l'inverse laisserait des
        appels sans trace de leur remise."""
        Trace = self.env['call.tracker.audit']
        trace = Trace.tracer('log_call', 'ok', self.appareil, numero='+213555800999')
        trace.flush_recordset()
        # `create_date` est écrit par la base : on le repositionne en SQL.
        self.env.cr.execute(
            "UPDATE call_tracker_audit SET create_date = %s WHERE id = %s",
            (fields.Datetime.now() - timedelta(days=200), trace.id),
        )
        trace.invalidate_recordset()

        with patch.dict('os.environ', {'CALL_TRACKER_RETENTION_DAYS': '30'}):
            self.Appel._purger()

        self.assertFalse(trace.exists())

    def test_la_purge_rend_le_nombre_supprime(self):
        self.journaliser(200, 'evt-ret-compte-1')
        self.journaliser(200, 'evt-ret-compte-2')
        with patch.dict('os.environ', {'CALL_TRACKER_RETENTION_DAYS': '30'}):
            self.assertGreaterEqual(self.Appel._purger(), 2)

    # ── La tâche planifiée existe et pointe au bon endroit ───────────────────

    def test_tache_planifiee_installee(self):
        cron = self.env.ref('call_tracker.cron_purge_retention')
        self.assertTrue(cron.active)
        self.assertEqual(cron.model_id.model, 'call.tracker.log')
        self.assertIn('_purger', cron.code)
