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

    def test_la_note_remonte_sans_balisage(self):
        """Le Caller ID s'affiche sur un téléphone, pas dans un éditeur.

        Toute emphase HTML dans le message est rendue en « *texte* » par
        html2plaintext, et se retrouvait telle quelle sur l'écran d'appel.
        """
        self.poster_avec_note('Devis a envoyer', 'evt-note-brute')
        notes = self.url_open(
            '/call_tracker/contact/+213555920001',
            headers={'Authorization': f'Bearer {self.JETON}'},
        ).json()['last_notes']
        self.assertNotIn('*', notes)
        self.assertIn('Devis a envoyer', notes)

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

    # ── Tout appel est tracé au fil, note ou pas ─────────────────────────────

    def test_un_appel_sans_note_est_quand_meme_trace(self):
        """Le défaut signalé le 2026-08-10.

        Seuls les appels portant une note apparaissaient dans la fiche. Un
        commercial ouvrant un client voyait donc ses appels entrants notés,
        et rien de ses appels sortants — dont personne ne note la plupart.
        Ouvrir une fiche doit suffire à voir qu'on a appelé.
        """
        self.poster(ChargeUtile.valide(
            client_event_id='evt-trace-muette',
            phone_number='+213555920001',
            direction='outbound',
            duration_seconds=45,
        ))
        message = self.env['mail.message'].search(
            [('model', '=', 'crm.lead'), ('res_id', '=', self.piste.id)],
            order='id desc', limit=1,
        )
        self.assertIn('+213555920001', message.body)
        self.assertIn('sortant', message.body)
        self.assertIn('45', message.body, "la durée renseigne sans ouvrir l'appel")

    def test_une_trace_muette_n_ecrase_pas_la_note_au_caller_id(self):
        """LE test de ce correctif, et le défaut qu'il aurait introduit.

        Le Caller ID affiche le dernier commentaire du fil. Si les appels sans
        note y étaient publiés comme des commentaires ordinaires, chaque appel
        muet remplacerait la dernière note utile par « Appel sortant — +213… ».
        La fiche resterait pleine et deviendrait inutile, sans la moindre
        erreur pour le signaler.
        """
        self.poster_avec_note('Veut un devis sous huitaine', 'evt-avant-muet')
        self.poster(ChargeUtile.valide(
            client_event_id='evt-apres-muet',
            phone_number='+213555920001',
            direction='outbound',
            duration_seconds=45,
        ))

        fiche = self.Appel.fiche_contact('+213555920001')
        self.assertIn('Veut un devis sous huitaine', fiche['last_notes'])
        # Le résumé de l'appel muet — « 45 s · répondu » — est ce qui aurait
        # pris la place de la note. L'en-tête, lui, est commun aux deux
        # messages : le chercher ne prouverait rien.
        self.assertNotIn('45 s', fiche['last_notes'])

    def test_la_trace_muette_est_une_notification_pas_un_commentaire(self):
        # C'est le type de message qui l'exclut du Caller ID. Le test
        # précédent constate l'effet ; celui-ci nomme le mécanisme, pour que
        # la cause soit lisible quand il cassera.
        self.poster(ChargeUtile.valide(
            client_event_id='evt-type-muet',
            phone_number='+213555920001',
            direction='outbound',
        ))
        message = self.env['mail.message'].search(
            [('model', '=', 'crm.lead'), ('res_id', '=', self.piste.id)],
            order='id desc', limit=1,
        )
        self.assertEqual(message.message_type, 'notification')
        self.assertEqual(message.subtype_id, self.env.ref('mail.mt_note'),
                         "interne dans tous les cas : jamais un envoi client")

    def test_un_appel_sortant_note_reste_un_commentaire(self):
        self.poster(ChargeUtile.valide(
            client_event_id='evt-sortant-note',
            phone_number='+213555920001',
            direction='outbound',
            note='Rappelé, commande confirmée',
        ))
        message = self.env['mail.message'].search(
            [('model', '=', 'crm.lead'), ('res_id', '=', self.piste.id)],
            order='id desc', limit=1,
        )
        self.assertEqual(message.message_type, 'comment')
        self.assertIn('Rappelé, commande confirmée', message.body)

    def test_un_appel_non_rattache_ne_trace_nulle_part(self):
        # Rien à quoi rattacher : l'appel rejoint la file « à qualifier », il
        # n'invente pas de destinataire.
        avant = self.env['mail.message'].search_count([])
        self.poster(ChargeUtile.valide(
            client_event_id='evt-muet-orphelin',
            phone_number='+213555999888',
            direction='outbound',
        ))
        self.assertEqual(self.env['mail.message'].search_count([]), avant)
