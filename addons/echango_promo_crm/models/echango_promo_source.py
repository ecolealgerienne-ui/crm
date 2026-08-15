# -*- coding: utf-8 -*-
import hashlib
import secrets
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class EchangoPromoSource(models.Model):
    """La source qui pousse l'instantané — une seule en pratique, et son jeton.

    ⚠️ **Pourquoi un modèle à part et non `call.tracker.device`.** Chez le
    voisin, `user_id` est obligatoire : c'est de lui que viennent l'attribution
    des appels et le cloisonnement des règles d'enregistrement. Une source
    « echango Promo » n'a pas d'utilisateur — ce n'est pas quelqu'un, c'est un
    serveur. Réutiliser ce modèle aurait demandé un utilisateur technique
    fictif, donc un compte de plus à protéger pour rien.

    ⚠️ **Seule l'empreinte est stockée.** Le jeton en clair n'existe qu'une
    fois, dans l'assistant qui le montre. Un jeton relisible en base est un
    jeton qui traîne dans les sauvegardes.
    """

    _name = 'echango.promo.source'
    _description = "echango Promo — source de synchronisation"
    _order = 'name'

    name = fields.Char(string="Nom", required=True, default="echango Promo")
    active = fields.Boolean(string="Actif", default=True)

    token_hash = fields.Char(
        string="Empreinte du jeton",
        readonly=True,
        copy=False,
        groups='base.group_system',
        help="SHA-256 du jeton. Le jeton lui-même n'est jamais stocké.",
    )

    #: ⚠️ Le silence n'est pas un succès. Sans cette date, « aucun commerçant
    #: n'a bougé » et « le lot n'est jamais arrivé » produisent le même écran.
    last_seen = fields.Datetime(string="Dernier lot reçu", readonly=True)
    last_batch = fields.Char(string="Identifiant du dernier lot", readonly=True)
    last_count = fields.Integer(string="Fiches du dernier lot", readonly=True)

    silencieux = fields.Boolean(
        string="Silencieuse",
        compute='_compute_silencieux',
        search='_search_silencieux',
        help="Aucun lot reçu depuis plus de 36 heures.",
    )

    #: 36 h et non 24 : un lot quotidien qui glisse d'une heure ne doit pas
    #: faire crier au loup, mais deux nuits manquées, si.
    SEUIL_SILENCE_HEURES = 36

    @api.depends('last_seen')
    def _compute_silencieux(self):
        # ⚠️ `timedelta` vient du module `datetime`, PAS de `fields` :
        # `fields.datetime` est la CLASSE datetime, et `fields.datetime.timedelta`
        # lève un AttributeError au premier calcul — donc à l'affichage du
        # ruban « Silencieuse », jamais au chargement du module.
        limite = fields.Datetime.now() - timedelta(hours=self.SEUIL_SILENCE_HEURES)
        for source in self:
            # ⚠️ Une source qui n'a JAMAIS reçu de lot est silencieuse, pas
            # « neuve » : c'est le cas de l'enrôlement qui n'a jamais abouti, et
            # celui qu'on découvre le plus tard.
            source.silencieux = not source.last_seen or source.last_seen < limite

    def _search_silencieux(self, operator, value):
        limite = fields.Datetime.now() - timedelta(hours=self.SEUIL_SILENCE_HEURES)
        muettes = self.search(['|', ('last_seen', '=', False),
                               ('last_seen', '<', limite)])
        positif = (operator == '=') == bool(value)
        return [('id', 'in' if positif else 'not in', muettes.ids)]

    @staticmethod
    def empreinte(jeton):
        return hashlib.sha256((jeton or '').encode('utf-8')).hexdigest()

    def action_generer_jeton(self):
        """Génère un jeton neuf et le montre **une seule fois**.

        Régénérer révoque l'ancien : l'authentification compare l'empreinte, il
        n'y a pas de second jeton valide.
        """
        self.ensure_one()
        jeton = secrets.token_urlsafe(32)
        self.sudo().write({'token_hash': self.empreinte(jeton)})
        assistant = self.env['echango.promo.token.wizard'].create({
            'source_id': self.id,
            'token': jeton,
        })
        return {
            'type': 'ir.actions.act_window',
            'name': _("Jeton de synchronisation"),
            'res_model': 'echango.promo.token.wizard',
            'res_id': assistant.id,
            'view_mode': 'form',
            'target': 'new',
        }

    @api.ondelete(at_uninstall=False)
    def _empecher_suppression_si_donnees(self):
        for source in self:
            if self.env['echango.promo.account'].search_count(
                    [('source_id', '=', source.id)]):
                raise UserError(_(
                    "Cette source porte des fiches de suivi. La désactiver "
                    "coupe la synchronisation sans rien perdre ; la supprimer "
                    "détacherait les fiches de leur origine."
                ))
