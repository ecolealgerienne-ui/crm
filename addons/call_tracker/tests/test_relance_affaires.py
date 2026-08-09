# -*- coding: utf-8 -*-
from datetime import timedelta

from odoo import fields
from odoo.tests import TransactionCase, new_test_user, tagged


@tagged('post_install', '-at_install')
class TestRelanceAffaires(TransactionCase):
    """Relance téléphonique des affaires — où le pipeline stagne."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.commercial = new_test_user(
            cls.env, login='rel_commercial',
            groups='sales_team.group_sale_salesman',
        )
        cls.collegue = new_test_user(
            cls.env, login='rel_collegue',
            groups='sales_team.group_sale_salesman',
        )
        cls.appareil = cls.env['call.tracker.device'].create({
            'name': 'Appareil relance', 'user_id': cls.commercial.id,
        })
        cls.Relance = cls.env['call.tracker.lead.activity']
        cls.Appel = cls.env['call.tracker.log']
        cls.compteur = 0

    def affaire(self, nom, numero=None, commercial=None, etape=None):
        valeurs = {'name': nom, 'user_id': (commercial or self.commercial).id}
        if numero:
            valeurs['phone'] = numero
        if etape:
            valeurs['stage_id'] = etape.id
        return self.env['crm.lead'].create(valeurs)

    def appeler(self, numero, jours=0):
        type(self).compteur += 1
        return self.Appel.create({
            'client_event_id': 'evt-rel-%d' % self.compteur,
            'phone_number': numero,
            'direction': 'outbound',
            'duration_seconds': 60,
            'started_at': fields.Datetime.now() - timedelta(days=jours),
            'device_id': self.appareil.id,
            'user_id': self.commercial.id,
        })

    def ligne(self, affaire):
        return self.Relance.search([('lead_id', '=', affaire.id)])

    # ── Le dénominateur : toutes les affaires ouvertes ───────────────────────

    def test_une_affaire_jamais_appelee_apparait(self):
        """Ce que cet écran montre et qu'aucun autre ne montre : l'absence."""
        aff = self.affaire('Jamais relancée')
        ligne = self.ligne(aff)

        self.assertTrue(ligne)
        self.assertTrue(ligne.never_called)
        self.assertEqual(ligne.call_count, 0)
        self.assertFalse(ligne.days_since_last_call)

    def test_une_affaire_archivee_disparait(self):
        # Une affaire perdue ou fermée n'est plus à relancer : la garder
        # gonflerait indéfiniment la liste de travail.
        aff = self.affaire('Perdue')
        self.assertTrue(self.ligne(aff))
        aff.active = False
        self.assertFalse(self.ligne(aff))

    # ── Le numérateur : les appels rattachés à l'affaire ─────────────────────

    def test_un_appel_rattache_compte_comme_relance(self):
        aff = self.affaire('Relancée', '+213555800001')
        self.appeler('+213555800001', jours=3)

        ligne = self.ligne(aff)
        self.assertFalse(ligne.never_called)
        self.assertEqual(ligne.call_count, 1)
        self.assertLessEqual(ligne.days_since_last_call, 4)

    def test_seuls_les_appels_de_cette_affaire_comptent(self):
        """Un appel au même contact sur une AUTRE affaire ne relance pas
        celle-ci : sinon une entreprise à plusieurs dossiers verrait tous ses
        dossiers marqués relancés par un seul appel."""
        contact = self.env['res.partner'].create({
            'name': 'Client multi-dossiers', 'phone': '+213555800010',
        })
        premiere = self.env['crm.lead'].create({
            'name': 'Dossier A', 'partner_id': contact.id,
            'user_id': self.commercial.id,
        })
        seconde = self.env['crm.lead'].create({
            'name': 'Dossier B', 'partner_id': contact.id,
            'user_id': self.commercial.id,
        })
        appel = self.appeler('+213555800010')
        # Le rapprochement automatique n'attache l'appel qu'à UNE affaire.
        self.assertIn(appel.lead_id, premiere | seconde)

        relancees = self.Relance.search([
            ('lead_id', 'in', (premiere | seconde).ids),
            ('never_called', '=', False),
        ])
        self.assertEqual(len(relancees), 1,
                         "un appel ne relance qu'une affaire")

    def test_les_delaissees_ressortent_par_le_filtre(self):
        vieille = self.affaire('Oubliée', '+213555800020')
        recente = self.affaire('Suivie', '+213555800021')
        self.appeler('+213555800020', jours=45)
        self.appeler('+213555800021', jours=2)

        delaissees = self.Relance.search([('days_since_last_call', '>', 30)])
        self.assertIn(self.ligne(vieille), delaissees)
        self.assertNotIn(self.ligne(recente), delaissees)

    # ── Étape gagnée ─────────────────────────────────────────────────────────

    def test_l_etape_gagnee_est_remontee(self):
        """Le filtre par défaut écarte les affaires gagnées : ne pas avoir
        rappelé une affaire déjà gagnée n'est pas un problème à traiter."""
        gagnee = self.env['crm.stage'].search([('is_won', '=', True)], limit=1)
        if not gagnee:
            self.skipTest("aucune étape gagnée dans cette base")
        aff = self.affaire('Signée', etape=gagnee)
        self.assertTrue(self.ligne(aff).is_won)

    # ── Cloisonnement ────────────────────────────────────────────────────────

    def test_chacun_voit_ses_affaires(self):
        mienne = self.affaire('À moi')
        sienne = self.affaire('À lui', commercial=self.collegue)

        vues = self.Relance.with_user(self.commercial).search([])
        self.assertIn(self.ligne(mienne), vues)
        self.assertNotIn(self.ligne(sienne), vues)

    def test_un_responsable_voit_toutes_les_affaires(self):
        responsable = new_test_user(
            self.env, login='rel_responsable',
            groups='sales_team.group_sale_manager',
        )
        mienne = self.affaire('Affaire A')
        sienne = self.affaire('Affaire B', commercial=self.collegue)

        vues = self.Relance.with_user(responsable).search([])
        self.assertIn(self.ligne(mienne), vues)
        self.assertIn(self.ligne(sienne), vues)

    # ── Ce que le modèle ne prétend PAS mesurer ──────────────────────────────

    def test_aucun_champ_de_taux_de_conversion(self):
        """Garde-fou délibéré.

        Un champ nommé « taux de conversion » sur ce modèle serait lu comme
        causal, alors qu'il ne s'agit que d'un instantané biaisé — un
        commercial appelle d'abord ce qui lui paraît prometteur. Le vrai calcul
        demande de dater chaque changement d'étape ; tant qu'il n'est pas fait,
        mieux vaut un chiffre absent qu'un chiffre qu'on croira causal.
        """
        interdits = [n for n in self.Relance._fields
                     if 'conversion' in n or 'taux' in n or 'rate' in n]
        self.assertFalse(interdits, f'champs trompeurs : {interdits}')
