# -*- coding: utf-8 -*-
"""Confier un lot de commercants a un commercial.

Ce que le banc eprouve n'est pas « l'assistant cree des opportunites » — il en
creerait aussi bien sur des fournisseurs. Ce sont ses REFUS : il doit ecarter
ce qui n'est pas un commercant, ce qui est supprime cote Promo, et ce qui est
deja suivi.
"""
from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestCampagne(TransactionCase):

    def setUp(self):
        super().setUp()
        self.commercial = self.env['res.users'].create({
            'name': "Commercial de banc", 'login': 'banc_campagne',
            'email': 'banc.campagne@example.org',
        })
        self.compteur = 0

    def _commercant(self, nom, **extra):
        """Un commercant complet : partenaire + compte Promo."""
        self.compteur += 1
        partenaire = self.env['res.partner'].create({
            'name': nom, 'is_company': True})
        valeurs = {
            'partner_id': partenaire.id,
            'promo_uuid': 'camp-%02d' % self.compteur,
            'nom_promo': nom,
            'telephone_e164': '+21377000%03d' % self.compteur,
            'pays': 'DZ',
        }
        valeurs.update(extra)
        self.env['echango.promo.account'].create(valeurs)
        return partenaire

    def _assistant(self, partenaires, **extra):
        valeurs = {'motif': "Appeler et comprendre l'absence de publication."}
        valeurs.update(extra)
        return self.env['echango.promo.campagne.wizard'].with_context(
            active_ids=partenaires.ids,
            active_model='res.partner',
        ).create(valeurs)

    # ── Ce qui doit marcher ───────────────────────────────────────────────

    def test_une_opportunite_PAR_commercant(self):
        """⚠️ Pas une seule pour le lot : le grain de travail est l'appel a UN
        commercant. Une opportunite portant trente noms ne pourrait ni avancer,
        ni etre gagnee, ni etre perdue."""
        cibles = self._commercant("Alpha") | self._commercant("Beta")
        assistant = self._assistant(cibles, commercial_id=self.commercial.id)

        assistant.action_creer()

        opportunites = self.env['crm.lead'].search(
            [('partner_id', 'in', cibles.ids)])
        self.assertEqual(len(opportunites), 2)
        self.assertEqual(sorted(opportunites.mapped('partner_id.name')),
                         ["Alpha", "Beta"])
        self.assertEqual(set(opportunites.mapped('user_id')),
                         {self.commercial})

    def test_l_opportunite_arrive_dans_la_PREMIERE_etape_du_pipeline(self):
        """⚠️ L'etape n'est jamais nommee en dur. « New » est la premiere etape
        non repliee de l'equipe ; l'ecrire en clair casserait sur toute base
        traduite ou renommee, et le symptome serait une opportunite rangee dans
        la mauvaise colonne — pas une erreur."""
        cible = self._commercant("Gamma")
        self._assistant(cible, commercial_id=self.commercial.id).action_creer()

        opportunite = self.env['crm.lead'].search(
            [('partner_id', '=', cible.id)], limit=1)
        self.assertTrue(opportunite.stage_id, "aucune etape posee")
        self.assertFalse(opportunite.stage_id.fold,
                         "l'opportunite arrive dans une etape repliee")
        # ⚠️ Odoo 19 : `crm.stage.team_id` N'EXISTE PLUS, c'est `team_ids`
        # (plusieurs equipes par etape). Un test ecrit sur l'ancien nom leve
        # une ValueError et non un echec d'assertion — donc un ERROR, pas un
        # FAIL, et on cherche le defaut au mauvais endroit.
        candidates = self.env['crm.stage'].search(
            ['|', ('team_ids', '=', False),
             ('team_ids', 'in', opportunite.team_id.ids)],
            order='sequence, id')
        self.assertTrue(candidates, "le pipeline n'a aucune etape")
        self.assertEqual(opportunite.stage_id, candidates[0],
                         "ce n'est pas la premiere etape du pipeline")

    def test_la_consigne_est_recopiee_dans_chaque_opportunite(self):
        cible = self._commercant("Delta")
        self._assistant(cible, commercial_id=self.commercial.id,
                        motif="Relancer avant vendredi.").action_creer()

        opportunite = self.env['crm.lead'].search(
            [('partner_id', '=', cible.id)], limit=1)
        # ⚠️ `description` est un champ HTML : le comparer a une chaine brute
        # echouerait sur le balisage, pas sur le contenu.
        self.assertIn("Relancer avant vendredi.", str(opportunite.description))

    def test_un_appel_est_planifie_sinon_personne_n_est_prevenu(self):
        """⚠️ Sans activite, l'opportunite existe et n'apparait dans la liste
        de taches de personne. Le travail serait cree sans etre confie."""
        cible = self._commercant("Epsilon")
        self._assistant(cible, commercial_id=self.commercial.id).action_creer()

        opportunite = self.env['crm.lead'].search(
            [('partner_id', '=', cible.id)], limit=1)
        activites = opportunite.activity_ids
        self.assertEqual(len(activites), 1)
        self.assertEqual(activites.user_id, self.commercial)

    def test_la_fiche_client_peut_NE_PAS_etre_reaffectee(self):
        """Confier une relance ponctuelle ne doit pas reattribuer le
        portefeuille : deux gestes distincts, deux cases."""
        cible = self._commercant("Zeta")
        self._assistant(cible, commercial_id=self.commercial.id,
                        affecter_fiche=False).action_creer()
        self.assertFalse(cible.user_id)

        cible2 = self._commercant("Eta")
        self._assistant(cible2, commercial_id=self.commercial.id,
                        affecter_fiche=True).action_creer()
        self.assertEqual(cible2.user_id, self.commercial)

    # ── Ce qui doit REFUSER ───────────────────────────────────────────────

    def test_un_contact_qui_n_est_PAS_commercant_est_ecarte(self):
        """⚠️ Le cas dangereux : une opportunite « relance publication » sur un
        fournisseur est une donnee fausse et parfaitement credible."""
        commercant = self._commercant("Theta")
        fournisseur = self.env['res.partner'].create(
            {'name': "Fournisseur quelconque", 'is_company': True})

        assistant = self._assistant(commercant | fournisseur,
                                    commercial_id=self.commercial.id)

        self.assertEqual(assistant.commercant_ids, commercant)
        assistant.action_creer()
        self.assertFalse(self.env['crm.lead'].search(
            [('partner_id', '=', fournisseur.id)]))

    def test_un_commercant_SUPPRIME_cote_promo_est_ecarte(self):
        """Un compte supprime n'a plus rien a relancer."""
        vivant = self._commercant("Iota")
        supprime = self._commercant("Kappa")
        supprime.promo_account_id.supprime_le = '2026-01-01 00:00:00'

        assistant = self._assistant(vivant | supprime,
                                    commercial_id=self.commercial.id)
        self.assertEqual(assistant.commercant_ids, vivant)

    def test_AUCUN_commercant_valable_leve_au_lieu_de_ne_rien_faire(self):
        """⚠️ Un assistant qui s'ouvre vide sur une selection entierement
        invalide ferait croire a une action possible. Le refus doit etre dit."""
        fournisseur = self.env['res.partner'].create(
            {'name': "Rien qu'un fournisseur", 'is_company': True})
        with self.assertRaises(UserError):
            self._assistant(fournisseur, commercial_id=self.commercial.id)

    def test_un_commercant_DEJA_suivi_n_en_recoit_pas_une_seconde(self):
        neuf = self._commercant("Lambda")
        deja = self._commercant("Mu")
        self._assistant(deja, commercial_id=self.commercial.id).action_creer()

        assistant = self._assistant(neuf | deja,
                                    commercial_id=self.commercial.id)
        self.assertEqual(assistant.nombre_selectionnes, 2)
        self.assertEqual(assistant.nombre_deja_en_cours, 1)
        self.assertEqual(assistant.nombre_a_creer, 1)

        assistant.action_creer()
        self.assertEqual(len(self.env['crm.lead'].search(
            [('partner_id', '=', deja.id)])), 1)

    def test_une_opportunite_GAGNEE_ne_bloque_pas_une_nouvelle_relance(self):
        """⚠️ « Ouverte » n'est pas « active » : une opportunite gagnee reste
        active. Ne regarder que `active` ferait passer pour « deja suivi » un
        commercant dont l'affaire est close depuis six mois — il ne serait
        jamais rappele, et rien ne le dirait."""
        cible = self._commercant("Nu")
        self._assistant(cible, commercial_id=self.commercial.id).action_creer()
        opportunite = self.env['crm.lead'].search(
            [('partner_id', '=', cible.id)], limit=1)
        gagnee = self.env['crm.stage'].search([('is_won', '=', True)], limit=1)
        self.assertTrue(gagnee, "le pipeline doit avoir une etape gagnee")
        opportunite.stage_id = gagnee

        assistant = self._assistant(cible, commercial_id=self.commercial.id)
        self.assertEqual(assistant.nombre_deja_en_cours, 0)
        self.assertEqual(assistant.nombre_a_creer, 1)

    def test_TOUS_deja_en_cours_leve_au_lieu_de_creer_zero(self):
        """Sortir en silence ferait croire que l'action a eu lieu."""
        cible = self._commercant("Xi")
        self._assistant(cible, commercial_id=self.commercial.id).action_creer()

        assistant = self._assistant(cible, commercial_id=self.commercial.id)
        with self.assertRaises(UserError):
            assistant.action_creer()

    def test_la_consigne_est_OBLIGATOIRE(self):
        """Une relance sans consigne est un nom dans une colonne : le
        commercial ne sait pas quoi dire."""
        cible = self._commercant("Omicron")
        with self.assertRaises(Exception):
            self.env['echango.promo.campagne.wizard'].with_context(
                active_ids=cible.ids).create({
                    'commercial_id': self.commercial.id,
                }).action_creer()
