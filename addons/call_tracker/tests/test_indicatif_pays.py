# -*- coding: utf-8 -*-
from odoo.tests import HttpCase, TransactionCase, tagged

from odoo.addons.call_tracker.models.call_tracker_log import (
    chiffres_significatifs, est_international, pays_incompatibles,
)

from .common import BancCallTracker, ChargeUtile


@tagged('post_install', '-at_install')
class TestIndicatifPays(TransactionCase):
    """Le garde-fou par indicatif pays, à l'unité.

    La clé de rapprochement ne retient que les 9 derniers chiffres, et deux
    pays peuvent la partager. Ces tests figent la frontière : quand le
    garde-fou mord, et surtout quand il ne doit pas mordre.
    """

    def test_la_collision_de_cles_est_reelle(self):
        """Le point de départ, reproduit noir sur blanc.

        Si ce test venait à échouer, c'est que la clé aurait changé — et tout
        le reste de ce fichier n'aurait plus d'objet.
        """
        self.assertEqual(chiffres_significatifs('+213 555 12 34 56'), '555123456')
        self.assertEqual(chiffres_significatifs('+971 55 512 3456'), '555123456')

    def test_deux_pays_differents_sont_incompatibles(self):
        self.assertTrue(pays_incompatibles('+213555123456', '+971555123456'))

    def test_le_meme_numero_ecrit_autrement_reste_compatible(self):
        """`00213…` et `+213…` désignent le même correspondant."""
        for autre in ('+213555123456', '00213555123456', '+213 555 12 34 56'):
            self.assertFalse(pays_incompatibles('+213555123456', autre), autre)

    def test_un_numero_national_ne_declenche_jamais_le_garde_fou(self):
        """LE cas à ne pas casser.

        C'est celui qui a imposé les 9 chiffres : une fiche saisie en
        `0555123456` doit retrouver un `+213555123456` reçu du téléphone. Dès
        qu'un des deux numéros est national, on ne sait pas de quel pays il
        vient — donc on ne refuse rien.
        """
        self.assertFalse(pays_incompatibles('+213555123456', '0555123456'))
        self.assertFalse(pays_incompatibles('0555123456', '+971555123456'))
        self.assertFalse(pays_incompatibles('0555123456', '0555123456'))

    def test_est_international_reconnait_les_deux_ecritures(self):
        self.assertTrue(est_international('+213555123456'))
        self.assertTrue(est_international('00213555123456'))
        self.assertFalse(est_international('0555123456'))
        self.assertFalse(est_international(''))


@tagged('post_install', '-at_install')
class TestRapprochementEntrePays(HttpCase, BancCallTracker):
    """Le garde-fou en situation, sur un appel réellement journalisé."""

    def setUp(self):
        super().setUp()
        self.appareil = self.creer_appareil()
        self.Appel = self.env['call.tracker.log']
        self.algerien = self.env['res.partner'].create({
            'name': 'Client algérien', 'phone': '+213555123456',
        })

    def journaliser(self, numero, identifiant):
        self.poster(ChargeUtile.valide(
            client_event_id=identifiant, phone_number=numero,
        ))
        return self.Appel.search([('client_event_id', '=', identifiant)])

    def test_un_appel_etranger_ne_se_rattache_pas_au_client_algerien(self):
        """Le défaut que ce chantier ferme.

        Les deux numéros partagent les 9 derniers chiffres. Sans le garde-fou,
        cet appel se rattachait au client algérien — et publiait une note dans
        son fil. Silencieusement : rien à l'écran ne distingue un rattachement
        juste d'un rattachement faux.
        """
        appel = self.journaliser('+971555123456', 'evt-pays-1')
        self.assertFalse(
            appel.partner_id,
            "un numéro de Dubaï ne doit pas désigner un client algérien",
        )

    def test_le_meme_client_reste_rattache(self):
        appel = self.journaliser('+213555123456', 'evt-pays-2')
        self.assertEqual(appel.partner_id, self.algerien)

    def test_un_appel_national_reste_rattache(self):
        """Non-régression sur le cas d'origine : le téléphone remonte souvent
        un numéro national là où la fiche porte l'indicatif."""
        appel = self.journaliser('0555123456', 'evt-pays-3')
        self.assertEqual(appel.partner_id, self.algerien)

    def test_une_fiche_nationale_est_retrouvee_par_un_appel_international(self):
        national = self.env['res.partner'].create({
            'name': 'Fiche sans indicatif', 'phone': '0661778899',
        })
        appel = self.journaliser('+213661778899', 'evt-pays-4')
        self.assertEqual(appel.partner_id, national)

    def test_le_bon_client_est_choisi_parmi_deux_homonymes_de_cle(self):
        """Le cas qui prouve qu'on filtre au lieu de prendre le premier venu.

        Deux fiches partagent la clé ; seule celle du bon pays doit sortir, et
        elle n'est pas la première par identifiant.
        """
        emirati = self.env['res.partner'].create({
            'name': 'Client émirati', 'phone': '+971555123456',
        })
        self.assertGreater(emirati.id, self.algerien.id)

        appel = self.journaliser('+971555123456', 'evt-pays-5')
        self.assertEqual(appel.partner_id, emirati)

    def test_la_fiche_a_la_sonnerie_applique_le_meme_filtre(self):
        """Les deux routes de lecture doivent s'accorder : afficher le client
        algérien pendant qu'un émirati appelle serait pire qu'afficher
        « inconnu »."""
        fiche = self.Appel.fiche_contact('+971555123456')
        self.assertFalse(
            fiche and fiche.get('name') == 'Client algérien',
            "la fiche à la sonnerie ne doit pas nommer le client d'un autre pays",
        )
