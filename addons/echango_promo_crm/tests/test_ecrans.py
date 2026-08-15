# -*- coding: utf-8 -*-
"""Les ecrans ouvrent-ils bien les vues qu'on croit ?

⚠️ **Ce fichier existe a cause d'un defaut REEL et parfaitement silencieux.**
`action_echango_promo_suivi` n'a longtemps designe aucune vue. Odoo prenait
alors la liste de plus faible `priority` pour `res.partner` — la liste Contacts
native (8) contre la notre (16). L'ecran s'ouvrait, listait les bons
commercants, se comportait normalement, et n'affichait AUCUNE colonne de Promo.
Rien ne le signalait : ni erreur, ni journal, ni page blanche. Le defaut n'a ete
trouve que parce qu'un bouton ajoute dans la vue n'apparaissait pas.

Une vue definie mais qu'aucune action n'ouvre est du code mort qui a l'air
vivant (regle #31).
"""
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestEcrans(TransactionCase):

    def _vues_de(self, xmlid):
        """{mode: id de vue} tel qu'Odoo le resoudra pour le client web."""
        action = self.env.ref(xmlid)
        return {mode: vue_id for vue_id, mode in action.views}

    def test_le_suivi_ouvre_NOTRE_liste_et_pas_celle_des_contacts(self):
        vues = self._vues_de('echango_promo_crm.action_echango_promo_suivi')
        notre = self.env.ref('echango_promo_crm.view_commercant_promo_list')
        self.assertEqual(
            vues.get('list'), notre.id,
            "l'ecran de suivi n'ouvre pas la liste des commercants — sans "
            "view_ids, Odoo retombe sur base.view_partner_tree")

    def test_le_suivi_garde_le_formulaire_NATIF(self):
        """⚠️ Le contre-cas : designer la liste ne doit pas entrainer de
        designer le formulaire. C'est la fiche client native — avec ses appels,
        ses notes et ses activites — que l'equipe vient chercher en cliquant
        sur une ligne. La remplacer serait exactement le defaut qui a fait
        reconstruire ces ecrans sur `res.partner`."""
        vues = self._vues_de('echango_promo_crm.action_echango_promo_suivi')
        self.assertIn('form', vues)
        self.assertFalse(
            vues.get('form'),
            "un formulaire est impose la ou le natif doit s'appliquer")

    def test_le_bouton_d_affectation_est_dans_la_liste_ouverte(self):
        """⚠️ Le controle qui aurait trouve le defaut d'un coup : le bouton
        existait, dans une vue que personne n'ouvrait. Verifier qu'il est
        « quelque part dans le module » n'aurait rien prouve."""
        vues = self._vues_de('echango_promo_crm.action_echango_promo_suivi')
        liste = self.env['ir.ui.view'].browse(vues['list'])
        action = self.env.ref('echango_promo_crm.action_campagne_wizard')
        self.assertIn('<header>', liste.arch,
                      "la liste ouverte n'a pas d'en-tete de selection")
        self.assertIn(str(action.id), liste.arch,
                      "le bouton d'affectation n'est pas dans la liste ouverte")

    def test_chaque_action_du_module_designe_une_vue_ou_est_seule_a_pouvoir(self):
        """La generalisation : une action qui ne designe rien n'est sure que si
        notre module est le SEUL a fournir des vues pour ce modele. Des qu'un
        autre module en fournit — `res.partner` est le cas d'ecole — le choix
        d'Odoo se fait sur la priorite, et il nous echappe."""
        Vue = self.env['ir.ui.view']
        for action in self.env['ir.actions.act_window'].search([]):
            xmlid = action.get_external_id().get(action.id) or ''
            if not xmlid.startswith('echango_promo_crm.'):
                continue
            if action.view_id or action.view_ids:
                continue
            concurrentes = Vue.search_count([
                ('model', '=', action.res_model),
                ('type', '=', 'list'),
                ('inherit_id', '=', False),
            ])
            self.assertLessEqual(
                concurrentes, 1,
                "%s ne designe aucune vue alors que %d listes existent pour "
                "%s : Odoo choisira par priorite, et pas forcement la notre"
                % (xmlid, concurrentes, action.res_model))
