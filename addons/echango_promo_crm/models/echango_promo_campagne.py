# -*- coding: utf-8 -*-
"""Confier un lot de commerçants à un commercial, avec une consigne.

⚠️ **Odoo n'a AUCUNE action de masse « créer des opportunités depuis une liste
de contacts ».** Le bouton « Opportunités » de la fiche client en crée une, à
l'unité. Confier trente commerçants dormants à un commercial se faisait donc
fiche par fiche — trente ouvertures, trente saisies de la même consigne.

⚠️ **Une opportunité PAR commerçant, pas une pour le lot.** C'est le grain de
travail réel : le commercial appelle *un* commerçant, note *sa* réponse, et son
étape avance ou pas. Une opportunité unique portant trente noms ne pourrait ni
avancer, ni être perdue, ni être gagnée — elle ne serait qu'un pense-bête, et
le pipeline ne dirait plus rien.
"""
import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools.mail import plaintext2html

_logger = logging.getLogger(__name__)


class EchangoPromoCampagneWizard(models.TransientModel):
    _name = 'echango.promo.campagne.wizard'
    _description = "Affecter des commerçants à un commercial"

    commercant_ids = fields.Many2many(
        'res.partner', string="Commerçants", readonly=True,
        help="Les commerçants sélectionnés dans la liste.")

    commercial_id = fields.Many2one(
        'res.users', string="Commercial", required=True,
        domain="[('share', '=', False)]",
        help="Celui qui traitera ces commerçants.")
    equipe_id = fields.Many2one(
        'crm.team', string="Équipe commerciale",
        help="Détermine le pipeline, donc les étapes. Laisser vide prend "
             "l'équipe par défaut du commercial.")

    sujet = fields.Char(
        string="Sujet", required=True, default="Relance publication",
        help="Titre de l'opportunité. Le nom du commerçant y est ajouté.")
    motif = fields.Text(
        string="Consigne", required=True,
        help="Ce que le commercial doit faire, et pourquoi. Recopié dans "
             "chaque opportunité.")
    date_echeance = fields.Date(string="Échéance")
    etiquette_ids = fields.Many2many('crm.tag', string="Étiquettes")

    #: ⚠️ **Deux gestes distincts, deux cases.** Créer l'opportunité met le
    #: commerçant dans un pipeline ; affecter la fiche dit *qui le suit* de
    #: façon durable. Les lier d'office empêcherait de confier une relance
    #: ponctuelle sans réattribuer le portefeuille.
    affecter_fiche = fields.Boolean(
        string="Affecter aussi la fiche client", default=True,
        help="Renseigne le commercial sur la fiche du commerçant, pas "
             "seulement sur l'opportunité.")
    planifier_appel = fields.Boolean(
        string="Planifier un appel", default=True,
        help="Crée l'activité « Appel » sur chaque opportunité, à l'échéance "
             "indiquée. Sans elle, rien n'apparaît dans la liste de tâches "
             "du commercial.")
    eviter_doublons = fields.Boolean(
        string="Ignorer ceux déjà en cours", default=True,
        help="Un commerçant qui a déjà une opportunité ouverte n'en reçoit "
             "pas une seconde.")

    nombre_selectionnes = fields.Integer(
        string="Sélectionnés", compute='_compute_repartition')
    nombre_deja_en_cours = fields.Integer(
        string="Déjà en cours", compute='_compute_repartition')
    nombre_a_creer = fields.Integer(
        string="À créer", compute='_compute_repartition')

    @api.model
    def default_get(self, champs):
        valeurs = super().default_get(champs)
        ids = self.env.context.get('active_ids') or []
        if not ids:
            return valeurs
        partenaires = self.env['res.partner'].browse(ids)

        # ⚠️ **Le filtre est ici, pas dans la vue.** L'action est posée sur une
        # liste de commerçants, mais rien n'empêche d'y arriver autrement — et
        # créer une opportunité « relance publication » sur un fournisseur
        # produirait une donnée fausse et parfaitement crédible.
        commercants = partenaires.filtered(
            lambda p: p.est_commercant_promo and not p.promo_supprime_le)
        if not commercants:
            raise UserError(_(
                "Aucun des %(total)s contacts sélectionnés n'est un commerçant "
                "echango Promo actif. Un compte supprimé côté Promo n'a plus "
                "rien à relancer.", total=len(partenaires)))

        valeurs['commercant_ids'] = [(6, 0, commercants.ids)]
        return valeurs

    @api.depends('commercant_ids', 'eviter_doublons')
    def _compute_repartition(self):
        for assistant in self:
            total = assistant.commercant_ids
            deja = assistant._commercants_deja_en_cours(total)
            assistant.nombre_selectionnes = len(total)
            assistant.nombre_deja_en_cours = len(deja)
            assistant.nombre_a_creer = len(
                total - deja if assistant.eviter_doublons else total)

    def _commercants_deja_en_cours(self, commercants):
        """Ceux qui portent déjà une opportunité ouverte.

        ⚠️ **« Ouverte » n'est pas « active ».** Une opportunité gagnée reste
        active : ne regarder que `active` ferait considérer comme « déjà
        suivi » un commerçant dont l'affaire est close depuis six mois, et il
        ne serait jamais rappelé. Une opportunité perdue, elle, est archivée —
        d'où le `active` en plus de l'étape.
        """
        if not commercants:
            return self.env['res.partner']
        # Une seule requête pour tout le lot (règle #14 : pas de compte par
        # commerçant dans une boucle).
        groupes = self.env['crm.lead']._read_group(
            [('partner_id', 'in', commercants.ids),
             ('active', '=', True),
             ('stage_id.is_won', '=', False)],
            groupby=['partner_id'])
        return self.env['res.partner'].union(*[g[0] for g in groupes])

    def action_creer(self):
        """Crée une opportunité par commerçant retenu, et rend leur liste."""
        self.ensure_one()

        cibles = self.commercant_ids
        if self.eviter_doublons:
            cibles -= self._commercants_deja_en_cours(cibles)
        if not cibles:
            raise UserError(_(
                "Les %(total)s commerçants sélectionnés ont déjà une "
                "opportunité ouverte. Décocher « Ignorer ceux déjà en cours » "
                "pour en créer une seconde malgré tout.",
                total=len(self.commercant_ids)))

        equipe = self.equipe_id or self._equipe_du_commercial()
        description = plaintext2html(self.motif)

        # ⚠️ **Un seul `create` pour tout le lot.** Trente `create()` dans une
        # boucle, c'est trente fois le calcul des champs dérivés et trente
        # messages de suivi — mesurable dès la deuxième dizaine.
        valeurs = [{
            'name': "%s — %s" % (self.sujet, partenaire.display_name),
            'type': 'opportunity',
            'partner_id': partenaire.id,
            'user_id': self.commercial_id.id,
            'team_id': equipe.id if equipe else False,
            'description': description,
            'date_deadline': self.date_echeance or False,
            'tag_ids': [(6, 0, self.etiquette_ids.ids)],
        } for partenaire in cibles]

        # ⚠️ **`stage_id` n'est PAS renseigné, volontairement.** Odoo pose
        # alors la première étape non repliée du pipeline de l'équipe — « New »
        # dans le pipeline par défaut. La nommer en dur ici casserait sur toute
        # base traduite ou dont les étapes ont été renommées, et le symptôme
        # serait une opportunité rangée dans la mauvaise colonne, pas une
        # erreur.
        opportunites = self.env['crm.lead'].create(valeurs)

        if self.affecter_fiche:
            cibles.write({'user_id': self.commercial_id.id})

        if self.planifier_appel:
            # ⚠️ Sans activité, rien n'apparaît dans la liste de tâches du
            # commercial : l'opportunité existe, et personne n'est prévenu.
            opportunites.activity_schedule(
                'mail.mail_activity_data_call',
                date_deadline=self.date_echeance or fields.Date.context_today(self),
                summary=self.sujet,
                note=description,
                user_id=self.commercial_id.id,
            )

        ignores = len(self.commercant_ids) - len(cibles)
        _logger.info(
            "echango_promo_crm : %d opportunité(s) créée(s) pour %s, "
            "%d ignorée(s) car déjà en cours",
            len(opportunites), self.commercial_id.display_name, ignores)

        return {
            'type': 'ir.actions.act_window',
            'name': _("%(nb)s opportunité(s) créée(s)", nb=len(opportunites)),
            'res_model': 'crm.lead',
            'view_mode': 'list,kanban,form',
            'domain': [('id', 'in', opportunites.ids)],
            'context': {'default_type': 'opportunity'},
        }

    def _equipe_du_commercial(self):
        """L'équipe par défaut du commercial, ou aucune.

        ⚠️ **Aucune équipe est un résultat valable, pas un défaut à combler.**
        Odoo sait choisir seul à la création ; lui imposer la première équipe
        venue rangerait l'opportunité dans un pipeline étranger, avec des
        étapes qui n'ont rien à voir.
        """
        self.ensure_one()
        return self.env['crm.team']._get_default_team_id(
            user_id=self.commercial_id.id)
