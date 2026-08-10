# -*- coding: utf-8 -*-
from odoo.tests import HttpCase, TransactionCase, tagged

from .common import BancCallTracker, ChargeUtile


@tagged('post_install', '-at_install')
class TestQualification(TransactionCase):
    """Aucune piste automatique, et un geste humain pour en créer une.

    Décision du 2026-08-09, qui revient sur le premier choix : une création
    automatique remplit le pipeline de taxis, de fournisseurs et de faux
    numéros. Un pipeline qu'on ne croit plus, personne ne le regarde.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.commercial = cls.env.ref('base.user_admin')
        cls.appareil = cls.env['call.tracker.device'].create({
            'name': 'Appareil qualification',
            'user_id': cls.commercial.id,
        })
        cls.Appel = cls.env['call.tracker.log']

    def journaliser(self, numero, identifiant, direction='inbound'):
        return self.Appel.create({
            'client_event_id': identifiant,
            'phone_number': numero,
            'direction': direction,
            'duration_seconds': 12,
            'started_at': '2026-08-09 14:32:00',
            'device_id': self.appareil.id,
            'user_id': self.commercial.id,
        })

    # ── Rien ne se crée tout seul ────────────────────────────────────────────

    def test_numero_inconnu_ne_cree_aucune_piste(self):
        avant = self.env['crm.lead'].search_count([])
        appel = self.journaliser('+213555650001', 'evt-q-1')

        self.assertFalse(appel.lead_id)
        self.assertFalse(appel.partner_id)
        self.assertEqual(
            self.env['crm.lead'].search_count([]), avant,
            "aucune piste ne doit apparaître sans geste humain",
        )

    def test_l_appel_non_rattache_rejoint_la_file_a_qualifier(self):
        """Le contrepoids au retrait de la création automatique.

        Un prospect entrant ne peut pas avoir été créé à l'avance. Ne rien
        créer le perdrait — sauf s'il apparaît dans cette file.
        """
        appel = self.journaliser('+213555650002', 'evt-q-2')
        action = self.env.ref('call_tracker.action_call_tracker_a_qualifier')

        # `domain` est stocké en TEXTE sur ir.actions.act_window, pas en liste :
        # il faut l'évaluer pour l'utiliser comme un domaine.
        from ast import literal_eval
        domaine = literal_eval(action.domain)
        self.assertIn(appel, self.Appel.search(domaine))
        self.assertIn(('lead_id', '=', False), domaine)

    # ── Le geste de qualification ────────────────────────────────────────────

    def test_creer_une_piste_depuis_un_appel(self):
        appel = self.journaliser('+213555650003', 'evt-q-3')
        resultat = appel.action_creer_piste()

        self.assertTrue(appel.lead_id)
        self.assertEqual(appel.lead_id.phone, '+213555650003')
        self.assertIn('+213555650003', appel.lead_id.name)
        self.assertEqual(
            appel.lead_id.user_id, self.commercial,
            "la piste revient au commercial qui a passé l'appel, pas à celui "
            "qui clique",
        )
        # L'action ouvre la piste : qualifier sans la voir n'aurait pas de sens.
        self.assertEqual(resultat['res_model'], 'crm.lead')
        self.assertEqual(resultat['res_id'], appel.lead_id.id)

    def test_le_libelle_porte_le_sens_de_l_appel(self):
        for numero, direction, attendu in [
            ('+213555651001', 'inbound', 'Entrant'),
            ('+213555651002', 'outbound', 'Sortant'),
            ('+213555651003', 'missed', 'Manqué'),
        ]:
            with self.subTest(direction=direction):
                appel = self.journaliser(numero, f'evt-q-lib-{direction}', direction)
                appel.action_creer_piste()
                self.assertIn(attendu, appel.lead_id.name)

    def test_qualifier_un_appel_qualifie_tous_ceux_du_meme_numero(self):
        """Sans cela, un prospect qui a rappelé trois fois laisserait deux
        appels dans la file, et il faudrait recommencer le geste — la file ne
        se viderait jamais vraiment."""
        premier = self.journaliser('+213555650004', 'evt-q-4a')
        deuxieme = self.journaliser('+213555650004', 'evt-q-4b', 'outbound')
        # Un autre numéro, qui ne doit PAS être emporté.
        temoin = self.journaliser('+213555650099', 'evt-q-temoin')

        premier.action_creer_piste()

        self.assertEqual(deuxieme.lead_id, premier.lead_id)
        self.assertFalse(temoin.lead_id)
        self.assertEqual(
            self.env['crm.lead'].search_count([('phone', '=', '+213555650004')]), 1
        )

    def test_qualifier_deux_fois_ne_cree_pas_deux_pistes(self):
        appel = self.journaliser('+213555650005', 'evt-q-5')
        appel.action_creer_piste()
        piste = appel.lead_id
        appel.action_creer_piste()

        self.assertEqual(appel.lead_id, piste)
        self.assertEqual(
            self.env['crm.lead'].search_count([('phone', '=', '+213555650005')]), 1
        )

    # ── Ce qui n'a pas à être qualifié ───────────────────────────────────────

    def test_contact_connu_est_rattache_sans_piste(self):
        contact = self.env['res.partner'].create({
            'name': 'Client fidèle', 'phone': '+213555650006',
        })
        appel = self.journaliser('+213555650006', 'evt-q-6')

        self.assertEqual(appel.partner_id, contact)
        self.assertFalse(appel.lead_id)
        # Et il ne doit pas encombrer la file : le contact est connu.
        a_qualifier = self.Appel.search(
            [('partner_id', '=', False), ('lead_id', '=', False)]
        )
        self.assertNotIn(appel, a_qualifier)

    def test_piste_existante_est_reutilisee(self):
        piste = self.env['crm.lead'].create({
            'name': 'Affaire en cours', 'phone': '+213555650007',
        })
        appel = self.journaliser('+213555650007', 'evt-q-7')
        self.assertEqual(appel.lead_id, piste)


@tagged('post_install', '-at_install')
class TestPublicationALaQualification(HttpCase, BancCallTracker):
    """Un appel qualifié après coup arrive au fil, avec sa note.

    Le défaut que ces tests ferment : `_publier_note` ne tournait qu'à la
    création de l'appel. Un numéro inconnu n'a alors ni contact ni piste — il
    n'a rien à quoi se rattacher, et rien n'était publié. La qualification
    manuelle attachait ensuite l'appel à une piste sans jamais rattraper la
    publication.

    C'est exactement le parcours d'un nouveau prospect : appel d'un inconnu,
    puis qualification. Ces appels-là étaient donc les SEULS à ne jamais
    apparaître dans un fil — et le défaut restait invisible sur les clients
    déjà connus, c'est-à-dire pendant tous les essais.
    """

    def setUp(self):
        super().setUp()
        self.appareil = self.creer_appareil()
        self.Appel = self.env['call.tracker.log']

    def journaliser(self, identifiant, note=None, numero='+213770998877'):
        charge = ChargeUtile.valide(
            client_event_id=identifiant, phone_number=numero, note=note,
        )
        if note is None:
            charge.pop('note', None)
        self.poster(charge)
        return self.Appel.search([('client_event_id', '=', identifiant)])

    def messages(self, piste):
        return self.env['mail.message'].search(
            [('model', '=', 'crm.lead'), ('res_id', '=', piste.id)],
        )

    def test_la_note_arrive_au_fil_a_la_qualification(self):
        appel = self.journaliser('evt-qualif-note', 'Rappeler après le 15')
        self.assertFalse(appel.lead_id, "le numéro doit être inconnu au départ")

        appel.action_creer_piste()

        corps = ' '.join(self.messages(appel.lead_id).mapped('body'))
        self.assertIn('Rappeler après le 15', corps)

    def test_un_appel_muet_qualifie_est_trace_aussi(self):
        appel = self.journaliser('evt-qualif-muet')
        appel.action_creer_piste()

        corps = ' '.join(self.messages(appel.lead_id).mapped('body'))
        self.assertIn(appel.phone_number, corps)

    def test_les_appels_du_meme_numero_arrivent_aussi(self):
        """Qualifier un appel qualifie tous ceux du même numéro — leurs notes
        doivent suivre, sinon seul le dernier prospect rappelé laisse une
        trace de ce qui s'est dit."""
        premier = self.journaliser('evt-qualif-1', 'Premier contact, curieux')
        second = self.journaliser('evt-qualif-2', 'Veut une remise')

        second.action_creer_piste()

        corps = ' '.join(self.messages(second.lead_id).mapped('body'))
        self.assertIn('Veut une remise', corps)
        self.assertIn('Premier contact, curieux', corps)
        self.assertEqual(premier.lead_id, second.lead_id)

    def test_la_note_revient_au_caller_id_apres_qualification(self):
        """La boucle complète : elle était rompue précisément là.

        Un prospect inconnu appelle, on note, on qualifie. Au rappel suivant,
        le téléphone doit afficher ce qui s'est dit — c'est toute la raison
        d'être du report au fil.
        """
        appel = self.journaliser('evt-qualif-boucle', 'Budget validé, relancer')
        appel.action_creer_piste()

        fiche = self.Appel.fiche_contact('+213770998877')
        self.assertIn('Budget validé, relancer', fiche['last_notes'])
