# -*- coding: utf-8 -*-
from datetime import timedelta

from odoo import fields
from odoo.tests import TransactionCase, new_test_user, tagged


@tagged('post_install', '-at_install')
class TestCouverture(TransactionCase):
    """Couverture du portefeuille — qui a été appelé, qui ne l'a pas été."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.commercial = new_test_user(
            cls.env, login='cov_commercial',
            groups='sales_team.group_sale_salesman',
        )
        cls.collegue = new_test_user(
            cls.env, login='cov_collegue',
            groups='sales_team.group_sale_salesman',
        )
        cls.appareil = cls.env['call.tracker.device'].create({
            'name': 'Appareil couverture', 'user_id': cls.commercial.id,
        })
        cls.Couverture = cls.env['call.tracker.coverage']
        cls.Appel = cls.env['call.tracker.log']
        cls.compteur = 0

    def compte(self, nom, numero, commercial=None):
        """Une société assignée à un commercial."""
        return self.env['res.partner'].create({
            'name': nom, 'is_company': True, 'phone': numero,
            'user_id': (commercial or self.commercial).id,
        })

    def appeler(self, numero, quand=None, commercial=None):
        type(self).compteur += 1
        return self.Appel.create({
            'client_event_id': 'evt-cov-%d' % self.compteur,
            'phone_number': numero,
            'direction': 'outbound',
            'duration_seconds': 60,
            'started_at': quand or fields.Datetime.now(),
            'device_id': self.appareil.id,
            'user_id': (commercial or self.commercial).id,
        })

    def ligne(self, partenaire):
        return self.Couverture.search([('partner_id', '=', partenaire.id)])

    # ── Le dénominateur ──────────────────────────────────────────────────────

    def test_un_compte_assigne_apparait_meme_sans_aucun_appel(self):
        """C'est tout l'intérêt de la mesure : ce qu'on ne voit pas ailleurs.

        Un client jamais appelé n'apparaît dans aucune liste d'appels — il
        n'existe que par différence avec le portefeuille.
        """
        compte = self.compte('Jamais appelé', '+213555700001')
        ligne = self.ligne(compte)

        self.assertTrue(ligne, "un compte assigné doit apparaître")
        self.assertTrue(ligne.never_called)
        self.assertEqual(ligne.call_count, 0)
        self.assertFalse(ligne.last_call_date)

    def test_un_compte_sans_commercial_n_est_pas_du_portefeuille(self):
        # Sans responsable, il n'appartient au portefeuille de personne : le
        # compter diluerait le taux de tout le monde.
        orphelin = self.env['res.partner'].create({
            'name': 'Sans commercial', 'is_company': True,
        })
        self.assertFalse(self.ligne(orphelin))

    def test_un_contact_rattache_ne_compte_pas_comme_une_ligne(self):
        """Une ligne par COMPTE, pas par interlocuteur.

        Sinon une société à cinq contacts pèserait cinq fois dans le
        dénominateur, et le taux de couverture n'aurait plus de sens.
        """
        societe = self.compte('Groupe Couverture', '+213555700002')
        interlocuteur = self.env['res.partner'].create({
            'name': 'Karim', 'parent_id': societe.id,
            'phone': '+213555700003', 'user_id': self.commercial.id,
        })
        self.assertTrue(self.ligne(societe))
        self.assertFalse(
            self.ligne(interlocuteur),
            "un contact rattaché ne doit pas être une ligne de portefeuille",
        )

    # ── Le numérateur ────────────────────────────────────────────────────────

    def test_appeler_un_interlocuteur_couvre_la_societe(self):
        """Le point qui rend la mesure juste.

        Les appels sont journalisés au nom de la personne qu'on a eue au
        téléphone. Compter au niveau du contact ferait apparaître comme
        « jamais appelée » une entreprise qu'on appelle chaque semaine.
        """
        societe = self.compte('Groupe Appelé', '+213555700010')
        self.env['res.partner'].create({
            'name': 'Interlocuteur', 'parent_id': societe.id,
            'phone': '+213555700011',
        })
        self.appeler('+213555700011')

        ligne = self.ligne(societe)
        self.assertFalse(ligne.never_called)
        self.assertEqual(ligne.call_count, 1)

    def test_la_date_retenue_est_celle_du_dernier_appel(self):
        compte = self.compte('Rappelé plusieurs fois', '+213555700020')
        self.appeler('+213555700020', fields.Datetime.now() - timedelta(days=40))
        self.appeler('+213555700020', fields.Datetime.now() - timedelta(days=5))

        ligne = self.ligne(compte)
        self.assertEqual(ligne.call_count, 2)
        self.assertLessEqual(ligne.days_since_last_call, 6)

    def test_jamais_appele_ne_veut_pas_dire_appele_aujourd_hui(self):
        """`days_since_last_call` est VIDE quand il n'y a jamais eu d'appel.

        Zéro signifierait « appelé aujourd'hui » — l'exact inverse, et un tri
        sur cette colonne placerait les comptes délaissés en tête des mieux
        suivis.
        """
        compte = self.compte('Aucun appel', '+213555700030')
        ligne = self.ligne(compte)
        self.assertTrue(ligne.never_called)
        self.assertFalse(ligne.days_since_last_call)

    def test_le_delaisse_ressort_par_le_filtre_a_90_jours(self):
        vieux = self.compte('Délaissé', '+213555700040')
        recent = self.compte('Suivi', '+213555700041')
        self.appeler('+213555700040', fields.Datetime.now() - timedelta(days=120))
        self.appeler('+213555700041', fields.Datetime.now() - timedelta(days=3))

        delaisses = self.Couverture.search([('days_since_last_call', '>', 90)])
        self.assertIn(self.ligne(vieux), delaisses)
        self.assertNotIn(self.ligne(recent), delaisses)

    # ── Cloisonnement ────────────────────────────────────────────────────────

    def test_chacun_voit_son_portefeuille(self):
        mien = self.compte('Mon compte', '+213555700050')
        sien = self.compte('Son compte', '+213555700051', commercial=self.collegue)

        vus = self.Couverture.with_user(self.commercial).search([])
        self.assertIn(self.ligne(mien), vus)
        self.assertNotIn(self.ligne(sien), vus)

    def test_un_responsable_voit_tous_les_portefeuilles(self):
        responsable = new_test_user(
            self.env, login='cov_responsable',
            groups='sales_team.group_sale_manager',
        )
        mien = self.compte('Compte A', '+213555700060')
        sien = self.compte('Compte B', '+213555700061', commercial=self.collegue)

        vus = self.Couverture.with_user(responsable).search([])
        self.assertIn(self.ligne(mien), vus)
        self.assertIn(self.ligne(sien), vus)

    # ── La vue reflète l'état, sans synchronisation ──────────────────────────

    def test_assigner_un_client_le_fait_apparaitre_aussitot(self):
        """Une vue SQL, pas une table : rien à tenir à jour.

        Un modèle stocké devrait être réécrit à chaque affectation de client,
        et se désynchroniserait au premier oubli.
        """
        compte = self.env['res.partner'].create({
            'name': 'Pas encore assigné', 'is_company': True,
        })
        self.assertFalse(self.ligne(compte))

        compte.user_id = self.commercial
        self.assertTrue(self.ligne(compte))
