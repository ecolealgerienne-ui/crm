# -*- coding: utf-8 -*-
from markupsafe import Markup

from odoo.tests import HttpCase, tagged

from .common import BancCallTracker

CHAMPS_AUTORISES = {'status', 'name', 'company', 'last_notes', 'crm_stage'}


@tagged('post_install', '-at_install')
class TestContact(HttpCase, BancCallTracker):
    """Route de lecture du Caller ID.

    L'enjeu de ces tests n'est pas qu'elle réponde, c'est qu'elle ne réponde
    QUE les quatre champs prévus. Le contrôleur travaille en ``sudo()`` : il a
    accès à tout le contact, et rien dans les droits d'Odoo ne l'empêchera d'en
    laisser fuir.
    """

    def setUp(self):
        super().setUp()
        self.creer_appareil()
        self.contact = self.env['res.partner'].create({
            'name': 'Ahmed Benali',
            'phone': '05 55 12 34 56',
            'email': 'ahmed.benali@exemple.dz',
            'street': '12 rue des Frères Bouadou',
            'city': 'Djelfa',
            'company_name': 'Marché Central',
        })

    def lire(self, numero, jeton=BancCallTracker.JETON):
        entetes = {'Authorization': f'Bearer {jeton}'} if jeton else {}
        return self.url_open(f'/call_tracker/contact/{numero}', headers=entetes)

    # ── Cas nominal ──────────────────────────────────────────────────────────

    def test_contact_trouve(self):
        reponse = self.lire('+213555123456')
        self.assertEqual(reponse.status_code, 200)
        corps = reponse.json()
        self.assertEqual(corps['status'], 'found')
        self.assertEqual(corps['name'], 'Ahmed Benali')
        self.assertEqual(corps['company'], 'Marché Central')

    def test_numero_trouve_quel_que_soit_son_format(self):
        for ecriture in ('+213555123456', '0555123456', '00213555123456'):
            with self.subTest(numero=ecriture):
                self.assertEqual(self.lire(ecriture).json()['name'], 'Ahmed Benali')

    def test_etape_crm_remontee(self):
        piste = self.env['crm.lead'].create({
            'name': 'Réassort mensuel', 'partner_id': self.contact.id,
        })
        corps = self.lire('+213555123456').json()
        self.assertEqual(corps['crm_stage'], piste.stage_id.name)

    def test_derniere_note_remontee_en_texte_brut(self):
        piste = self.env['crm.lead'].create({
            'name': 'Réassort', 'partner_id': self.contact.id,
        })
        # ⚠️ `Markup` et pas une chaîne simple. `message_post` ÉCHAPPE une
        # chaîne : `'<p>Bonjour</p>'` est stocké comme le texte littéral
        # « <p>Bonjour</p> », pas comme du HTML. C'est une protection contre
        # l'injection, et elle rend ce test faux si on l'ignore — il vérifiait
        # alors que la conversion HTML échoue sur du texte qui n'était pas du
        # HTML.
        piste.message_post(
            body=Markup('<p>Relance prévue <b>vendredi</b></p>'),
            message_type='comment',
        )
        corps = self.lire('+213555123456').json()
        self.assertIn('Relance prévue', corps['last_notes'])
        self.assertNotIn('<b>', corps['last_notes'], 'le HTML doit être converti')

    def test_note_tronquee(self):
        piste = self.env['crm.lead'].create({
            'name': 'Bavard', 'partner_id': self.contact.id,
        })
        piste.message_post(
            body=Markup('<p>' + ('x' * 500) + '</p>'), message_type='comment'
        )
        self.assertLessEqual(len(self.lire('+213555123456').json()['last_notes']), 200)

    def test_les_notifications_automatiques_ne_sont_pas_des_notes(self):
        """Un changement d'étape ou un courriel envoyé remplit le fil de
        messages ``notification``. Les afficher noierait la vraie note sous du
        bruit à chaque sonnerie."""
        piste = self.env['crm.lead'].create({
            'name': 'Suivi', 'partner_id': self.contact.id,
        })
        piste.message_post(body=Markup('<p>Vraie note</p>'), message_type='comment')
        piste.message_post(
            body=Markup('<p>Étape modifiée</p>'), message_type='notification'
        )
        self.assertIn('Vraie note', self.lire('+213555123456').json()['last_notes'])

    # ── Ce qui ne doit JAMAIS sortir ─────────────────────────────────────────

    def test_aucun_champ_hors_liste_blanche(self):
        corps = self.lire('+213555123456').json()
        self.assertEqual(
            set(corps) - CHAMPS_AUTORISES, set(),
            'un champ non prévu est sorti du CRM',
        )

    def test_ni_courriel_ni_adresse_dans_la_reponse(self):
        # Vérification sur le corps BRUT : un champ pourrait fuir sous un autre
        # nom que celui de l'ORM, et une comparaison de clés ne le verrait pas.
        brut = self.lire('+213555123456').text
        for interdit in ('ahmed.benali@exemple.dz', 'Bouadou', 'Djelfa'):
            self.assertNotIn(interdit, brut, f'« {interdit} » ne doit pas sortir')

    # ── Numéros sans correspondance ──────────────────────────────────────────

    def test_numero_inconnu(self):
        reponse = self.lire('+213555999888')
        self.assertEqual(reponse.status_code, 404)
        self.assertEqual(reponse.json()['status'], 'not_found')

    def test_numero_trop_court(self):
        # Pas de rattachement au hasard sur trois chiffres.
        self.assertEqual(self.lire('123').status_code, 404)

    def test_contact_archive_invisible(self):
        self.contact.active = False
        self.assertEqual(self.lire('+213555123456').status_code, 404)

    # ── Authentification ─────────────────────────────────────────────────────

    def test_sans_jeton(self):
        self.assertEqual(self.lire('+213555123456', jeton=None).status_code, 401)

    def test_jeton_invalide(self):
        self.assertEqual(self.lire('+213555123456', jeton='faux').status_code, 401)

    def test_appareil_revoque(self):
        self.env['call.tracker.device'].search([]).write({'active': False})
        self.assertEqual(self.lire('+213555123456').status_code, 401)

    def test_401_ne_revele_pas_l_existence_du_contact(self):
        """Un jeton invalide doit répondre pareil pour un numéro connu et pour
        un inconnu — sinon la route devient un oracle qui dit qui est au CRM."""
        connu = self.lire('+213555123456', jeton='faux')
        inconnu = self.lire('+213555999888', jeton='faux')
        self.assertEqual(connu.status_code, inconnu.status_code)
        self.assertEqual(connu.json(), inconnu.json())
