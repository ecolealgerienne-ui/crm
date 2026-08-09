# -*- coding: utf-8 -*-
from odoo.tests import HttpCase, tagged

from .common import BancCallTracker, ChargeUtile


@tagged('post_install', '-at_install')
class TestNote(HttpCase, BancCallTracker):
    """Note prise après l'appel : transport, stockage, report dans le CRM."""

    def setUp(self):
        super().setUp()
        self.appareil = self.creer_appareil()
        self.contact = self.env['res.partner'].create({
            'name': 'Client noté', 'phone': '+213555920001',
        })
        self.piste = self.env['crm.lead'].create({
            'name': 'Affaire notée', 'partner_id': self.contact.id,
        })
        self.Appel = self.env['call.tracker.log']

    def poster_avec_note(self, note, identifiant='evt-note'):
        reponse = self.poster(ChargeUtile.valide(
            client_event_id=identifiant,
            phone_number='+213555920001',
            note=note,
        ))
        return reponse, self.Appel.search([('client_event_id', '=', identifiant)])

    # ── Transport et stockage ────────────────────────────────────────────────

    def test_note_transportee_et_stockee(self):
        reponse, appel = self.poster_avec_note('Relance prévue vendredi')
        self.assertEqual(reponse.status_code, 201)
        self.assertEqual(appel.note, 'Relance prévue vendredi')

    def test_note_facultative(self):
        """L'immense majorité des appels n'en portera pas.

        Exiger une saisie ferait abandonner la fonctionnalité en une semaine —
        et surtout, ferait échouer la remise de tous les appels sans note.
        """
        reponse = self.poster(ChargeUtile.valide(client_event_id='evt-sans-note'))
        self.assertEqual(reponse.status_code, 201)
        appel = self.Appel.search([('client_event_id', '=', 'evt-sans-note')])
        self.assertFalse(appel.note)

    def test_note_vide_equivaut_a_pas_de_note(self):
        _, appel = self.poster_avec_note('   ', 'evt-note-vide')
        self.assertFalse(appel.note)

    def test_note_trop_longue_refusee(self):
        reponse = self.poster(ChargeUtile.valide(
            client_event_id='evt-note-longue', note='x' * 1001,
        ))
        self.assertEqual(reponse.status_code, 400)
        self.assertIn('note', reponse.json()['detail'])

    def test_note_non_textuelle_refusee(self):
        reponse = self.poster(ChargeUtile.valide(
            client_event_id='evt-note-nombre', note=42,
        ))
        self.assertEqual(reponse.status_code, 400)

    # ── Report dans le CRM ───────────────────────────────────────────────────

    def test_note_publiee_dans_le_fil_de_la_piste(self):
        """Sans ce report, la note resterait enfermée dans un modèle technique
        que personne n'ouvre."""
        _, appel = self.poster_avec_note('Veut un devis sous huitaine', 'evt-note-fil')
        self.assertEqual(appel.lead_id, self.piste)

        message = self.env['mail.message'].search([
            ('model', '=', 'crm.lead'), ('res_id', '=', self.piste.id),
        ], order='id desc', limit=1)
        self.assertIn('Veut un devis sous huitaine', message.body)
        self.assertIn(appel.phone_number, message.body)

    def test_la_note_est_interne_et_ne_notifie_pas_le_client(self):
        # Se tromper de sous-type enverrait la note au contact par courriel.
        _, appel = self.poster_avec_note('Ne pas rappeler avant lundi', 'evt-note-interne')
        message = self.env['mail.message'].search([
            ('model', '=', 'crm.lead'), ('res_id', '=', self.piste.id),
        ], order='id desc', limit=1)
        self.assertEqual(message.subtype_id, self.env.ref('mail.mt_note'))

    def test_la_note_est_attribuee_au_commercial(self):
        _, appel = self.poster_avec_note('Compte rendu', 'evt-note-auteur')
        message = self.env['mail.message'].search([
            ('model', '=', 'crm.lead'), ('res_id', '=', self.piste.id),
        ], order='id desc', limit=1)
        self.assertEqual(message.author_id, appel.user_id.partner_id)

    def test_la_boucle_se_referme_sur_le_caller_id(self):
        """Le point qui rend la fonctionnalité utile plutôt que décorative :
        la note écrite après un appel s'affiche au suivant."""
        self.poster_avec_note('Rappeler après le 15', 'evt-note-boucle')

        reponse = self.url_open(
            '/call_tracker/contact/+213555920001',
            headers={'Authorization': f'Bearer {self.JETON}'},
        )
        self.assertIn('Rappeler après le 15', reponse.json()['last_notes'])

    def test_sans_rattachement_la_note_reste_sur_l_appel(self):
        # Un numéro trop court ne crée ni contact ni piste : la note ne doit
        # pas disparaître pour autant.
        reponse = self.poster(ChargeUtile.valide(
            client_event_id='evt-note-orpheline', phone_number='123',
            note='Numéro incomplet',
        ))
        self.assertEqual(reponse.status_code, 201)
        appel = self.Appel.search([('client_event_id', '=', 'evt-note-orpheline')])
        self.assertEqual(appel.note, 'Numéro incomplet')
        self.assertFalse(appel.lead_id)
