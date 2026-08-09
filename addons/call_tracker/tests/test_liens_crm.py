# -*- coding: utf-8 -*-
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestLiensCrm(TransactionCase):
    """Accès aux appels depuis la fiche contact et depuis la piste.

    Le rattachement existait déjà en base — `partner_id` et `lead_id` étaient
    renseignés. Ce qui manquait, c'est le chemin inverse : partir d'un client
    pour voir ses appels. Un lien qui n'existe que dans la base ne sert qu'à
    celui qui écrit du SQL.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.appareil = cls.env['call.tracker.device'].create({
            'name': 'Appareil liens',
            'user_id': cls.env.ref('base.user_admin').id,
        })
        cls.societe = cls.env['res.partner'].create({
            'name': 'Groupe Test', 'is_company': True, 'phone': '+213555930001',
        })
        cls.interlocuteur = cls.env['res.partner'].create({
            'name': 'Karim, du Groupe Test',
            'parent_id': cls.societe.id,
            'phone': '+213555930002',
        })

    def journaliser(self, numero, identifiant):
        return self.env['call.tracker.log'].create({
            'client_event_id': identifiant,
            'phone_number': numero,
            'direction': 'outbound',
            'duration_seconds': 20,
            'started_at': '2026-08-09 14:32:00',
            'device_id': self.appareil.id,
            'user_id': self.appareil.user_id.id,
        })

    # ── Contact ──────────────────────────────────────────────────────────────

    def test_compteur_sur_la_fiche_contact(self):
        self.journaliser('+213555930002', 'evt-lien-1')
        self.interlocuteur.invalidate_recordset()
        self.assertEqual(self.interlocuteur.call_tracker_count, 1)

    def test_la_societe_totalise_les_appels_de_ses_contacts(self):
        """Sur une société, les appels sont journalisés au nom de
        l'interlocuteur. Un compteur qui n'additionnerait que les appels de la
        société afficherait zéro là où il y a le plus à voir."""
        self.journaliser('+213555930002', 'evt-lien-2')  # l'interlocuteur
        self.journaliser('+213555930001', 'evt-lien-3')  # la société
        self.societe.invalidate_recordset()
        self.assertEqual(self.societe.call_tracker_count, 2)

    def test_un_contact_sans_appel_affiche_zero(self):
        muet = self.env['res.partner'].create({'name': 'Jamais appelé'})
        self.assertEqual(muet.call_tracker_count, 0)

    def test_action_du_bouton_filtre_sur_la_descendance(self):
        action = self.societe.action_voir_appels()
        self.assertEqual(action['res_model'], 'call.tracker.log')
        self.assertIn(('partner_id', 'child_of', self.societe.id), action['domain'])
        self.assertFalse(action['context']['create'])

    # ── Piste ────────────────────────────────────────────────────────────────

    def test_compteur_sur_la_piste(self):
        piste = self.env['crm.lead'].create({
            'name': 'Affaire liée', 'partner_id': self.interlocuteur.id,
        })
        self.journaliser('+213555930002', 'evt-lien-4')
        piste.invalidate_recordset()
        self.assertEqual(piste.call_tracker_count, 1)

    def test_action_du_bouton_de_la_piste(self):
        piste = self.env['crm.lead'].create({'name': 'Affaire vide'})
        action = piste.action_voir_appels()
        self.assertEqual(action['res_model'], 'call.tracker.log')
        self.assertIn(('lead_id', '=', piste.id), action['domain'])

    # ── Les vues héritées existent bien ──────────────────────────────────────

    def test_boutons_installes_dans_les_formulaires(self):
        # Une vue héritée mal ancrée ne lève pas à l'installation : elle est
        # simplement ignorée, et le bouton n'apparaît jamais.
        for xmlid, modele in [
            ('call_tracker.view_partner_form_call_tracker', 'res.partner'),
            ('call_tracker.view_crm_lead_form_call_tracker', 'crm.lead'),
        ]:
            with self.subTest(vue=xmlid):
                vue = self.env.ref(xmlid)
                self.assertEqual(vue.model, modele)
                self.assertTrue(vue.inherit_id)
                self.assertIn('action_voir_appels', vue.arch)
