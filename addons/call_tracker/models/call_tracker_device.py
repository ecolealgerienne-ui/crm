# -*- coding: utf-8 -*-
import hashlib
import secrets
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError

#: Au-delà de ce silence, l'appareil est signalé. Trois jours couvrent un
#: week-end sans crier, et restent en deçà du délai où l'on cesserait de
#: pouvoir reconstituer ce qui s'est passé.
#: ⚠️ Ce seuil est repris en dur dans le filtre de recherche des vues, qui
#: doit s'exprimer en domaine côté serveur — les deux sont à changer ensemble.
SILENCE_JOURS = 3


def hacher_jeton(jeton):
    """Empreinte SHA-256 d'un jeton, en hexadécimal.

    Un SHA-256 nu suffit ici, et ce n'est pas un raccourci. Les fonctions
    lentes (pbkdf2, bcrypt) servent à rendre coûteuse l'énumération de secrets
    à faible entropie — les mots de passe choisis par des humains. Un jeton
    produit par ``secrets.token_urlsafe(32)`` porte 256 bits d'aléa : il n'y a
    rien à énumérer, et un KDF lent ne ferait que ralentir chaque appel de
    l'app sans rien protéger de plus.
    """
    return hashlib.sha256(jeton.encode('utf-8')).hexdigest()


class CallTrackerDevice(models.Model):
    _name = 'call.tracker.device'
    _description = "Appareil mobile relié au Call Tracker"
    _order = 'name'

    name = fields.Char(
        string="Libellé",
        required=True,
        help="Pour identifier l'appareil d'un coup d'œil, ex. « Samsung d'Amar ».",
    )
    # Un appareil = un commercial. Décision du 2026-08-09 : pas de session
    # utilisateur au MVP, le jeton porte l'identité. La spec (§10.3) jugeait
    # elle-même le multi-commercial par appareil peu probable. Le jour où il
    # faudrait des sessions, ce champ deviendrait le défaut plutôt que la
    # seule source — le schéma des journaux n'a pas à changer.
    user_id = fields.Many2one(
        'res.users',
        string="Commercial",
        required=True,
        ondelete='restrict',
        help="Utilisateur Odoo auquel les appels de cet appareil sont attribués.",
    )
    # Seule l'empreinte est conservée. Le jeton en clair n'existe qu'une fois,
    # dans l'assistant affiché juste après sa génération.
    token_hash = fields.Char(
        string="Empreinte du jeton",
        readonly=True,
        copy=False,
        index=True,
        groups='base.group_system',
    )
    active = fields.Boolean(
        default=True,
        help="Décocher révoque l'appareil : ses appels sont refusés, sans "
             "toucher au compte du commercial ni aux appels déjà journalisés.",
    )
    # ── Ce que l'appareil déclare de lui-même ────────────────────────────────
    #
    # Renseignés par l'application à chaque appel remis, via des EN-TÊTES HTTP
    # et non par la charge utile : celle-ci a une liste blanche stricte qui
    # rejette tout champ inconnu, et y ajouter des clés ferait échouer l'envoi
    # de TOUS les appels d'une version d'app plus ancienne. Un en-tête absent
    # ne casse rien.
    #
    # ⚠️ Déclaratif, donc à ne pas confondre avec une preuve. Ces champs
    # servent à EXPLIQUER un délai de remise, pas à établir un fait : un
    # appareil peut annoncer ce qu'il veut. C'est suffisant pour répondre à
    # « quels modèles remontent en retard ? », insuffisant pour fonder quoi
    # que ce soit de contractuel.
    device_model = fields.Char(
        string="Modèle",
        readonly=True,
        help="Marque et modèle annoncés par l'appareil au dernier envoi.",
    )
    os_version = fields.Char(
        string="Version d'Android",
        readonly=True,
    )

    # « Dernier contact » et non « dernier appel reçu » : ce champ ne dit rien
    # des appels entrants du téléphone, il date la dernière fois que le serveur
    # a eu des nouvelles de cet appareil. C'est le champ dont dépend tout le
    # diagnostic « ce commercial n'appelle plus » contre « ce téléphone
    # n'envoie plus » ; un intitulé ambigu le rendait illisible.
    last_seen = fields.Datetime(
        string="Dernier contact de l'appareil",
        readonly=True,
        copy=False,
        help="Dernière remise d'appel reçue de cet appareil.",
    )
    log_count = fields.Integer(
        string="Appels journalisés",
        compute='_compute_log_count',
    )

    silencieux = fields.Boolean(
        string="Silencieux",
        compute='_compute_silencieux',
        help="Aucune nouvelle de cet appareil depuis plus de "
             "%s jours." % SILENCE_JOURS,
    )

    @api.depends('last_seen', 'active', 'create_date')
    def _compute_silencieux(self):
        """Un appareil actif dont on n'a plus de nouvelles.

        Le repli sur ``create_date`` n'est pas un détail : sans lui, un
        appareil déclaré ce matin serait signalé avant même que le commercial
        ait eu le temps d'installer l'application. Avec lui, l'appareil déclaré
        il y a quatre jours qui n'a JAMAIS rien envoyé est signalé — et c'est
        exactement le cas d'un enrôlement raté, que rien d'autre ne révèle.
        """
        seuil = fields.Datetime.now() - timedelta(days=SILENCE_JOURS)
        for appareil in self:
            if not appareil.active:
                # Un appareil révoqué est silencieux par construction : le
                # signaler noierait ceux qui devraient parler.
                appareil.silencieux = False
                continue
            dernier_signe = appareil.last_seen or appareil.create_date
            appareil.silencieux = bool(dernier_signe and dernier_signe < seuil)

    def _compute_log_count(self):
        # read_group en un seul appel : un search_count par ligne ferait une
        # requête par appareil dans la vue liste.
        comptes = dict(self.env['call.tracker.log']._read_group(
            [('device_id', 'in', self.ids)],
            groupby=['device_id'],
            aggregates=['__count'],
        ))
        for appareil in self:
            appareil.log_count = comptes.get(appareil, 0)

    @api.model
    def _resoudre_par_jeton(self, jeton):
        """Retourne l'appareil actif correspondant au jeton, ou un recordset vide.

        Recherche par empreinte : le jeton en clair n'est jamais comparé à
        quoi que ce soit de stocké, et une fuite de la base ne livre pas de
        jeton utilisable.
        """
        if not jeton:
            return self.browse()
        return self.sudo().search(
            [('token_hash', '=', hacher_jeton(jeton))],
            limit=1,
        )

    def action_generer_jeton(self):
        """Génère un jeton, n'en garde que l'empreinte, et l'affiche une fois."""
        self.ensure_one()
        if not self.env.user.has_group('base.group_system'):
            raise UserError(_("Seul un administrateur peut générer un jeton d'appareil."))

        jeton = secrets.token_urlsafe(32)
        self.sudo().write({'token_hash': hacher_jeton(jeton)})

        assistant = self.env['call.tracker.token.wizard'].create({
            'device_id': self.id,
            'token_clear': jeton,
        })
        return {
            'type': 'ir.actions.act_window',
            'name': _("Jeton de l'appareil"),
            'res_model': 'call.tracker.token.wizard',
            'res_id': assistant.id,
            'view_mode': 'form',
            'target': 'new',
        }
