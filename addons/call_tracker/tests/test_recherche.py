# -*- coding: utf-8 -*-
from odoo.tests import HttpCase, tagged

from .common import BancCallTracker


@tagged('post_install', '-at_install')
class TestRechercheContacts(HttpCase, BancCallTracker):
    """Recherche de contacts par fragment de numéro.

    La route la plus sensible du module : elle interroge le carnet d'adresses
    à partir d'un bout de numéro, avec pour seule authentification un jeton
    d'appareil. Ces tests portent autant sur ce qu'elle rend que sur ce
    qu'elle refuse.
    """

    def setUp(self):
        super().setUp()
        self.appareil = self.creer_appareil()
        self.Appel = self.env['call.tracker.log']
        self.societe = self.env['res.partner'].create({
            'name': 'Sonatrach Distribution', 'is_company': True,
        })
        self.contact = self.env['res.partner'].create({
            'name': 'Yacine Amrani',
            'parent_id': self.societe.id,
            'phone': '+213 661 44 55 66',
        })
        self.autre = self.env['res.partner'].create({
            'name': 'Leïla Hamidi', 'phone': '0661445599',
        })

    def chercher(self, fragment):
        return self.url_open(
            '/call_tracker/contacts/%s' % fragment,
            headers={'Authorization': 'Bearer %s' % self.JETON},
        )

    # ── Ce qu'elle rend ──────────────────────────────────────────────────────

    def test_un_fragment_du_milieu_retrouve_le_contact(self):
        """Un commercial se souvient d'un morceau, rarement de la fin exacte."""
        reponse = self.chercher('4455')
        self.assertEqual(reponse.status_code, 200)
        corps = reponse.json()
        self.assertEqual(corps['status'], 'found')
        noms = [r['name'] for r in corps['results']]
        self.assertIn('Yacine Amrani', noms)
        self.assertIn('Leïla Hamidi', noms)

    def test_la_mise_en_forme_de_la_fiche_est_ignoree(self):
        # La fiche porte « +213 661 44 55 66 » avec des espaces ; la recherche
        # se fait sur les chiffres seuls, des deux côtés.
        for fragment in ('66144', '661 44', '661-44'):
            resultats = self.chercher(fragment).json()['results']
            self.assertIn('Yacine Amrani', [r['name'] for r in resultats],
                          "fragment %r" % fragment)

    def test_le_numero_fait_partie_du_resultat(self):
        """Sans lui la liste est inutilisable : on ne sait ni lequel choisir,
        ni quoi composer en tapant dessus."""
        resultats = self.chercher('445566').json()['results']
        self.assertTrue(resultats)
        self.assertTrue(all(r['phone'] for r in resultats))

    def test_la_societe_accompagne_le_nom(self):
        resultats = self.chercher('445566').json()['results']
        fiche = next(r for r in resultats if r['name'] == 'Yacine Amrani')
        self.assertEqual(fiche['company'], 'Sonatrach Distribution')

    def test_aucun_resultat_se_dit_sans_erreur(self):
        reponse = self.chercher('999888777')
        self.assertEqual(reponse.status_code, 200)
        self.assertEqual(reponse.json()['status'], 'not_found')
        self.assertEqual(reponse.json()['results'], [])

    # ── Ce qu'elle refuse ────────────────────────────────────────────────────

    def test_un_fragment_trop_court_est_refuse(self):
        """Sans minimum, « 0 » rendrait un échantillon de tout le carnet.

        400 et non une liste vide : « trop court » et « aucun résultat »
        appellent deux messages différents à l'écran, et l'app ne peut pas les
        distinguer si le serveur répond la même chose.
        """
        reponse = self.chercher('661')
        self.assertEqual(reponse.status_code, 400)
        self.assertEqual(reponse.json()['status'], 'too_short')
        self.assertEqual(reponse.json()['min_digits'], self.Appel.FRAGMENT_MIN)

    def test_le_nombre_de_resultats_est_plafonne(self):
        """Un téléphone perdu ne doit pas vider le carnet en quelques requêtes."""
        for i in range(self.Appel.RESULTATS_MAX + 5):
            self.env['res.partner'].create({
                'name': 'Masse %d' % i, 'phone': '+2137770000%02d' % i,
            })
        resultats = self.chercher('7770000').json()['results']
        self.assertEqual(len(resultats), self.Appel.RESULTATS_MAX)

    def test_sans_jeton_rien_ne_sort(self):
        reponse = self.url_open('/call_tracker/contacts/445566')
        self.assertEqual(reponse.status_code, 401)
        self.assertNotIn('results', reponse.json())

    # ── Ce qu'elle laisse comme trace ────────────────────────────────────────

    def test_chaque_recherche_est_journalisee_avec_son_compte(self):
        """Une énumération se reconnaît à sa forme : des recherches courtes en
        rafale, chacune rendant le maximum. Sans le nombre de résultats, la
        trace ne dit pas si le carnet a été effleuré ou vidé.
        """
        self.chercher('445566')
        trace = self.env['call.tracker.audit'].search(
            [('action', '=', 'contact_search')], order='id desc', limit=1,
        )
        self.assertTrue(trace)
        self.assertEqual(trace.result, 'ok')
        self.assertEqual(trace.phone_number, '445566')
        self.assertIn('resultat', trace.detail)

    def test_un_fragment_trop_court_laisse_une_trace(self):
        """C'est LE cas où la trace compte le plus.

        Sonder le carnet à coups de fragments courts est exactement ce que la
        borne refuse ; si le refus ne laissait rien, l'audit ne verrait qu'un
        silence là où il y a une tentative. Le défaut a existé : `too_short`
        n'appartenait pas à la sélection du champ `result`, et l'écriture
        échouait — sans bruit, parce que `tracer()` avale tout par conception.
        """
        self.chercher('661')
        trace = self.env['call.tracker.audit'].search(
            [('action', '=', 'contact_search')], order='id desc', limit=1,
        )
        self.assertTrue(trace, "un refus doit laisser une trace")
        self.assertEqual(trace.result, 'too_short')

    def test_un_refus_laisse_aussi_une_trace(self):
        avant = self.env['call.tracker.audit'].search_count([])
        self.url_open('/call_tracker/contacts/445566')
        self.assertGreater(self.env['call.tracker.audit'].search_count([]), avant)

    # ── Les prospects qui n'ont pas encore de fiche contact ──────────────────

    def test_une_piste_sans_contact_est_trouvee(self):
        """Le trou constaté en rejouant les scénarios le 2026-08-10.

        Qualifier un appel d'un numéro inconnu crée une PISTE, pas un contact.
        La fiche à la sonnerie la trouvait, la recherche par fragment non :
        elle n'interrogeait que `res.partner`. Le commercial venait de
        qualifier un prospect et ne pouvait plus le retrouver pour le
        rappeler.
        """
        self.env['crm.lead'].create({
            'name': 'Entrant — +213555909090',
            'phone': '+213555909090',
        })
        noms = [r['name'] for r in self.chercher('909090').json()['results']]
        self.assertIn('Entrant — +213555909090', noms)

    def test_les_deux_routes_s_accordent_sur_un_meme_numero(self):
        """L'incohérence est ce qui se remarque, plus que l'absence.

        Un numéro que la sonnerie sait nommer et que la recherche ignore se
        lit comme une panne intermittente.
        """
        self.env['crm.lead'].create({
            'name': 'Prospect accordé', 'phone': '+213555818181',
        })
        fiche = self.Appel.fiche_contact('+213555818181')
        liste = self.chercher('818181').json()

        self.assertTrue(fiche, "la fiche à la sonnerie doit le trouver")
        self.assertEqual(liste['count'], 1, "la recherche aussi")

    def test_une_piste_rattachee_n_apparait_pas_deux_fois(self):
        """Elle remonte déjà par son contact ; l'ajouter afficherait la même
        personne sous deux intitulés."""
        contact = self.env['res.partner'].create({
            'name': 'Client avec affaire', 'phone': '+213555727272',
        })
        self.env['crm.lead'].create({
            'name': 'Affaire du client', 'partner_id': contact.id,
            'phone': '+213555727272',
        })
        resultats = self.chercher('727272').json()['results']
        self.assertEqual(len(resultats), 1)
        self.assertEqual(resultats[0]['name'], 'Client avec affaire')

    def test_le_numero_de_la_piste_accompagne_le_resultat(self):
        self.env['crm.lead'].create({
            'name': 'Prospect à rappeler', 'phone': '+213555636363',
        })
        fiche = self.chercher('636363').json()['results'][0]
        self.assertTrue(fiche['phone'], "sans numéro, impossible d'appeler")

    def test_le_plafond_couvre_les_deux_sources(self):
        """Le cap borne le TOTAL, pas chaque source : sinon un jeton volé
        récolterait deux fois plus par requête."""
        for i in range(self.Appel.RESULTATS_MAX + 3):
            self.env['res.partner'].create({
                'name': 'Contact %d' % i, 'phone': '+2135554400%02d' % i,
            })
        for i in range(5):
            self.env['crm.lead'].create({
                'name': 'Piste %d' % i, 'phone': '+2135554401%02d' % i,
            })
        resultats = self.chercher('55544').json()['results']
        self.assertLessEqual(len(resultats), self.Appel.RESULTATS_MAX)
