# -*- coding: utf-8 -*-
from odoo.tests import HttpCase, tagged

from .common import BancCallTracker, ChargeUtile


@tagged('post_install', '-at_install')
class TestNoteTardive(HttpCase, BancCallTracker):
    """La note qui arrive après l'appel qu'elle décrit.

    Le rejeu d'un ``client_event_id`` déjà connu répondait « duplicate » et
    jetait la charge utile sans la lire. C'est juste pour tous les champs sauf
    un : la note arrive légitimement APRÈS. La retenue de deux minutes qui
    laisse le temps de l'écrire est du même ordre de grandeur que le temps
    qu'on met à l'écrire — le commercial qui valide quelques secondes trop
    tard voyait sa note acceptée par le téléphone, affichée dans sa liste, et
    jamais remontée. Silencieusement des deux côtés.
    """

    def setUp(self):
        super().setUp()
        self.appareil = self.creer_appareil()
        self.Appel = self.env['call.tracker.log']
        self.client = self.env['res.partner'].create({
            'name': 'Boulangerie Amine', 'phone': '+213555000000',
        })

    def journaliser(self, identifiant='evt-nt-1', note=None):
        charge = ChargeUtile.valide(client_event_id=identifiant)
        if note is not None:
            charge['note'] = note
        self.poster(charge)
        return self.Appel.search([('client_event_id', '=', identifiant)])

    def messages(self):
        return self.env['mail.message'].search([
            ('model', '=', 'res.partner'), ('res_id', '=', self.client.id),
        ])

    # ── Le cas qui était perdu ───────────────────────────────────────────────

    def test_une_note_arrivee_apres_coup_est_acceptee(self):
        appel = self.journaliser()
        self.assertFalse(appel.note)

        self.journaliser(note="Rappeler lundi, il attend le devis")

        self.assertEqual(appel.note, "Rappeler lundi, il attend le devis")

    def test_le_rejeu_repond_toujours_200(self):
        """Le complément ne doit pas changer le contrat du rejeu.

        L'application doit pouvoir retirer l'événement de sa file : un 4xx la
        ferait réessayer indéfiniment le seul cas où tout va bien.
        """
        self.journaliser()
        reponse = self.poster(ChargeUtile.valide(
            client_event_id='evt-nt-1', note="Une note",
        ))
        self.assertEqual(reponse.status_code, 200)

    def test_la_note_tardive_atteint_le_fil_du_client(self):
        """Sans publication, la note vivrait sur l'appel sans servir à rien.

        Les deux endroits où elle compte sont le fil du client et le Caller ID
        du prochain appel — tous deux alimentés par ``_publier_note``.
        """
        self.journaliser()
        avant = len(self.messages())

        self.journaliser(note="Il change de fournisseur en janvier")

        apres = self.messages()
        self.assertEqual(len(apres) - avant, 1)
        self.assertIn("Il change de fournisseur en janvier", apres[0].body)

    def test_la_note_tardive_revient_au_caller_id(self):
        self.journaliser()
        self.journaliser(note="Demande un rendez-vous sur site")

        fiche = self.Appel.fiche_contact('+213555000000')
        self.assertIn("Demande un rendez-vous sur site", fiche['last_notes'])

    # ── Ce que le complément n'a PAS le droit de faire ───────────────────────

    def test_une_note_existante_n_est_jamais_ecrasee(self):
        """Monotone : le complément ne remplit que le vide.

        C'est ce qui permet de le faire sur un chemin conçu pour être rejoué —
        deux envois concurrents ne peuvent pas se contredire, et un rejeu reste
        sans effet.
        """
        appel = self.journaliser(note="La vraie note, écrite à temps")

        self.journaliser(note="Une seconde version, arrivée trop tard")

        self.assertEqual(appel.note, "La vraie note, écrite à temps")

    def test_un_rejeu_sans_note_n_efface_rien(self):
        appel = self.journaliser(note="À conserver")
        self.journaliser()
        self.assertEqual(appel.note, "À conserver")

    def test_le_rejeu_ne_publie_rien_quand_il_n_ajoute_rien(self):
        """Sans quoi chaque réessai du téléphone gonflerait le fil du client."""
        self.journaliser()
        avant = len(self.messages())
        self.journaliser()
        self.assertEqual(len(self.messages()), avant)

    def test_un_autre_appareil_ne_peut_pas_completer(self):
        """Cadré sur l'appareil qui a remis l'appel.

        Un ``client_event_id`` est un UUID, donc impraticable à deviner — mais
        cadrer coûte une comparaison et évite qu'un jeton quelconque puisse
        écrire dans le fil d'un client au nom d'un autre commercial.
        """
        appel = self.journaliser()

        autre_jeton = 'jeton-intrus-bbbbbbbbbbbbbbbbbbbbbbbbbbbb'
        self.creer_appareil(jeton=autre_jeton)
        self.poster(
            ChargeUtile.valide(client_event_id='evt-nt-1', note="Injectée"),
            jeton=autre_jeton,
        )

        self.assertFalse(appel.note)
        self.assertTrue(self.env['call.tracker.audit'].search([
            ('result', '=', 'forbidden'),
        ]), "la tentative doit laisser une trace : elle ne devrait jamais arriver")
