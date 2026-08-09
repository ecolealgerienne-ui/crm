# -*- coding: utf-8 -*-
import logging
import re

from odoo import api, fields, models

_logger = logging.getLogger(__name__)

# Nombre de chiffres significatifs comparés pour rapprocher un numéro d'un
# contact. Neuf, parce qu'un mobile algérien s'écrit indifféremment
# 0555000000, +213555000000 ou 00213555000000 : ce qui reste stable, ce sont
# les neuf derniers chiffres. Comparer davantage ferait échouer le
# rapprochement selon la forme saisie dans la fiche contact.
CHIFFRES_SIGNIFICATIFS = 9

# Colonnes susceptibles de porter un numéro, par ordre de préférence.
#
# ⚠️ Écrire ces noms en dur serait une erreur : `mobile` a DISPARU de
# res.partner et de crm.lead en Odoo 19 (vérifié le 2026-08-09, seul `phone`
# subsiste), et une requête sur une colonne absente échoue au lieu de ne rien
# trouver. La liste est donc filtrée à l'exécution sur les champs réellement
# stockés — `mobile` y reste pour les versions qui l'ont encore.
#
# `phone_sanitized` est la normalisation E.164 calculée et stockée par Odoo.
# Elle vaut mieux que le champ libre quand elle est renseignée, mais elle est
# NULL dès qu'Odoo n'a pas su déduire le pays : on interroge donc les deux.
COLONNES_TELEPHONE = ('phone_sanitized', 'phone', 'mobile')


def chiffres_significatifs(numero):
    """Réduit un numéro à ses derniers chiffres, indépendamment de la mise en forme.

    Retourne une chaîne vide si le numéro est trop court pour être rapproché
    de quoi que ce soit — mieux vaut aucun rattachement qu'un rattachement au
    hasard sur trois chiffres.
    """
    if not numero:
        return ''
    chiffres = re.sub(r'\D', '', numero)
    if len(chiffres) < CHIFFRES_SIGNIFICATIFS:
        return ''
    return chiffres[-CHIFFRES_SIGNIFICATIFS:]


class CallTrackerLog(models.Model):
    _name = 'call.tracker.log'
    _description = "Appel journalisé par le Call Tracker"
    _order = 'started_at desc, id desc'
    _rec_name = 'phone_number'

    # ── Identité de l'événement ──────────────────────────────────────────────
    # Fourni par l'app mobile, unique par appel. C'est LA clé d'idempotence.
    #
    # ⚠️ Elle n'est pas une précaution théorique. L'app garde une file locale
    # persistante et réémet ce qu'elle n'a pas pu livrer : les réessais sont
    # certains, pas hypothétiques. Sans l'unicité posée ci-dessous, chaque
    # coupure réseau produirait des appels en double dans le CRM.
    client_event_id = fields.Char(
        string="Identifiant d'événement",
        required=True,
        readonly=True,
        index=True,
        copy=False,
    )

    device_id = fields.Many2one(
        'call.tracker.device',
        string="Appareil",
        required=True,
        readonly=True,
        ondelete='restrict',
        index=True,
    )
    # Stocké et non related : l'appel doit rester attribué au commercial qui
    # l'a passé, même si l'appareil change de main plus tard.
    user_id = fields.Many2one(
        'res.users',
        string="Commercial",
        required=True,
        readonly=True,
        ondelete='restrict',
        index=True,
    )

    # ── L'appel ──────────────────────────────────────────────────────────────
    phone_number = fields.Char(string="Numéro", required=True, readonly=True)
    phone_key = fields.Char(
        string="Clé de rapprochement",
        readonly=True,
        index=True,
        help="Derniers chiffres du numéro, servant à retrouver le contact.",
    )
    direction = fields.Selection(
        [('inbound', "Entrant"), ('outbound', "Sortant"), ('missed', "Manqué")],
        required=True,
        readonly=True,
    )
    duration_seconds = fields.Integer(string="Durée (s)", readonly=True)
    started_at = fields.Datetime(string="Début", required=True, readonly=True)

    # ── Rattachement ─────────────────────────────────────────────────────────
    partner_id = fields.Many2one('res.partner', string="Contact", index=True)
    lead_id = fields.Many2one('crm.lead', string="Piste", index=True)

    def init(self):
        """Contrainte d'unicité posée en SQL plutôt que via ``_sql_constraints``.

        L'API déclarative des contraintes a bougé entre versions récentes
        d'Odoo ; un index SQL créé ici se comporte de la même façon partout,
        et c'est exactement la garantie recherchée : deux insertions
        concurrentes du même ``client_event_id`` — deux réessais de l'app qui
        se croisent — ne peuvent pas passer toutes les deux.
        """
        self.env.cr.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS call_tracker_log_client_event_id_uniq
            ON call_tracker_log (client_event_id)
        """)

    @api.model_create_multi
    def create(self, liste_valeurs):
        for valeurs in liste_valeurs:
            valeurs['phone_key'] = chiffres_significatifs(valeurs.get('phone_number'))
        appels = super().create(liste_valeurs)
        appels._rattacher()
        return appels

    def _rattacher(self):
        """Associe chaque appel au contact et à la piste correspondants."""
        for appel in self:
            if not appel.phone_key:
                continue
            partenaire = appel._chercher_partenaire()
            if partenaire:
                appel.partner_id = partenaire
            appel.lead_id = appel._chercher_piste(partenaire)

    def _condition_telephone(self, nom_modele):
        """Fragment SQL « un de ces numéros finit par la clé », et ses paramètres.

        Ne retient que les champs réellement STOCKÉS : ``_fields`` contient
        aussi des champs calculés non stockés (``phone_mobile_search``,
        ``phone_blacklisted``) qui n'ont pas de colonne, et les interroger
        ferait échouer la requête.
        """
        champs = self.env[nom_modele]._fields
        colonnes = [c for c in COLONNES_TELEPHONE if c in champs and champs[c].store]
        if not colonnes:
            return None, []
        condition = ' OR '.join(
            "regexp_replace(coalesce(%s, ''), '\\D', '', 'g') LIKE %%s" % colonne
            for colonne in colonnes
        )
        return condition, ['%' + self.phone_key] * len(colonnes)

    def _chercher_partenaire(self):
        """Retrouve un ``res.partner`` dont le téléphone finit par la même clé.

        Le rapprochement se fait sur les chiffres du numéro, la mise en forme
        des fiches contact étant libre (espaces, points, indicatif ou non).
        Aucun index ne couvre cette expression : à l'échelle du carnet
        d'adresses d'une PME c'est sans conséquence, mais c'est le premier
        endroit à revoir si le rapprochement ralentit.
        """
        self.ensure_one()
        Partenaire = self.env['res.partner']
        condition, parametres = self._condition_telephone('res.partner')
        if not condition:
            return Partenaire
        self.env.cr.execute(
            "SELECT id FROM res_partner WHERE active = true AND (%s) "
            "ORDER BY id LIMIT 1" % condition,
            parametres,
        )
        ligne = self.env.cr.fetchone()
        return Partenaire.browse(ligne[0]) if ligne else Partenaire

    def _chercher_piste(self, partenaire):
        """Piste ouverte la plus récente pour ce contact, sinon pour ce numéro."""
        self.ensure_one()
        Piste = self.env['crm.lead']
        if partenaire:
            piste = Piste.search(
                [('partner_id', '=', partenaire.id), ('active', '=', True)],
                order='write_date desc', limit=1,
            )
            if piste:
                return piste
        # Une piste peut porter un numéro sans être encore reliée à un contact.
        condition, parametres = self._condition_telephone('crm.lead')
        if not condition:
            return Piste
        self.env.cr.execute(
            "SELECT id FROM crm_lead WHERE active = true AND (%s) "
            "ORDER BY write_date DESC LIMIT 1" % condition,
            parametres,
        )
        ligne = self.env.cr.fetchone()
        return Piste.browse(ligne[0]) if ligne else Piste
