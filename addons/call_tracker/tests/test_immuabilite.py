# -*- coding: utf-8 -*-
from odoo.exceptions import AccessError, UserError
from odoo.tests import TransactionCase, new_test_user, tagged


@tagged('post_install', '-at_install')
class TestImmuabiliteDeLAppel(TransactionCase):
    """Un appel journalisé est un compte rendu : il ne se réécrit pas.

    Tout le dispositif repose là-dessus. Le commercial est mesuré sur ces
    lignes ; s'il peut les corriger après coup, la mesure ne vaut rien et le
    journal d'audit non plus — il tracerait fidèlement des consultations de
    données falsifiables.

    Le principe était écrit partout dans la documentation et n'était vérifié
    nulle part. `readonly=True` sur un champ est une consigne d'INTERFACE : le
    client web ne l'envoie pas, mais l'ORM l'accepte, et un appel RPC direct
    passe. C'est exactement le genre d'écart qu'un test doit figer plutôt
    qu'une docstring.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.commercial = new_test_user(
            cls.env, login='ct_immuable',
            groups='sales_team.group_sale_salesman',
        )
        cls.responsable = new_test_user(
            cls.env, login='ct_immuable_chef',
            groups='sales_team.group_sale_manager',
        )
        cls.appareil = cls.env['call.tracker.device'].create({
            'name': 'Appareil immuabilité', 'user_id': cls.commercial.id,
        })
        cls.Appel = cls.env['call.tracker.log']

    def journaliser(self, **valeurs):
        base = {
            'client_event_id': 'evt-imm-1',
            'phone_number': '+213555777888',
            'direction': 'outbound',
            'duration_seconds': 30,
            'started_at': '2026-08-09 14:32:00',
            'device_id': self.appareil.id,
            'user_id': self.commercial.id,
        }
        base.update(valeurs)
        return self.Appel.create(base)

    # ── Ce qu'un commercial ne doit pas pouvoir réécrire ─────────────────────

    def test_un_commercial_ne_peut_pas_rallonger_un_appel(self):
        """Le cas qui vide le pilotage de son sens.

        La durée est la mesure par défaut du tableau de bord, choisie parce
        que « dix appels de cinq secondes ne valent pas dix conversations ».
        Si le mesuré peut l'écrire, il n'y a plus rien à mesurer.
        """
        appel = self.journaliser()
        with self.assertRaises(UserError):
            appel.with_user(self.commercial).duration_seconds = 3600
        self.assertEqual(appel.duration_seconds, 30)

    def test_un_commercial_ne_peut_pas_changer_le_numero(self):
        """Réécrire le numéro déplacerait l'appel sur la fiche d'un autre
        client — et la note publiée dans le fil resterait, elle, à sa place."""
        appel = self.journaliser()
        with self.assertRaises(UserError):
            appel.with_user(self.commercial).phone_number = '+213555000111'

    def test_un_commercial_ne_peut_pas_deplacer_un_appel_dans_le_temps(self):
        """`started_at` porte la rétention ET le délai de remise : le décaler
        change à la fois la date d'effacement et la mesure du retard."""
        appel = self.journaliser()
        with self.assertRaises(UserError):
            appel.with_user(self.commercial).started_at = '2026-01-01 08:00:00'

    def test_un_commercial_ne_peut_pas_s_attribuer_l_appel_d_un_autre(self):
        appel = self.journaliser()
        with self.assertRaises(UserError):
            appel.with_user(self.commercial).user_id = self.responsable.id

    def test_le_responsable_non_plus(self):
        """L'immuabilité ne dépend pas du droit d'accès.

        Un responsable peut voir tous les appels et en supprimer ; il ne peut
        pas en modifier un. Supprimer laisse un trou visible, réécrire laisse
        une ligne plausible — c'est la différence qui compte ici.
        """
        appel = self.journaliser()
        with self.assertRaises(UserError):
            appel.with_user(self.responsable).duration_seconds = 3600

    def test_le_message_dit_quoi_faire(self):
        appel = self.journaliser()
        with self.assertRaises(UserError) as erreur:
            appel.with_user(self.commercial).duration_seconds = 3600
        self.assertIn('note', str(erreur.exception).lower())

    # ── Ce qui reste ouvert, et qui doit le rester ───────────────────────────

    def test_la_qualification_reste_possible(self):
        """Rattacher un appel à un client n'est pas le réécrire.

        C'est une interprétation qu'on ajoute par-dessus le fait, pas une
        correction du fait. Fermer cette porte enlèverait sa raison d'être à
        la file « Appels à qualifier ».
        """
        appel = self.journaliser(client_event_id='evt-imm-2')
        client = self.env['res.partner'].create({'name': 'Client test'})

        appel.with_user(self.responsable).partner_id = client.id

        self.assertEqual(appel.partner_id, client)

    def test_la_note_peut_encore_etre_completee_par_le_serveur(self):
        """Le complément tardif passe par `sudo()` depuis le contrôleur.

        Il ne doit pas être emporté par le verrou : la note arrive
        légitimement après l'appel qu'elle décrit.
        """
        appel = self.journaliser(client_event_id='evt-imm-3')
        client = self.env['res.partner'].create({
            'name': 'Client note', 'phone': '+213555777888',
        })
        appel.partner_id = client

        self.assertTrue(appel.completer_note("Arrivée après coup"))
        self.assertEqual(appel.note, "Arrivée après coup")

    def test_un_appel_reste_supprimable_par_le_responsable(self):
        """La purge et le droit à l'effacement passent par là."""
        appel = self.journaliser(client_event_id='evt-imm-4')
        appel.with_user(self.responsable).unlink()
        self.assertFalse(appel.exists())

    def test_un_commercial_ne_peut_pas_supprimer_ses_appels(self):
        appel = self.journaliser(client_event_id='evt-imm-5')
        with self.assertRaises(AccessError):
            appel.with_user(self.commercial).unlink()
