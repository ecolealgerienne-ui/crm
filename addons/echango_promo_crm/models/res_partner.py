# -*- coding: utf-8 -*-
from odoo import _, api, fields, models

#: Les motifs qu'une action de NOTRE côté peut lever. Les autres (position
#: absente, plafond, quota) se lèvent chez le commerçant : les mêler ferait
#: appeler des gens à qui l'on n'a rien à demander.
MOTIFS_A_DEBLOQUER = ['registre_en_attente', 'profil_en_revue']


class ResPartner(models.Model):
    """Le commerçant, vu comme un client — et c'est le point de la manœuvre.

    ⚠️ **Pourquoi les écrans de suivi sont bâtis ICI et non sur la vue SQL.**
    Un clic sur une ligne de liste ouvre le formulaire **du modèle de la
    liste**. Une liste bâtie sur `echango.promo.suivi` ouvre donc une ligne de
    vue SQL — techniquement valide, commercialement vide : ni appels, ni notes,
    ni activités, ni commercial. Or c'est exactement ce que l'équipe vient
    chercher.

    En posant les faits de Promo sur `res.partner`, le clic de ligne ouvre la
    **fiche client** sans qu'aucun code ne s'en mêle. C'est le comportement
    natif d'Odoo qui fait le travail, pas un contournement.

    ⚠️ **`store=True` sur les champs liés, et ce n'est pas de la duplication
    gratuite** : sans stockage, aucun de ces champs ne serait ni triable, ni
    filtrable, ni regroupable — donc aucun des écrans ne serait utilisable.
    Odoo les tient à jour tout seul à chaque écriture sur la fiche Promo.
    """

    _inherit = 'res.partner'

    echango_promo_account_ids = fields.One2many(
        'echango.promo.account', 'partner_id', string="Suivi echango Promo")

    #: ⚠️ Un seul compte par client — l'unicité est posée en base
    #: (`echango_promo_account_partner_uniq`). Ce many2one existe pour que les
    #: champs liés ci-dessous aient un chemin stable à traverser.
    promo_account_id = fields.Many2one(
        'echango.promo.account', string="Fiche Promo",
        compute='_compute_promo_account_id', store=True)

    @api.depends('echango_promo_account_ids')
    def _compute_promo_account_id(self):
        for partenaire in self:
            partenaire.promo_account_id = partenaire.echango_promo_account_ids[:1]

    #: ⚠️ **La provenance ne se lit ni sur une équipe ni sur une étiquette.**
    #: Une équipe est mutable, une étiquette se retire ; l'existence d'une fiche
    #: Promo, non. Et `res.partner` n'a de toute façon plus de `team_id` en
    #: Odoo 19 — vérifié sur les sources.
    est_commercant_promo = fields.Boolean(
        string="Commerçant echango Promo",
        compute='_compute_est_commercant_promo', store=True,
        help="Vient d'echango Promo. C'est l'identifiant technique qui le dit, "
             "pas un champ que l'on peut changer.")

    @api.depends('promo_account_id')
    def _compute_est_commercant_promo(self):
        for partenaire in self:
            partenaire.est_commercant_promo = bool(partenaire.promo_account_id)

    # ── Les faits de Promo, portés par le client ────────────────────────────

    promo_derniere_publication = fields.Datetime(
        related='promo_account_id.date_derniere_publication', store=True,
        string="Dernière publication")
    promo_jamais_publie = fields.Boolean(
        string="N'a jamais publié", compute='_compute_promo_jamais_publie',
        store=True)
    promo_en_ligne = fields.Integer(
        related='promo_account_id.promos_en_ligne', store=True,
        string="Promos en ligne")
    promo_visibles = fields.Integer(
        related='promo_account_id.promos_visibles', store=True,
        string="Promos visibles")
    promo_signalements_90j = fields.Integer(
        related='promo_account_id.signalements_90j', store=True,
        string="Signalements (90 j)")
    promo_peut_publier = fields.Boolean(
        related='promo_account_id.peut_publier', store=True,
        string="Peut publier")
    promo_motif_blocage = fields.Selection(
        related='promo_account_id.motif_blocage', store=True,
        string="Motif de blocage")
    promo_registre_statut = fields.Selection(
        related='promo_account_id.registre_statut', store=True,
        string="Registre")
    promo_ville = fields.Char(
        related='promo_account_id.ville_geocodee', store=True, string="Ville")
    promo_wilaya = fields.Char(
        related='promo_account_id.wilaya_geocodee', store=True,
        string="Wilaya")
    promo_geocodage_statut = fields.Selection(
        related='promo_account_id.geocodage_statut', store=True,
        string="Géocodage")
    promo_derniere_synchro = fields.Datetime(
        related='promo_account_id.derniere_synchro', store=True,
        string="Reçu le")

    #: ⚠️ **Un compte supprimé n'a plus rien à suivre**, et il fausse tout ce
    #: qu'on compte : la vue SQL l'excluait, les écrans bâtis sur `res.partner`
    #: doivent l'exclure aussi. Sans ce champ, « À débloquer » passait de 70 à
    #: 176 — les 106 supprimés portant le motif `compte_supprime`, qui ne se
    #: débloque par personne.
    #:
    #: Il reste servi 30 jours par Promo (propagation de l'effacement), donc sa
    #: fiche existe encore ici : c'est bien un filtre d'écran qu'il faut, pas un
    #: archivage.
    promo_supprime_le = fields.Datetime(
        related='promo_account_id.supprime_le', store=True,
        string="Supprimé côté Promo")
    promo_suspendu_le = fields.Datetime(
        related='promo_account_id.suspendu_le', store=True,
        string="Suspendu")

    #: ⚠️ **Ces trois-là ne sont pas du confort.** Ils étaient la seule raison
    #: de garder un menu vers la donnée brute, et leur absence rendait
    #: invisibles trois faits qui ne se voient nulle part ailleurs :
    #:
    #: - `consentement_le` vide = compte créé par un agent, qui n'a accepté
    #:   aucune CGU. 182 fiches sur 280 au 2026-08-15 — c'est le point de
    #:   conformité 18-07, pas un détail ;
    #: - `plafond_propre` renseigné = dérogation négociée, invisible partout
    #:   ailleurs puisque le plafond effectif l'absorbe ;
    #: - `promos_masquees` = modération subie, que le commerçant ne voit pas et
    #:   dont le commercial doit savoir avant d'appeler.
    promo_consentement_le = fields.Datetime(
        related='promo_account_id.consentement_le', store=True,
        string="CGU acceptées le")
    promo_plafond_propre = fields.Integer(
        related='promo_account_id.plafond_propre', store=True,
        string="Dérogation de plafond")
    promo_masquees = fields.Integer(
        related='promo_account_id.promos_masquees', store=True,
        string="Promos masquées")

    #: ⚠️ **Non stocké, et c'est délibéré.** Ce nombre dépend d'AUJOURD'HUI :
    #: stocké, il serait juste le jour de son écriture et faux le lendemain,
    #: sans que rien ne le dise. Il ne sert donc qu'à l'affichage — trier par
    #: `promo_derniere_publication` donne exactement le même ordre, et lui est
    #: stocké.
    promo_jours_depuis_publication = fields.Integer(
        string="Jours depuis la dernière publication",
        compute='_compute_promo_jours_depuis_publication', aggregator='avg')

    #: ⚠️ **Deux méthodes, et ce n'est pas une redite.** Une seule méthode
    #: calculant à la fois un champ stocké et un champ non stocké fait lever
    #: Odoo 19 à l'installation : « inconsistent 'store' for computed fields,
    #: accessing promo_jours_depuis_publication may recompute and update
    #: promo_jamais_publie ». Ce n'est pas qu'un avertissement de style —
    #: **lire** le champ d'affichage déclencherait une **écriture** sur le champ
    #: stocké, donc une transaction là où l'on croyait ne faire qu'afficher.
    @api.depends('promo_derniere_publication', 'promo_account_id')
    def _compute_promo_jamais_publie(self):
        for partenaire in self:
            partenaire.promo_jamais_publie = (
                not partenaire.promo_derniere_publication
                and bool(partenaire.promo_account_id))

    @api.depends('promo_derniere_publication')
    def _compute_promo_jours_depuis_publication(self):
        aujourdhui = fields.Date.context_today(self)
        for partenaire in self:
            date = partenaire.promo_derniere_publication
            # ⚠️ **Zéro n'est pas « jamais ».** Le champ voisin porte cette
            # distinction ; ici, zéro veut dire « publié aujourd'hui ».
            partenaire.promo_jours_depuis_publication = (
                (aujourdhui - date.date()).days if date else 0)

    # ── Actions ─────────────────────────────────────────────────────────────

    def action_voir_suivi_promo(self):
        """La fiche Promo détaillée, depuis le bouton de la fiche client."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _("Suivi echango Promo — %s", self.display_name),
            'res_model': 'echango.promo.account',
            'view_mode': 'form',
            'res_id': self.promo_account_id.id,
            'context': {'create': False},
        }
