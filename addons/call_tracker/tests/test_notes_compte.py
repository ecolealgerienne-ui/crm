# -*- coding: utf-8 -*-
from odoo.tests import HttpCase, tagged

from .common import BancCallTracker, ChargeUtile


@tagged('post_install', '-at_install')
class TestNotesDuCompte(HttpCase, BancCallTracker):
    """L'historique des notes, rassemblé sur la fiche du compte.

    Le problème que cet écran résout : une note vit dans le fil de la PISTE
    quand l'appel en avait une, sinon dans celui du contact — la piste
    l'emporte. L'historique est donc éclaté par construction, et de plus en
    plus à mesure qu'un client accumule des affaires. Mesuré sur les données
    réelles avant ce chantier : sept notes sur huit sur des pistes, une seule
    visible depuis une fiche client.
    """

    def setUp(self):
        super().setUp()
        self.appareil = self.creer_appareil()
        self.Appel = self.env['call.tracker.log']
        self.societe = self.env['res.partner'].create({
            'name': 'Compte groupé', 'is_company': True,
        })
        self.floyd = self.env['res.partner'].create({
            'name': 'Floyd', 'parent_id': self.societe.id,
            'phone': '+213770220011',
        })
        self.collegue = self.env['res.partner'].create({
            'name': 'Collègue', 'parent_id': self.societe.id,
            'phone': '+213770220022',
        })

    def appeler(self, numero, identifiant, note):
        self.poster(ChargeUtile.valide(
            client_event_id=identifiant, phone_number=numero, note=note,
        ))

    def notes(self, fiche):
        return self.env['mail.message'].search(fiche._domaine_notes())

    def corps(self, fiche):
        return ' '.join(self.notes(fiche).mapped('body'))

    # ── L'accumulation ───────────────────────────────────────────────────────

    def test_les_notes_s_accumulent_au_lieu_de_se_remplacer(self):
        self.appeler('+213770220011', 'evt-cum-1', 'Premier échange')
        self.appeler('+213770220011', 'evt-cum-2', 'Deuxième échange')
        self.appeler('+213770220011', 'evt-cum-3', 'Troisième échange')

        corps = self.corps(self.societe)
        for texte in ('Premier échange', 'Deuxième échange', 'Troisième échange'):
            self.assertIn(texte, corps)

    # ── Le rassemblement ─────────────────────────────────────────────────────

    def test_les_notes_d_une_piste_remontent_au_compte(self):
        """Le cœur du problème : sans cela, la fiche client est presque vide."""
        piste = self.env['crm.lead'].create({
            'name': 'Affaire du compte', 'partner_id': self.floyd.id,
            'phone': '+213770220011',
        })
        self.appeler('+213770220011', 'evt-piste', 'Note posée sur la piste')

        appel = self.Appel.search([('client_event_id', '=', 'evt-piste')])
        self.assertEqual(appel.lead_id, piste, "la piste doit l'emporter")
        self.assertIn('Note posée sur la piste', self.corps(self.societe))

    def test_les_notes_des_collegues_remontent_au_compte(self):
        """Une société à cinq interlocuteurs ne doit pas obliger à ouvrir cinq
        fiches pour reconstituer une conversation."""
        self.appeler('+213770220011', 'evt-floyd', 'Vu avec Floyd')
        self.appeler('+213770220022', 'evt-collegue', 'Vu avec le collègue')

        corps = self.corps(self.societe)
        self.assertIn('Vu avec Floyd', corps)
        self.assertIn('Vu avec le collègue', corps)

    def test_ouvrir_un_contact_montre_le_compte_entier(self):
        # Le périmètre est le COMPTE, pas la fiche ouverte : partir d'un
        # interlocuteur doit montrer la même chose que partir de la société.
        self.appeler('+213770220022', 'evt-depuis-contact', 'Note du collègue')
        self.assertIn('Note du collègue', self.corps(self.floyd))

    def test_les_deux_sources_se_rejoignent(self):
        """Ce que le téléphone remonte et ce qu'on écrit depuis le CRM."""
        self.appeler('+213770220011', 'evt-source-1', 'Dit au téléphone')
        self.floyd.message_post(
            body="Écrit depuis le CRM",
            message_type='comment', subtype_xmlid='mail.mt_note',
        )

        corps = self.corps(self.societe)
        self.assertIn('Dit au téléphone', corps)
        self.assertIn('Écrit depuis le CRM', corps)

    # ── Ce qui est écarté ────────────────────────────────────────────────────

    def test_le_bruit_interne_d_odoo_est_ecarte(self):
        """`user_notification` est une mécanique interne d'Odoo : elle porte le
        même sous-type qu'une note, et n'a rien à dire du client."""
        # `message_notify` et non `message_post` : Odoo refuse explicitement de
        # poster un `user_notification` par la voie ordinaire. C'est bien la
        # mécanique interne qu'on veut reproduire ici, pas une note déguisée.
        self.floyd.message_notify(
            body="Bruit interne",
            partner_ids=self.env.user.partner_id.ids,
        )
        self.assertNotIn('Bruit interne', self.corps(self.societe))

    def test_un_courriel_au_client_n_est_pas_une_note_interne(self):
        # Sous-type « Discussions » : c'est une communication SORTANTE, pas
        # une note prise pour soi. Les mélanger ferait relire au commercial,
        # à la sonnerie, ce que le client a déjà lu.
        self.floyd.message_post(
            body="Bonjour, voici votre devis",
            message_type='comment', subtype_xmlid='mail.mt_comment',
        )
        self.assertNotIn('voici votre devis', self.corps(self.societe))

    # ── Le compteur ──────────────────────────────────────────────────────────

    def test_le_compteur_suit_le_nombre_de_notes(self):
        self.appeler('+213770220011', 'evt-compte-1', 'Une')
        self.floyd.invalidate_recordset(['call_note_count'])
        avant = self.floyd.call_note_count

        self.appeler('+213770220011', 'evt-compte-2', 'Deux')
        self.floyd.invalidate_recordset(['call_note_count'])

        self.assertGreater(self.floyd.call_note_count, avant)

    def test_l_action_ouvre_la_liste_du_compte(self):
        action = self.floyd.action_voir_notes()
        self.assertEqual(action['res_model'], 'mail.message')
        self.assertIn('Compte groupé', action['name'])
