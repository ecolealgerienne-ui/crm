# -*- coding: utf-8 -*-
from datetime import timedelta

from odoo import fields
from odoo.exceptions import AccessError
from odoo.tests import TransactionCase, new_test_user, tagged


@tagged('post_install', '-at_install')
class TestIndicateurs(TransactionCase):
    """Champs dérivés et cloisonnement — le lot 1 du reporting."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.commercial = new_test_user(
            cls.env, login='ct_commercial',
            groups='sales_team.group_sale_salesman', tz='Africa/Algiers',
        )
        cls.collegue = new_test_user(
            cls.env, login='ct_collegue',
            groups='sales_team.group_sale_salesman', tz='Africa/Algiers',
        )
        cls.responsable = new_test_user(
            cls.env, login='ct_responsable',
            groups='sales_team.group_sale_manager',
        )
        cls.appareil = cls.env['call.tracker.device'].create({
            'name': 'Appareil indicateurs', 'user_id': cls.commercial.id,
        })
        cls.Appel = cls.env['call.tracker.log']
        cls.compteur = 0

    def journaliser(self, duree=30, quand='2026-08-09 14:32:00', commercial=None):
        type(self).compteur += 1
        return self.Appel.create({
            'client_event_id': 'evt-ind-%d' % self.compteur,
            'phone_number': '+21355590%04d' % self.compteur,
            'direction': 'outbound',
            'duration_seconds': duree,
            'started_at': quand,
            'device_id': self.appareil.id,
            'user_id': (commercial or self.commercial).id,
        })

    # ── Issue de l'appel ─────────────────────────────────────────────────────

    def test_un_sortant_sans_reponse_n_est_pas_manque(self):
        """Le défaut que ce champ existe pour éviter.

        Android journalise un sortant qui sonne dans le vide en `outbound`
        avec une durée nulle : `missed` ne concerne que les entrants. Compter
        le décroché sur la seule direction rendrait faux tout le sortant.
        """
        appel = self.journaliser(duree=0)
        self.assertEqual(appel.direction, 'outbound')
        self.assertEqual(appel.outcome, 'no_answer')

    def test_une_conversation_est_repondue(self):
        self.assertEqual(self.journaliser(duree=45).outcome, 'answered')

    def test_l_issue_est_stockee_donc_groupable(self):
        # Un champ calculé non stocké ne peut pas servir de colonne dans un
        # tableau croisé — ce qui est tout l'objet de ces champs.
        self.assertTrue(self.Appel._fields['outcome'].store)
        self.journaliser(duree=10)
        groupes = self.Appel._read_group(
            [('user_id', '=', self.commercial.id)],
            groupby=['outcome'], aggregates=['__count'],
        )
        self.assertTrue(groupes)

    # ── Heure locale ─────────────────────────────────────────────────────────

    def test_l_heure_est_celle_du_commercial_pas_l_utc(self):
        # 22 h 30 UTC = 23 h 30 à Alger. Stocker l'heure UTC placerait cet
        # appel dans la mauvaise tranche de la journée.
        appel = self.journaliser(quand='2026-08-09 22:30:00')
        self.assertEqual(appel.hour_of_day, 23)

    def test_fuseau_inconnu_retombe_sur_utc_sans_echouer(self):
        """Le fuseau ne peut pas être invalide côté utilisateur — Odoo valide
        `res.users.tz` contre une liste. Il peut l'être côté CONTEXTE : session
        mal formée, appel distant qui pousse n'importe quoi. Le calcul ne doit
        pas échouer pour autant, un appel vaut mieux qu'une heure exacte."""
        self.commercial.tz = False
        type(self).compteur += 1
        appel = self.Appel.with_context(tz='Mars/Olympus_Mons').create({
            'client_event_id': 'evt-ind-tz-%d' % self.compteur,
            'phone_number': '+213555910001',
            'direction': 'outbound',
            'duration_seconds': 5,
            'started_at': '2026-08-09 22:30:00',
            'device_id': self.appareil.id,
            'user_id': self.commercial.id,
        })
        self.assertEqual(appel.hour_of_day, 22)
        self.commercial.tz = 'Africa/Algiers'

    def test_aucun_champ_semaine_n_est_ajoute(self):
        """Odoo groupe déjà par semaine, dans le fuseau de l'utilisateur.

        Un champ stocké serait calculé en UTC, et un appel du dimanche soir
        tomberait dans la mauvaise semaine — deux façons de compter la même
        chose qui ne concordent pas.
        """
        self.assertNotIn('week_number', self.Appel._fields)

    # ── Délai de remise ──────────────────────────────────────────────────────

    def test_le_delai_de_remise_est_mesure(self):
        il_y_a_deux_heures = fields.Datetime.now() - timedelta(hours=2)
        appel = self.journaliser(quand=il_y_a_deux_heures)
        self.assertGreaterEqual(appel.delivery_lag_minutes, 118)
        self.assertLessEqual(appel.delivery_lag_minutes, 122)

    def test_une_horloge_de_telephone_dereglee_ne_donne_pas_de_delai_negatif(self):
        # Un appel « du futur » fausserait toute moyenne s'il comptait négatif.
        dans_une_heure = fields.Datetime.now() + timedelta(hours=1)
        self.assertEqual(self.journaliser(quand=dans_une_heure).delivery_lag_minutes, 0)

    # ── Cloisonnement ────────────────────────────────────────────────────────

    def test_un_commercial_ne_voit_que_ses_appels(self):
        sien = self.journaliser()
        autre = self.journaliser(commercial=self.collegue)

        visibles = self.Appel.with_user(self.commercial).search([])
        self.assertIn(sien, visibles)
        self.assertNotIn(autre, visibles, "un commercial ne doit pas voir les "
                                          "appels de ses collègues")

    def test_un_responsable_voit_tout(self):
        sien = self.journaliser()
        autre = self.journaliser(commercial=self.collegue)

        visibles = self.Appel.with_user(self.responsable).search([])
        self.assertIn(sien, visibles)
        self.assertIn(autre, visibles)

    def test_un_utilisateur_hors_ventes_n_a_aucun_acces(self):
        comptable = new_test_user(self.env, login='ct_comptable',
                                  groups='base.group_user')
        self.journaliser()
        with self.assertRaises(AccessError):
            self.Appel.with_user(comptable).search([])

    def test_la_fiche_contact_reste_lisible_sans_acces_aux_appels(self):
        """Le piège du cloisonnement.

        Un comptable ouvre lui aussi des fiches contact. Si le compteur
        d'appels levait une erreur d'accès, la fiche ENTIÈRE deviendrait
        illisible pour lui — à cause d'un bouton qui ne le concerne pas.
        """
        comptable = new_test_user(self.env, login='ct_comptable2',
                                  groups='base.group_user')
        contact = self.env['res.partner'].create({'name': 'Vu par tous'})
        self.assertEqual(
            contact.with_user(comptable).call_tracker_count, 0,
            'le compteur doit valoir zéro, pas lever',
        )

    def test_un_commercial_peut_qualifier_son_propre_appel(self):
        # Le cloisonnement ne doit pas lui retirer le geste de qualification.
        appel = self.journaliser()
        appel.with_user(self.commercial).action_creer_piste()
        self.assertTrue(appel.lead_id)
