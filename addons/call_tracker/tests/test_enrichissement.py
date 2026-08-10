# -*- coding: utf-8 -*-
from odoo.exceptions import UserError
from odoo.tests import HttpCase, new_test_user, tagged

from .common import BancCallTracker, ChargeUtile


@tagged('post_install', '-at_install')
class TestEnrichissement(HttpCase, BancCallTracker):
    """Enrichir depuis le CRM, sans toucher au compte rendu de l'appel.

    Le partage : l'appel est le compte rendu d'un **événement**, figé par
    nature ; le fil du client est l'histoire de la **relation**, cumulative.
    Ces tests vérifient que la frontière tient, et que ce qu'on écrit d'un
    côté ressort bien de l'autre — sur le téléphone.
    """

    def setUp(self):
        super().setUp()
        self.appareil = self.creer_appareil()
        self.Appel = self.env['call.tracker.log']
        self.contact = self.env['res.partner'].create({
            'name': 'Client enrichi', 'phone': '+213770112233',
        })
        self.poster(ChargeUtile.valide(
            client_event_id='evt-enrichi', phone_number='+213770112233',
        ))
        self.appel = self.Appel.search([('client_event_id', '=', 'evt-enrichi')])

    # ── La frontière ─────────────────────────────────────────────────────────

    def test_les_faits_de_l_appel_restent_en_lecture_seule(self):
        """Le socle du reporting.

        Une durée corrigeable rendrait chaque chiffre négociable en réunion,
        et la mesure du délai de remise — qui doit précéder tout classement
        entre commerciaux — ne vaudrait plus rien.
        """
        for champ in ('phone_number', 'direction', 'duration_seconds',
                      'started_at', 'device_id', 'user_id'):
            self.assertTrue(
                self.Appel._fields[champ].readonly,
                "%s doit rester en lecture seule" % champ,
            )

    def test_la_note_de_l_appel_n_est_pas_reecrite_par_un_complement(self):
        note_initiale = self.appel.note
        self.completer("Le client a rappelé, il veut un devis")
        self.assertEqual(self.appel.note, note_initiale)

    # ── Le complément ────────────────────────────────────────────────────────

    def completer(self, texte):
        action = self.appel.action_completer_note()
        assistant = self.env['call.tracker.note.wizard'].browse(action['res_id'])
        assistant.note = texte
        return assistant.action_publier()

    def test_le_complement_va_au_fil_du_client(self):
        self.completer("Déménage en septembre")
        message = self.env['mail.message'].search(
            [('model', '=', 'res.partner'), ('res_id', '=', self.contact.id)],
            order='id desc', limit=1,
        )
        self.assertIn('Déménage en septembre', message.body)
        self.assertEqual(message.message_type, 'comment')
        self.assertEqual(message.subtype_id, self.env.ref('mail.mt_note'),
                         "interne : jamais un message envoyé au client")

    def test_le_complement_revient_au_telephone(self):
        """La boucle, et la raison d'être de tout le dispositif.

        Ce qu'un responsable écrit depuis le CRM doit s'afficher sur le
        téléphone du commercial à la sonnerie suivante.
        """
        self.completer("Litige facturation en cours, ne rien promettre")
        fiche = self.Appel.fiche_contact('+213770112233')
        self.assertIn('Litige facturation en cours', fiche['last_notes'])

    def test_le_complement_est_publie_sans_entete(self):
        """Le Caller ID tronque à 200 caractères.

        Un en-tête « Appel sortant — +213… » en mangerait la moitié pour
        redire ce que le fil affiche déjà à côté du message.
        """
        self.completer("Rappeler jeudi")
        fiche = self.Appel.fiche_contact('+213770112233')
        self.assertEqual(fiche['last_notes'], 'Rappeler jeudi')

    def test_un_appel_non_rattache_refuse_le_complement(self):
        self.poster(ChargeUtile.valide(
            client_event_id='evt-orphelin', phone_number='+213770999000',
        ))
        orphelin = self.Appel.search([('client_event_id', '=', 'evt-orphelin')])
        self.assertFalse(orphelin.partner_id or orphelin.lead_id)
        with self.assertRaises(UserError):
            orphelin.action_completer_note()

    def test_le_complement_respecte_les_droits_du_commercial(self):
        """Publié au nom de l'utilisateur réel, sans `sudo()`.

        Passer en sudo laisserait quelqu'un écrire dans le fil d'une piste
        qu'il n'a pas le droit de voir, par le détour d'un appel.
        """
        self.completer("Trace")
        message = self.env['mail.message'].search(
            [('model', '=', 'res.partner'), ('res_id', '=', self.contact.id)],
            order='id desc', limit=1,
        )
        self.assertEqual(message.author_id, self.env.user.partner_id)

    # ── Le contexte affiché sur l'appel ──────────────────────────────────────

    def test_la_derniere_note_du_client_est_lisible_depuis_l_appel(self):
        self.completer("Préfère être appelé le matin")
        self.appel.invalidate_recordset(['last_note'])
        self.assertIn('Préfère être appelé le matin', self.appel.last_note)

    def test_la_derniere_note_n_est_pas_stockee(self):
        """Le fil grossit après l'appel : une copie figée dirait « dernière
        note » en montrant l'avant-dernière."""
        self.assertFalse(self.Appel._fields['last_note'].store)

    # ── Le chemin vers la fiche ──────────────────────────────────────────────

    def test_l_action_ouvre_la_fiche_du_client(self):
        action = self.appel.action_ouvrir_client()
        self.assertEqual(action['res_model'], 'res.partner')
        self.assertEqual(action['res_id'], self.contact.id)

    def test_l_action_prefere_la_piste_quand_il_y_en_a_une(self):
        piste = self.env['crm.lead'].create({
            'name': 'Affaire enrichie', 'partner_id': self.contact.id,
        })
        self.appel.lead_id = piste
        action = self.appel.action_ouvrir_client()
        self.assertEqual(action['res_model'], 'crm.lead')
        self.assertEqual(action['res_id'], piste.id)
