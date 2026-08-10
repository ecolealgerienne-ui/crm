# -*- coding: utf-8 -*-
from odoo.tests import HttpCase, tagged

from .common import CHEMIN, BancCallTracker, ChargeUtile


@tagged('post_install', '-at_install')
class TestTelemetrieAppareil(HttpCase, BancCallTracker):
    """Ce que l'appareil déclare de lui-même, et à quoi ça sert.

    `docs/REPORTING_KPI.md` fait de la mesure du délai de remise le préalable
    à tout classement entre commerciaux : un téléphone qui remonte avec six
    heures de retard ferait comparer des réglages de batterie, pas des gens.
    Encore faut-il pouvoir rapporter ce délai **par modèle** — ce qui suppose
    de savoir quel modèle a passé l'appel.
    """

    def setUp(self):
        super().setUp()
        self.appareil = self.creer_appareil()
        self.Appel = self.env['call.tracker.log']

    def poster_avec_entetes(self, identifiant, modele=None, os=None):
        import json
        entetes = {
            'Content-Type': 'application/json',
            'Authorization': 'Bearer %s' % self.JETON,
        }
        if modele:
            entetes['X-Device-Model'] = modele
        if os:
            entetes['X-Device-Os'] = os
        self.url_open(
            CHEMIN,
            data=json.dumps(ChargeUtile.valide(client_event_id=identifiant)),
            headers=entetes,
        )
        return self.Appel.search([('client_event_id', '=', identifiant)])

    # ── Ce qui remonte ───────────────────────────────────────────────────────

    def test_le_modele_est_releve_sur_l_appareil(self):
        self.poster_avec_entetes('evt-tel-1', 'OnePlus GM1913', 'Android 12')
        self.assertEqual(self.appareil.device_model, 'OnePlus GM1913')
        self.assertEqual(self.appareil.os_version, 'Android 12')

    def test_le_modele_est_fige_sur_l_appel(self):
        """Fixé à la création, pas un champ related.

        Un related, même stocké, serait réécrit le jour où le commercial
        change de téléphone — et toute la distribution des délais passés
        basculerait rétroactivement sur le nouveau modèle, effaçant justement
        ce qu'on cherchait à mesurer.
        """
        appel = self.poster_avec_entetes('evt-tel-2', 'Samsung SM-A536B')
        self.assertEqual(appel.device_model, 'Samsung SM-A536B')

        self.poster_avec_entetes('evt-tel-3', 'Xiaomi 2201123G')

        self.assertEqual(self.appareil.device_model, 'Xiaomi 2201123G')
        self.assertEqual(
            appel.device_model, 'Samsung SM-A536B',
            "l'appel garde le modèle qu'il avait au moment où il a eu lieu",
        )

    def test_le_tout_premier_appel_porte_deja_le_modele(self):
        """L'appareil est noté AVANT la création de l'appel.

        Le noter après laisserait sans modèle le premier appel de chaque
        téléphone — soit exactement celui qu'on découvre.
        """
        self.assertFalse(self.appareil.device_model)
        appel = self.poster_avec_entetes('evt-tel-4', 'OnePlus GM1913')
        self.assertEqual(appel.device_model, 'OnePlus GM1913')

    # ── Ce qui ne casse pas ──────────────────────────────────────────────────

    def test_une_application_qui_n_annonce_rien_fonctionne(self):
        """Compatibilité ascendante : les en-têtes sont facultatifs.

        C'est la raison d'être du choix des en-têtes plutôt que de la charge
        utile — celle-ci a une liste blanche stricte, et y ajouter des clés
        ferait échouer l'envoi de TOUS les appels d'une version antérieure.
        """
        appel = self.poster_avec_entetes('evt-tel-5')
        self.assertTrue(appel, "l'appel doit être journalisé quand même")
        self.assertFalse(appel.device_model)

    def test_une_annonce_trop_longue_est_tronquee(self):
        appel = self.poster_avec_entetes('evt-tel-6', 'X' * 200)
        self.assertLessEqual(len(self.appareil.device_model), 64)
        self.assertTrue(appel)

    # ── Ce que ça permet ─────────────────────────────────────────────────────

    def test_le_delai_de_remise_se_rapporte_par_modele(self):
        """La question à laquelle tout ce chantier sert à répondre."""
        self.poster_avec_entetes('evt-tel-7', 'OnePlus GM1913')
        self.poster_avec_entetes('evt-tel-8', 'Samsung SM-A536B')

        groupes = self.Appel._read_group(
            [('device_model', '!=', False)],
            groupby=['device_model'],
            aggregates=['delivery_lag_minutes:avg'],
        )
        modeles = {modele for modele, _moyenne in groupes}
        self.assertIn('OnePlus GM1913', modeles)
        self.assertIn('Samsung SM-A536B', modeles)
