# -*- coding: utf-8 -*-
from datetime import date, timedelta

from odoo.tests import HttpCase, new_test_user, tagged

from .common import BancCallTracker


@tagged('post_install', '-at_install')
class TestActivitesAAppeler(HttpCase, BancCallTracker):
    """Les appels programmés dans le CRM, rendus au commercial sur son téléphone.

    La seule route qui donne au lieu de prendre. Tout le reste du dispositif
    est rétrospectif ; celle-ci est la raison d'ouvrir l'application — et donc,
    indirectement, ce qui fait que la file d'envoi se vide.
    """

    def setUp(self):
        super().setUp()
        self.appareil = self.creer_appareil()
        self.Appel = self.env['call.tracker.log']
        self.mien = self.appareil.user_id
        self.collegue = new_test_user(
            self.env, login='activites_collegue',
            groups='sales_team.group_sale_salesman',
        )
        self.type_appel = self.env['mail.activity.type'].search(
            [('category', '=', 'phonecall')], limit=1,
        )
        self.assertTrue(self.type_appel, "aucun type d'activité téléphonique")

        self.client = self.env['res.partner'].create({
            'name': 'Client à rappeler', 'phone': '+213661550011',
        })
        self.piste = self.env['crm.lead'].create({
            'name': 'Affaire à relancer', 'partner_id': self.client.id,
        })

    def programmer(self, quand, commercial=None, sur=None, resume="Rappeler"):
        cible = sur or self.piste
        return self.env['mail.activity'].create({
            'activity_type_id': self.type_appel.id,
            'res_model_id': self.env['ir.model']._get_id(cible._name),
            'res_id': cible.id,
            'user_id': (commercial or self.mien).id,
            'date_deadline': quand,
            'summary': resume,
        })

    def lister(self):
        return self.url_open(
            '/call_tracker/activities',
            headers={'Authorization': 'Bearer %s' % self.JETON},
        ).json()

    def mes_lignes(self):
        """Indexées par résumé.

        ⚠️ Ne jamais prendre `results[0]` : la base de démonstration porte déjà
        des activités « Call » assignées au même utilisateur, et elles passent
        devant selon leur échéance. Un test qui lit le premier résultat
        vérifie alors la donnée d'Odoo, pas la nôtre — et passe ou échoue au
        gré des jeux de démonstration.
        """
        return {r['summary']: r for r in self.lister().get('results', [])}

    # ── Ce que la liste contient ─────────────────────────────────────────────

    def test_mes_appels_programmes_remontent(self):
        self.programmer(date.today())
        self.assertEqual(self.lister()['status'], 'found')
        self.assertIn('Rappeler', self.mes_lignes())

    def test_le_numero_accompagne_l_activite(self):
        """Sans lui, la liste dit quoi faire sans permettre de le faire."""
        self.programmer(date.today(), resume="Avec numero")
        self.assertEqual(self.mes_lignes()["Avec numero"]['phone'], '+213661550011')

    def test_le_numero_suit_une_activite_posee_sur_le_contact(self):
        # Une activité ne vit pas toujours sur une piste : elle peut être
        # posée directement sur la fiche client. Le numéro doit se trouver
        # dans les deux cas.
        self.programmer(date.today(), sur=self.client, resume="Sur la fiche")
        self.assertEqual(
            self.mes_lignes()["Sur la fiche"]['phone'], '+213661550011',
        )

    def test_une_activite_sans_numero_reste_affichee(self):
        """La masquer ferait perdre une tâche réelle pour un champ manquant."""
        muette = self.env['crm.lead'].create({'name': 'Piste sans numéro'})
        self.programmer(date.today(), sur=muette, resume="Trouver le numéro")

        lignes = self.mes_lignes()
        self.assertIn("Trouver le numéro", lignes)
        self.assertEqual(lignes["Trouver le numéro"]['phone'], '')

    def test_le_retard_passe_devant(self):
        self.programmer(date.today() + timedelta(days=3), resume="Plus tard")
        self.programmer(date.today() - timedelta(days=2), resume="En retard")
        self.programmer(date.today(), resume="Aujourd'hui")

        # Filtré sur MES trois activités : la base de démonstration en porte
        # d'autres, qui s'intercalent selon leur propre échéance.
        miennes = ["En retard", "Aujourd'hui", "Plus tard"]
        ordre = [r['summary'] for r in self.lister()['results']
                 if r['summary'] in miennes]
        self.assertEqual(ordre, miennes)

    def test_l_etat_est_celui_calcule_par_odoo(self):
        """Le recalculer côté téléphone donnerait deux vérités pour la même
        échéance — et elles divergeraient au changement de fuseau."""
        self.programmer(date.today() - timedelta(days=1), resume="Hier")
        self.assertEqual(self.mes_lignes()["Hier"]['state'], 'overdue')

    # ── Ce qu'elle ne contient pas ───────────────────────────────────────────

    def test_les_activites_du_collegue_ne_remontent_pas(self):
        """Le cloisonnement est dans la donnée : une activité est assignée.

        Contrairement à la recherche de contacts, il n'y a rien à régler ici.
        """
        self.programmer(date.today(), commercial=self.collegue, resume="Pas à moi")
        self.assertNotIn("Pas à moi", self.mes_lignes())

    def test_les_autres_types_d_activite_sont_ecartes(self):
        courriel = self.env['mail.activity.type'].search(
            [('category', '!=', 'phonecall')], limit=1,
        )
        self.env['mail.activity'].create({
            'activity_type_id': courriel.id,
            'res_model_id': self.env['ir.model']._get_id('crm.lead'),
            'res_id': self.piste.id,
            'user_id': self.mien.id,
            'date_deadline': date.today(),
            'summary': "Envoyer le devis",
        })
        self.assertNotIn("Envoyer le devis", self.mes_lignes())

    def test_le_filtre_porte_sur_la_categorie_pas_sur_le_nom(self):
        """« Call » est un libellé : il se traduit et se renomme. Une instance
        en français l'appellera « Appel », et un filtre sur le nom rendrait
        alors une liste vide sans que rien ne le signale."""
        self.type_appel.name = "Coup de fil"
        self.programmer(date.today(), resume="Toujours là")
        self.assertIn("Toujours là", self.mes_lignes())

    def test_sans_jeton_rien_ne_sort(self):
        self.programmer(date.today())
        reponse = self.url_open('/call_tracker/activities')
        self.assertEqual(reponse.status_code, 401)
        self.assertNotIn('results', reponse.json())

    # ── La clôture ───────────────────────────────────────────────────────────

    def cloturer(self, identifiant, jeton=None):
        return self.url_open(
            '/call_tracker/activity/%d/done' % identifiant,
            # ⚠️ Corps non vide obligatoire : `url_open` bascule en GET quand
            # `data` est vide, et la route POST répond alors 405.
            data='{}',
            headers={'Authorization': 'Bearer %s' % (jeton or self.JETON)},
        )

    def test_cloturer_retire_l_activite_de_la_liste(self):
        """⚠️ Odoo 19 ne SUPPRIME plus une activité close : il la désactive.

        `exists()` continue donc de la voir, et un test écrit pour une version
        antérieure passerait à côté. Ce qui compte n'est pas que la ligne
        disparaisse de la base, c'est qu'elle disparaisse de la LISTE — ce que
        le filtre `active` implicite d'Odoo assure déjà.
        """
        activite = self.programmer(date.today(), resume="À clore")
        self.assertIn("À clore", self.mes_lignes())

        reponse = self.cloturer(activite.id)

        self.assertEqual(reponse.status_code, 200)
        self.assertEqual(reponse.json()['status'], 'done')
        self.assertFalse(activite.active, "une activité close est désactivée")
        self.assertNotIn("À clore", self.mes_lignes(),
                         "elle ne doit plus revenir sur le téléphone")

    def test_une_activite_close_ne_revient_jamais(self):
        # Le défaut qu'on n'aurait vu qu'en production : sans le filtre
        # implicite sur `active`, la liste d'un commercial ne se viderait
        # jamais et grossirait à chaque appel passé.
        for i in range(3):
            self.cloturer(self.programmer(date.today(), resume="Close %d" % i).id)
        lignes = self.mes_lignes()
        for i in range(3):
            self.assertNotIn("Close %d" % i, lignes)

    def test_on_ne_cloture_pas_l_activite_d_un_collegue(self):
        """Le contrôle le plus important de cette route.

        Rien n'empêche un jeton volé d'envoyer des identifiants au hasard. Et
        une tâche qui disparaît de la liste d'un collègue ne se remarque pas :
        elle s'oublie.
        """
        sienne = self.programmer(date.today(), commercial=self.collegue)
        reponse = self.cloturer(sienne.id)

        self.assertEqual(reponse.status_code, 404)
        self.assertTrue(sienne.exists(), "l'activité du collègue doit survivre")

    def test_une_activite_inexistante_rend_le_meme_404(self):
        """Indistinguable de « pas la vôtre » : les séparer renseignerait sur
        le portefeuille des autres."""
        self.assertEqual(self.cloturer(999999).status_code, 404)

    def test_la_cloture_est_journalisee(self):
        activite = self.programmer(date.today())
        self.cloturer(activite.id)
        trace = self.env['call.tracker.audit'].search(
            [('action', '=', 'activity_done')], order='id desc', limit=1,
        )
        self.assertEqual(trace.result, 'ok')

    def test_une_cloture_refusee_laisse_aussi_une_trace(self):
        sienne = self.programmer(date.today(), commercial=self.collegue)
        self.cloturer(sienne.id)
        trace = self.env['call.tracker.audit'].search(
            [('action', '=', 'activity_done')], order='id desc', limit=1,
        )
        self.assertEqual(trace.result, 'not_found')
