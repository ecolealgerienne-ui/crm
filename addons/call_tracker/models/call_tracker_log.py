# -*- coding: utf-8 -*-
import logging
import os
import re
from datetime import timedelta

import pytz
from markupsafe import Markup

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import html2plaintext

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


def est_international(numero):
    """Le numéro porte-t-il explicitement un indicatif pays ?

    `+213…` ou `00213…`. Un numéro national — `0555…` — n'en porte pas, et
    c'est précisément le cas qui a imposé de ne comparer que les derniers
    chiffres.
    """
    return bool(numero) and (numero.strip().startswith('+')
                             or re.sub(r'\D', '', numero).startswith('00'))


def chiffres_internationaux(numero):
    """Tous les chiffres d'un numéro international, indicatif compris.

    `00` de tête retiré : `00213555…` et `+213555…` désignent le même
    correspondant et doivent se comparer à l'identique.
    """
    chiffres = re.sub(r'\D', '', numero or '')
    return chiffres[2:] if chiffres.startswith('00') else chiffres


def pays_incompatibles(a, b):
    """Deux numéros INTERNATIONAUX qui ne désignent pas le même correspondant.

    ⚠️ **Le garde-fou qui manquait au rapprochement.** La clé de rapprochement
    ne retient que les 9 derniers chiffres — voir `CHIFFRES_SIGNIFICATIFS` —
    et deux pays différents peuvent parfaitement la partager :

        Algérie  +213 555 12 34 56   ->  555123456
        Dubaï    +971 55 512 3456    ->  555123456

    Sans ce contrôle, un appel dubaïote se rattachait au client algérien, et
    publiait une note dans son fil. Silencieusement : rien dans l'interface ne
    distingue un rattachement juste d'un rattachement faux.

    **Ne mord que si les DEUX numéros portent un indicatif.** Dès que l'un des
    deux est national, on ne sait pas de quel pays il vient et on retombe sur
    la comparaison par les derniers chiffres — le comportement d'origine, celui
    qui fait qu'un `0555…` saisi dans une fiche retrouve un `+213555…` reçu du
    téléphone. Ce garde-fou ne peut donc que RETIRER des rapprochements entre
    pays différents, jamais en casser un qui marchait.
    """
    if not (est_international(a) and est_international(b)):
        return False
    return chiffres_internationaux(a) != chiffres_internationaux(b)


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

    # Ce que le commercial verra au prochain appel de ce numéro. Affiché sur
    # la fiche de l'appel pour donner le contexte sans naviguer.
    #
    # **Non stocké**, et c'est le point : le fil grossit après l'appel, et une
    # copie figée dirait « dernière note » en montrant l'avant-dernière. Le
    # champ n'est donc ni filtrable ni groupable — ce qu'on veut, il n'a rien
    # à faire dans un tableau croisé.
    last_note = fields.Text(
        string="Dernière note du client",
        compute='_compute_last_note',
        help="Dernier commentaire du fil du client ou de la piste. "
             "C'est ce texte qui s'affiche sur le téléphone à la sonnerie.",
    )

    def _compute_last_note(self):
        for appel in self:
            appel.last_note = self._derniere_note(appel.partner_id, appel.lead_id)

    # ── Champs dérivés, pour l'analyse ───────────────────────────────────────
    # Stockés : ils servent de colonnes de regroupement dans les tableaux
    # croisés, ce qu'un champ calculé non stocké ne permet pas.

    outcome = fields.Selection(
        [('answered', "Répondu"), ('no_answer', "Sans réponse")],
        string="Issue",
        compute='_compute_outcome',
        store=True,
        index=True,
    )
    hour_of_day = fields.Integer(
        string="Heure locale",
        compute='_compute_hour_of_day',
        store=True,
        index=True,
        help="Heure de l'appel dans le fuseau du commercial, de 0 à 23.",
    )
    # Figé à la création, et surtout PAS un champ related : le modèle est
    # recopié au moment de l'appel. Un related, même stocké, serait réécrit le
    # jour où le commercial change de téléphone — et toute la distribution des
    # délais passés basculerait rétroactivement sur le nouveau modèle, en
    # effaçant justement ce qu'on cherchait à mesurer.
    device_model = fields.Char(
        string="Modèle d'appareil",
        readonly=True,
        index=True,
        help="Modèle de l'appareil au moment de l'appel. Sert à rapporter le "
             "délai de remise par modèle, les surcouches constructeur n'ayant "
             "pas toutes le même appétit pour suspendre les applications.",
    )

    delivery_lag_minutes = fields.Integer(
        string="Délai de remise (min)",
        compute='_compute_delivery_lag',
        store=True,
        help="Minutes écoulées entre l'appel et son arrivée dans Odoo.",
    )

    @api.depends('duration_seconds', 'direction')
    def _compute_outcome(self):
        """Répondu ou non — et ce n'est PAS la direction.

        ⚠️ Un appel sortant qui sonne dans le vide est journalisé par Android
        en `outbound` avec une durée nulle : `missed` ne concerne que les
        entrants. Sans ce champ, le taux de décroché est donc faux pour toute
        l'activité sortante, qui est justement celle qu'un manager regarde.

        Une sélection et non un booléen : dans un tableau croisé, des colonnes
        « Vrai » / « Faux » ne se lisent pas.
        """
        for appel in self:
            appel.outcome = 'answered' if appel.duration_seconds > 0 else 'no_answer'

    @api.depends('started_at', 'user_id')
    def _compute_hour_of_day(self):
        """Heure de l'appel, dans le fuseau du COMMERCIAL.

        Ce champ existe parce que le regroupement natif par heure produit
        « 9 août 14 h », pas « 14 h toutes dates confondues » : la répartition
        horaire d'une journée type n'est pas atteignable autrement.

        ⚠️ En revanche, **aucun champ « numéro de semaine » n'est ajouté** :
        Odoo groupe déjà nativement par jour, semaine, mois et trimestre, et il
        le fait dans le fuseau de l'utilisateur. Un champ stocké serait calculé
        en UTC — un appel du dimanche 23 h 30 à Alger tomberait dans la mauvaise
        semaine — et on aurait deux façons de compter la même chose qui ne
        concordent pas.

        Le fuseau retenu est celui du commercial, à défaut celui de la session,
        à défaut UTC : l'heure qui a un sens ici est celle vécue par la
        personne qui passe l'appel. La valeur est figée à l'écriture ; changer
        le fuseau d'un commercial ne réécrit pas son historique.
        """
        for appel in self:
            if not appel.started_at:
                appel.hour_of_day = 0
                continue
            fuseau = appel.user_id.tz or self.env.context.get('tz') or 'UTC'
            try:
                local = pytz.timezone(fuseau)
            except pytz.UnknownTimeZoneError:
                local = pytz.utc
            appel.hour_of_day = pytz.utc.localize(appel.started_at).astimezone(local).hour

    @api.depends('started_at', 'create_date')
    def _compute_delivery_lag(self):
        """Minutes entre l'appel et son arrivée dans Odoo.

        La mesure qui doit précéder tout classement entre commerciaux.

        Quand une surcouche constructeur suspend l'application, le receveur
        n'est plus délivré et rien ne remonte — mais le journal du téléphone
        continue d'être écrit, et le balayage repart d'un curseur qui n'avance
        que sur ce qui a été lu. **Au réveil suivant, tout est rattrapé.** Le
        risque n'est donc pas la perte, c'est le retard : un total mensuel
        reste juste, un chiffre journalier et une alerte de seuil ne le sont
        pas.

        Rapporté par appareil, ce délai dit immédiatement quel téléphone
        décroche du reste. Voir docs/REPORTING_KPI.md.
        """
        for appel in self:
            if not appel.started_at or not appel.create_date:
                appel.delivery_lag_minutes = 0
                continue
            ecart = appel.create_date - appel.started_at
            # Un appel remonté « avant » d'avoir eu lieu signale une horloge de
            # téléphone déréglée. On borne à zéro plutôt que d'afficher un
            # délai négatif, qui fausserait toute moyenne.
            appel.delivery_lag_minutes = max(0, int(ecart.total_seconds() // 60))

    # ── Note prise après l'appel ─────────────────────────────────────────────
    # Saisie par le commercial sur son téléphone, juste après avoir raccroché.
    # Facultative : l'immense majorité des appels n'en portera pas, et exiger
    # une saisie ferait abandonner la fonctionnalité en une semaine.
    note = fields.Text(string="Note")

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
        Appareil = self.env['call.tracker.device']
        for valeurs in liste_valeurs:
            valeurs['phone_key'] = chiffres_significatifs(valeurs.get('phone_number'))
            # Recopié depuis l'appareil, une fois pour toutes. Voir le champ.
            if valeurs.get('device_id') and not valeurs.get('device_model'):
                valeurs['device_model'] = Appareil.browse(
                    valeurs['device_id']
                ).device_model or False
        appels = super().create(liste_valeurs)
        appels._rattacher()
        appels._publier_note()
        return appels

    def _publier_note(self):
        """Trace l'appel dans le fil de discussion du CRM.

        **Tout appel rattaché est tracé**, entrant comme sortant, avec ou sans
        note. C'est là que le commercial et son responsable travaillent : un
        appel qui n'existe que dans un modèle technique que personne n'ouvre
        n'a, en pratique, pas eu lieu. Ouvrir une fiche client doit suffire à
        voir qu'on l'a appelé mardi.

        Publiée sur la piste — ou à défaut sur le contact. Sous-type
        ``mt_note`` dans les deux cas : une note **interne**, jamais un message
        envoyé au client. Se tromper ici notifierait le contact.

        ⚠️ **Deux types de message, et la distinction est le cœur de cette
        méthode.** Ce même fil est relu par ``_derniere_note`` pour alimenter
        le Caller ID : ce que le commercial voit s'afficher à la sonnerie
        suivante, c'est le dernier ``comment`` de ce fil.

        - Appel **avec note** → ``comment``. Ce sont les mots d'un humain, ce
          qu'on veut relire avant de décrocher.
        - Appel **sans note** → ``notification``. Une trace automatique, au
          même titre qu'un changement d'étape. Sans cette distinction, chaque
          appel muet écraserait au Caller ID la dernière note utile par un
          « Appel sortant — +213… » qui n'apprend rien à personne. Le défaut
          serait discret : la fiche resterait remplie, mais vide de sens.
        """
        for appel in self:
            cible = appel.lead_id or appel.partner_id
            if not cible:
                continue
            libelles = dict(self._fields['direction'].selection)
            entete = _("Appel %(sens)s — %(numero)s") % {
                'sens': (libelles.get(appel.direction) or '').lower(),
                'numero': appel.phone_number,
            }
            # ⚠️ Pas de <b> sur l'en-tête, et ce n'est pas un oubli de mise en
            # forme. Ce message est relu par `_derniere_note` pour alimenter le
            # Caller ID, et `html2plaintext` rend le gras en « *texte* » : la
            # fiche affichée sur le téléphone montrait des astérisques au
            # milieu de la note. Le lecteur final compte plus que l'emphase
            # dans le fil.
            cible.sudo().message_post(
                body=Markup('<p>%s</p><p>%s</p>') % (
                    entete, appel.note or appel._resume_sans_note(),
                ),
                message_type='comment' if appel.note else 'notification',
                subtype_xmlid='mail.mt_note',
                # Attribuée au commercial, pas au compte technique : le fil
                # doit dire QUI a passé l'appel.
                author_id=appel.user_id.partner_id.id or False,
            )

    def _resume_sans_note(self):
        """Corps du message pour un appel sans note : durée et issue.

        « 45 s · répondu » plutôt qu'un message vide. Le fil doit répondre à
        « l'a-t-on eu au téléphone ? » sans ouvrir l'appel.
        """
        self.ensure_one()
        issues = dict(self._fields['outcome'].selection)
        if self.duration_seconds:
            return _("%(duree)s s · %(issue)s") % {
                'duree': self.duration_seconds,
                'issue': (issues.get(self.outcome) or '').lower(),
            }
        return (issues.get(self.outcome) or '').capitalize()

    def _rattacher(self):
        """Associe chaque appel au contact et à la piste correspondants.

        ⚠️ **Aucune piste n'est créée automatiquement** — décision du
        2026-08-09, qui revient sur le premier choix.

        Une création automatique remplit le pipeline de taxis, de fournisseurs
        et de faux numéros ; les rapports deviennent faux, et un pipeline qu'on
        ne croit plus, personne ne le regarde. Un appel sans correspondance
        reste donc non rattaché et rejoint la file « Appels à qualifier », où
        un humain décide — c'est la troisième option de la spec §10.2, la
        validation manuelle.

        Le risque de cette approche est de perdre un prospect entrant, qui ne
        peut pas avoir été créé à l'avance. Il est traité par la visibilité de
        cette file, pas par une création aveugle : voir
        ``action_call_tracker_a_qualifier``.
        """
        for appel in self:
            if not appel.phone_key:
                continue
            partenaire = self._chercher_partenaire(
                appel.phone_key, appel.phone_number,
            )
            if partenaire:
                appel.partner_id = partenaire
            appel.lead_id = self._chercher_piste(
                appel.phone_key, partenaire, appel.phone_number,
            )

    # ── Qualification manuelle ───────────────────────────────────────────────

    def action_creer_piste(self):
        """Crée une piste depuis un appel non rattaché, et l'ouvre.

        Le geste que remplace l'ancienne création automatique : un clic, mais
        un clic humain.
        """
        self.ensure_one()
        if not self.lead_id:
            self.lead_id = self._creer_piste()
            self._rattacher_appels_du_meme_numero()
            # ⚠️ Publier MAINTENANT, et pas seulement à la création de l'appel.
            #
            # `_publier_note` tourne dans `create()`, où un appel entrant d'un
            # numéro inconnu n'a encore ni contact ni piste : il n'a donc rien
            # à quoi se rattacher, et ne publie rien. C'est justement le
            # chemin normal d'un prospect — appel d'un inconnu, puis
            # qualification. Sans cette ligne, ces appels-là étaient les SEULS
            # à ne jamais apparaître dans un fil, ni leur note à revenir au
            # Caller ID. Le défaut ne se voyait pas sur les appels de clients
            # déjà connus, c'est-à-dire pendant tous les essais.
            #
            # Constaté le 2026-08-10 : une note prise sur un appel sortant
            # introuvable sur la fiche du client créé juste après.
            self._publier_note()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'crm.lead',
            'res_id': self.lead_id.id,
            'view_mode': 'form',
        }

    def action_ouvrir_client(self):
        """Ouvre la piste, ou à défaut la fiche contact, de cet appel.

        Le chemin existait, rien ne le montrait. C'est là que se fait
        l'enrichissement : ce qui s'écrit dans ce fil revient au téléphone à
        la sonnerie suivante.
        """
        self.ensure_one()
        cible = self.lead_id or self.partner_id
        if not cible:
            raise UserError(_(
                "Cet appel n'est rattaché à aucun client ni à aucune piste."
            ))
        return {
            'type': 'ir.actions.act_window',
            'res_model': cible._name,
            'res_id': cible.id,
            'view_mode': 'form',
        }

    def action_completer_note(self):
        """Ouvre l'assistant qui publie une note dans le fil du client.

        ⚠️ La note va au fil du client, **pas** sur l'appel. L'appel est le
        compte rendu d'un événement, figé ; le fil est l'histoire de la
        relation, cumulative. Voir ``call.tracker.note.wizard``.
        """
        self.ensure_one()
        cible = self.lead_id or self.partner_id
        if not cible:
            raise UserError(_(
                "Cet appel n'est rattaché à aucun client ni à aucune piste. "
                "Qualifiez-le d'abord : la note n'aurait nulle part où aller."
            ))
        assistant = self.env['call.tracker.note.wizard'].create({
            'call_id': self.id,
            'target_name': cible.display_name,
        })
        return {
            'type': 'ir.actions.act_window',
            'name': _("Compléter la note"),
            'res_model': 'call.tracker.note.wizard',
            'res_id': assistant.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def _rattacher_appels_du_meme_numero(self):
        """Qualifier un appel qualifie tous ceux du même numéro.

        Sans cela, un prospect qui a rappelé trois fois laisserait deux appels
        dans la file après qualification, et il faudrait recommencer le geste
        pour chacun — la file ne se viderait jamais vraiment.
        """
        self.ensure_one()
        if not self.lead_id or not self.phone_key:
            return
        autres = self.search([
            ('id', '!=', self.id),
            ('phone_key', '=', self.phone_key),
            ('lead_id', '=', False),
            ('partner_id', '=', False),
        ])
        autres.write({'lead_id': self.lead_id.id})
        # Eux aussi arrivent au fil : ils viennent d'être rattachés, et leurs
        # notes valent celle qui a déclenché la qualification.
        autres._publier_note()

    def _creer_piste(self):
        """Construit la piste correspondant à cet appel."""
        self.ensure_one()
        libelles = dict(self._fields['direction'].selection)
        valeurs = {
            'name': "%s — %s" % (libelles.get(self.direction, ''), self.phone_number),
            'phone': self.phone_number,
            # Attribuée au commercial qui a passé ou reçu l'appel : c'est lui
            # qui a le contexte, et lui seul saura quoi en faire.
            'user_id': self.user_id.id,
            # `lead` si le client a activé l'étape de qualification, sinon
            # `opportunity`. Créer un `lead` sur une base où la fonction est
            # désactivée le rendrait INVISIBLE : le menu correspondant est
            # masqué, et la piste n'apparaîtrait dans aucun écran.
            #
            # Le test porte sur le COMMERCIAL de l'appel, pas sur celui qui
            # clique : la piste doit apparaître là où SON propriétaire la
            # cherchera, pas là où la voit un administrateur de passage.
            'type': 'lead' if self.user_id.has_group('crm.group_use_lead')
                    else 'opportunity',
        }
        medium = self.env.ref('utm.utm_medium_phone', raise_if_not_found=False)
        if medium:
            valeurs['medium_id'] = medium.id

        piste = self.env['crm.lead'].sudo().create(valeurs)
        _logger.info(
            "Call Tracker : piste %s creee pour le numero inconnu %s",
            piste.id, self.phone_number,
        )
        return piste

    @api.model
    def _condition_telephone(self, nom_modele, cle):
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
        return condition, ['%' + cle] * len(colonnes)

    #: Candidats ramenés avant le filtre par pays. La clé de 9 chiffres écarte
    #: déjà l'immense majorité du carnet ; ce qui reste tient largement là.
    CANDIDATS_MAX = 20

    @api.model
    def _compatible(self, enregistrement, numero):
        """L'un des numéros de cet enregistrement peut-il être `numero` ?

        Faux uniquement quand TOUS ses numéros portent un indicatif pays qui
        contredit celui de `numero`. Voir `pays_incompatibles`.
        """
        if not numero:
            return True
        valeurs = [
            enregistrement[c] for c in COLONNES_TELEPHONE
            if c in enregistrement._fields and enregistrement[c]
        ]
        if not valeurs:
            return True
        return any(not pays_incompatibles(numero, v) for v in valeurs)

    @api.model
    def _chercher_partenaire(self, cle, numero=None):
        """Retrouve un ``res.partner`` dont le téléphone finit par la même clé.

        Le rapprochement se fait sur les chiffres du numéro, la mise en forme
        des fiches contact étant libre (espaces, points, indicatif ou non).
        Aucun index ne couvre cette expression : à l'échelle du carnet
        d'adresses d'une PME c'est sans conséquence, mais c'est le premier
        endroit à revoir si le rapprochement ralentit.

        `numero` — le numéro complet, tel qu'il a été composé ou reçu — sert au
        garde-fou par indicatif pays : sans lui, un `+971555123456` se
        rattacherait au client algérien `+213555123456`, les deux partageant
        les mêmes 9 derniers chiffres. Facultatif pour ne pas casser les
        appelants qui n'ont que la clé, mais tous ceux du module le passent.
        """
        Partenaire = self.env['res.partner']
        condition, parametres = self._condition_telephone('res.partner', cle)
        if not condition:
            return Partenaire
        self.env.cr.execute(
            "SELECT id FROM res_partner WHERE active = true AND (%s) "
            "ORDER BY id LIMIT %%s" % condition,
            parametres + [self.CANDIDATS_MAX],
        )
        for (identifiant,) in self.env.cr.fetchall():
            candidat = Partenaire.browse(identifiant)
            if self._compatible(candidat, numero):
                return candidat
        return Partenaire

    # ── Recherche par fragment, depuis l'application ─────────────────────────

    #: En deçà, la recherche est refusée. Trois chiffres rendraient un
    #: échantillon du carnet d'adresses à qui tape n'importe quoi ; quatre
    #: suffisent à cibler un correspondant qu'on a en tête.
    FRAGMENT_MIN = 4

    #: Plafond de résultats. Ce n'est pas de la pagination oubliée : c'est la
    #: borne. Un écran de téléphone n'affiche pas davantage, et surtout un
    #: jeton volé ne doit pas pouvoir aspirer le carnet dix par dix moins
    #: lentement que ça.
    RESULTATS_MAX = 10

    #: Périmètre par défaut quand la variable d'environnement est absente.
    #: `all` = le comportement historique, celui des instances déjà déployées.
    PERIMETRE_DEFAUT = 'all'

    @api.model
    def _perimetre_recherche(self):
        """`all` ou `own` — jusqu'où va la recherche depuis l'application.

        `CALL_TRACKER_SEARCH_SCOPE`, dans le `.env` du serveur, au même endroit
        que la durée de rétention. Un réglage de cette portée n'a rien à faire
        dans une interface où personne ne le retrouverait le jour où il faut
        répondre à une question de conformité.

        - `all` — tout le carnet d'adresses, comportement historique et défaut.
        - `own` — les clients du commercial de l'appareil, et ceux des
          affaires qui lui sont assignées.

        ⚠️ **Les deux replis ne vont pas dans le même sens, et c'est voulu.**

        Variable *absente* → `all` : ne rien configurer est une situation
        normale, et changer le comportement sous les pieds d'un exploitant qui
        n'a rien demandé serait pire que de le laisser tel quel.

        Valeur *illisible* → `own` : c'est une erreur, et une faute de frappe
        ne doit pas ouvrir le carnet d'adresses en silence. Restreindre à tort
        se remarque en une heure — un commercial ne retrouve plus ses clients.
        Ouvrir à tort ne se remarque jamais.

        ⚠️ **Ne s'applique qu'à la recherche par fragment.** La fiche à la
        sonnerie reste ouverte quel que soit ce réglage : quand le téléphone
        sonne, il faut savoir qui appelle, même si la fiche appartient à un
        collègue. Afficher « inconnu » ferait décrocher à l'aveugle — pire que
        de ne rien afficher du tout.
        """
        brut = (os.environ.get('CALL_TRACKER_SEARCH_SCOPE') or '').strip().lower()
        if not brut:
            return self.PERIMETRE_DEFAUT
        if brut in ('all', 'own'):
            return brut
        _logger.warning(
            "Call Tracker : CALL_TRACKER_SEARCH_SCOPE=%r illisible, "
            "recherche restreinte au portefeuille du commercial", brut,
        )
        return 'own'

    @api.model
    def rechercher_contacts(self, fragment, limite=None, commercial=None):
        """Contacts dont le numéro contient ce fragment de chiffres.

        Sert la recherche manuelle de l'application, distincte du Caller ID :
        celui-ci part d'un numéro complet et rend UNE fiche, celle-ci part
        d'un bout de numéro et rend une liste.

        **Contacts d'abord, puis pistes sans contact.** Un prospect qualifié
        depuis un appel n'existe que comme piste ; l'omettre rendait
        introuvable, dans la recherche, quelqu'un que la fiche à la sonnerie
        trouvait — et précisément au moment où on veut le rappeler. Voir
        ``_pistes_sans_contact``.

        ⚠️ **C'est la route la plus sensible du module, et il faut le dire.**
        Un fragment court interroge tout le carnet d'adresses, alors que
        l'authentification ne repose que sur un jeton d'appareil, sans droits
        Odoo. Trois bornes, et chacune répond à un scénario précis :

        - ``FRAGMENT_MIN`` — sans minimum, ``0`` rend un échantillon de tout ;
        - ``RESULTATS_MAX`` — un téléphone perdu ne doit pas vider le carnet
          en quelques requêtes ;
        - la trace d'audit, écrite par le contrôleur avec le fragment ET le
          nombre de résultats — une énumération laisse alors une signature
          lisible : des centaines de recherches courtes en rafale.

        Elles limitent le débit, **elles n'empêchent pas** une énumération
        patiente. Le jour où ça compte, c'est le périmètre qu'il faut réduire
        — restreindre aux clients du commercial de l'appareil — pas les
        bornes qu'il faut resserrer.
        """
        chiffres = re.sub(r'\D', '', fragment or '')
        if len(chiffres) < self.FRAGMENT_MIN:
            return []

        Partenaire = self.env['res.partner']
        champs = Partenaire._fields
        colonnes = [c for c in COLONNES_TELEPHONE if c in champs and champs[c].store]
        if not colonnes:
            return []

        # `LIKE %fragment%` et non `LIKE %fragment` : on cherche n'importe où
        # dans le numéro. Un commercial se souvient rarement de la fin exacte,
        # plus souvent d'un morceau du milieu.
        condition = ' OR '.join(
            "regexp_replace(coalesce(p.%s, ''), '\\D', '', 'g') LIKE %%s" % colonne
            for colonne in colonnes
        )
        parametres = ['%' + chiffres + '%'] * len(colonnes)

        # Cloisonnement, quand l'exploitant l'a demandé. Trois façons d'être
        # « à moi », et il faut les trois : la fiche m'est assignée, la SOCIÉTÉ
        # dont elle dépend m'est assignée — un interlocuteur n'a presque jamais
        # de commercial propre —, ou une affaire à mon nom la désigne : un
        # prospect n'a souvent aucun commercial sur sa fiche, seulement sur sa
        # piste, et l'oublier rendrait la recherche aveugle là où elle sert le
        # plus, sur les affaires en cours.
        cloison = ''
        if self._perimetre_recherche() == 'own' and commercial:
            cloison = """
              AND (
                p.user_id = %s
                OR EXISTS (
                    SELECT 1 FROM res_partner societe
                    WHERE societe.id = p.commercial_partner_id
                      AND societe.user_id = %s
                )
                OR EXISTS (
                    SELECT 1 FROM crm_lead affaire
                    WHERE affaire.partner_id = p.id
                      AND affaire.user_id = %s
                      AND affaire.active
                )
              )"""
            parametres += [commercial.id] * 3

        self.env.cr.execute(
            "SELECT p.id FROM res_partner p WHERE p.active = true AND (%s) %s "
            "ORDER BY p.id LIMIT %%s" % (condition, cloison),
            parametres + [min(limite or self.RESULTATS_MAX, self.RESULTATS_MAX)],
        )
        identifiants = [ligne[0] for ligne in self.env.cr.fetchall()]

        resultats = []
        for partenaire in Partenaire.browse(identifiants):
            piste = self._chercher_piste(
                chiffres_significatifs(partenaire.phone or ''), partenaire,
            )
            resultats.append({
                'name': partenaire.name or '',
                'company': self._societe(partenaire, piste),
                # Le numéro fait partie du résultat, contrairement à la fiche
                # du Caller ID : sans lui la liste est inutilisable — on ne
                # sait ni lequel choisir, ni quoi composer.
                'phone': partenaire.phone or '',
                'crm_stage': piste.stage_id.name or '' if piste else '',
            })

        reste = min(limite or self.RESULTATS_MAX, self.RESULTATS_MAX) - len(resultats)
        if reste > 0:
            resultats += self._pistes_sans_contact(chiffres, commercial, reste)
        return resultats

    @api.model
    def _pistes_sans_contact(self, chiffres, commercial, limite):
        """Prospects qui n'existent que comme piste, sans fiche contact.

        **Le trou que cette méthode bouche.** Qualifier un appel d'un numéro
        inconnu crée une PISTE, pas un contact. La fiche affichée à la sonnerie
        le trouvait — ``fiche_contact`` retombe sur ``crm.lead`` — mais la
        recherche par fragment, non : elle n'interrogeait que ``res.partner``.
        Un commercial venait donc de qualifier un prospect et ne pouvait pas le
        retrouver pour le rappeler. Constaté en rejouant les scénarios le
        2026-08-10.

        ``partner_id IS NULL`` : les pistes rattachées à un contact sont déjà
        remontées par la requête précédente, à travers ce contact. Les inclure
        ici afficherait deux fois la même personne, une fois sous son nom et
        une fois sous l'intitulé de son affaire.
        """
        champs = self.env['crm.lead']._fields
        colonnes = [c for c in COLONNES_TELEPHONE if c in champs and champs[c].store]
        if not colonnes:
            return []

        # ⚠️ `\\D` et non `\D` : dans une chaîne Python ordinaire, `\D` n'est
        # pas une séquence d'échappement connue. Python 3.12 le laisse passer
        # tel quel — le SQL produit est donc correct — mais il émet un
        # `SyntaxWarning` à CHAQUE chargement du module, qui atterrit dans les
        # journaux de production. Les deux autres requêtes de ce fichier
        # doublent l'antislash ; celle-ci l'avait oublié.
        condition = ' OR '.join(
            "regexp_replace(coalesce(l.%s, ''), '\\D', '', 'g') LIKE %%s" % colonne
            for colonne in colonnes
        )
        parametres = ['%' + chiffres + '%'] * len(colonnes)

        cloison = ''
        if self._perimetre_recherche() == 'own' and commercial:
            # Une seule façon d'être « à moi » ici, contrairement aux
            # contacts : une piste porte son commercial directement.
            cloison = ' AND l.user_id = %s'
            parametres.append(commercial.id)

        self.env.cr.execute(
            "SELECT l.id FROM crm_lead l "
            "WHERE l.active = true AND l.partner_id IS NULL AND (%s) %s "
            "ORDER BY l.id LIMIT %%s" % (condition, cloison),
            parametres + [limite],
        )
        identifiants = [ligne[0] for ligne in self.env.cr.fetchall()]

        resultats = []
        for piste in self.env['crm.lead'].browse(identifiants):
            resultats.append({
                # `contact_name` quand la piste nomme une personne, sinon son
                # intitulé — c'est ce qu'un commercial reconnaîtra.
                'name': piste.contact_name or piste.name or '',
                'company': piste.partner_name or '',
                'phone': self._premier_telephone(piste),
                'crm_stage': piste.stage_id.name or '',
            })
        return resultats

    @api.model
    def _chercher_piste(self, cle, partenaire=None, numero=None):
        """Piste ouverte la plus récente pour ce contact, sinon pour ce numéro.

        `numero` sert au même garde-fou par indicatif pays que
        `_chercher_partenaire`. Il ne s'applique qu'à la recherche PAR NUMÉRO :
        une piste trouvée par son contact l'a été sans passer par un numéro,
        et le contact, lui, a déjà été filtré.
        """
        Piste = self.env['crm.lead']
        if partenaire:
            piste = Piste.search(
                [('partner_id', '=', partenaire.id), ('active', '=', True)],
                order='write_date desc', limit=1,
            )
            if piste:
                return piste
        # Une piste peut porter un numéro sans être encore reliée à un contact.
        condition, parametres = self._condition_telephone('crm.lead', cle)
        if not condition:
            return Piste
        self.env.cr.execute(
            "SELECT id FROM crm_lead WHERE active = true AND (%s) "
            "ORDER BY write_date DESC LIMIT %%s" % condition,
            parametres + [self.CANDIDATS_MAX],
        )
        for (identifiant,) in self.env.cr.fetchall():
            candidate = Piste.browse(identifiant)
            if self._compatible(candidate, numero):
                return candidate
        return Piste

    # ── Appels à passer, depuis l'application ────────────────────────────────

    #: Plafond de la liste renvoyée au téléphone. Au-delà, ce n'est plus une
    #: liste de travail mais un arriéré qu'on ne regarde plus.
    ACTIVITES_MAX = 50

    @api.model
    def activites_a_appeler(self, commercial, limite=None):
        """Les appels programmés dans le CRM pour ce commercial.

        C'est la seule route qui rende quelque chose au commercial au lieu de
        lui prendre. Tout le reste du dispositif est rétrospectif — il capture,
        il transmet, il rapporte à un responsable. Un outil qui ne rend rien
        ne s'ouvre pas, et une application qu'on n'ouvre jamais est une
        application dont la file d'envoi ne se vide pas : constaté sur un
        OnePlus, où la tâche d'envoi n'a tourné qu'au moment où l'écran s'est
        allumé.

        ⚠️ **Le filtre porte sur `category`, pas sur le nom du type.** « Call »
        est un libellé : il se traduit, il se renomme, et une instance en
        français l'appellera « Appel ». `phonecall` est structurel — c'est ce
        qu'Odoo utilise lui-même pour décider d'afficher une icône de
        téléphone.

        ⚠️ **Le périmètre n'est pas un choix ici.** Une activité est assignée à
        un utilisateur, et l'appareil connaît le sien : la route est cloisonnée
        par la donnée elle-même. Contrairement à la recherche de contacts, il
        n'y a rien à régler et rien à débattre.
        """
        activites = self.env['mail.activity'].sudo().search(
            [
                ('user_id', '=', commercial.id),
                ('activity_type_id.category', '=', 'phonecall'),
            ],
            # Les échéances les plus anciennes d'abord : le retard passe devant
            # ce qui est prévu pour demain. `state` est calculé, donc pas
            # triable en base — mais trier par échéance produit exactement le
            # même ordre, et sans coût.
            order='date_deadline asc, id asc',
            limit=min(limite or self.ACTIVITES_MAX, self.ACTIVITES_MAX),
        )
        return [self._resume_activite(a) for a in activites]

    @api.model
    def _resume_activite(self, activite):
        client, numero = self._cible_de_l_activite(activite)
        return {
            'id': activite.id,
            'client': client,
            'phone': numero,
            'deadline': activite.date_deadline and str(activite.date_deadline) or '',
            # `overdue` / `today` / `planned`, calculé par Odoo dans le fuseau
            # de l'utilisateur. Le recalculer côté téléphone donnerait deux
            # vérités pour la même échéance.
            'state': activite.state or '',
            'summary': activite.summary or activite.activity_type_id.name or '',
            # Le HTML d'une note d'activité ne s'affiche pas sur un téléphone,
            # et 200 caractères suffisent à se rappeler pourquoi on appelle.
            'note': html2plaintext(activite.note or '').strip()[:200],
        }

    @api.model
    def _cible_de_l_activite(self, activite):
        """Nom du client et numéro à composer, quel que soit le modèle porteur.

        Une activité peut vivre sur une piste comme sur une fiche contact.
        Le numéro se cherche donc là où il est, et sur une piste il faut
        retomber sur le contact rattaché : beaucoup de pistes ne portent pas
        de numéro propre.

        Un numéro introuvable ne fait pas disparaître l'activité : elle
        s'affiche sans bouton d'appel. La masquer ferait perdre une tâche
        réelle pour un champ manquant.
        """
        if not activite.res_model or not activite.res_id:
            return activite.res_name or '', ''

        enregistrement = self.env[activite.res_model].sudo().browse(activite.res_id)
        if not enregistrement.exists():
            return activite.res_name or '', ''

        numero = self._premier_telephone(enregistrement)
        if not numero and 'partner_id' in enregistrement._fields:
            numero = self._premier_telephone(enregistrement.partner_id)

        return enregistrement.display_name or activite.res_name or '', numero

    @api.model
    def _premier_telephone(self, enregistrement):
        if not enregistrement:
            return ''
        for colonne in COLONNES_TELEPHONE:
            if colonne in enregistrement._fields:
                valeur = enregistrement[colonne]
                if valeur:
                    return valeur
        return ''

    @api.model
    def cloturer_activite(self, identifiant, commercial, retour=None):
        """Marque une activité comme faite, si elle appartient bien au commercial.

        ⚠️ **La vérification d'appartenance est le cœur de cette méthode.**
        L'application envoie un identifiant ; rien n'empêche un jeton volé
        d'en envoyer d'autres. Sans ce contrôle, un appareil clôturerait les
        activités de n'importe qui — et une tâche qui disparaît de la liste
        d'un collègue ne se remarque pas, elle s'oublie.

        Rend `False` si l'activité n'existe pas ou n'est pas la sienne : le
        contrôleur en fait un 404, indistinguable de l'un ou l'autre cas. Dire
        « elle existe mais elle n'est pas à vous » renseignerait sur le
        portefeuille des autres.
        """
        activite = self.env['mail.activity'].sudo().browse(identifiant)
        if not activite.exists() or activite.user_id != commercial:
            return False
        activite.action_feedback(feedback=retour or _("Appel passé depuis le mobile"))
        return True

    # ── Rétention ────────────────────────────────────────────────────────────

    @api.model
    def _jours_de_retention(self):
        """Durée de conservation, lue dans l'environnement du serveur.

        `CALL_TRACKER_RETENTION_DAYS`, injectée par docker-compose depuis
        `.env.production`. Le même endroit que le reste de la configuration de
        cette instance — pas un réglage caché dans une interface, où personne
        ne le retrouverait le jour où il faut répondre à une question de
        conformité.

        Absente, vide, illisible ou nulle : **aucune purge**. Un défaut de
        configuration ne doit jamais faire disparaître des données ; le sens
        de l'erreur est choisi, pas subi.
        """
        brut = (os.environ.get('CALL_TRACKER_RETENTION_DAYS') or '').strip()
        if not brut:
            return 0
        try:
            jours = int(brut)
        except ValueError:
            _logger.warning(
                "Call Tracker : CALL_TRACKER_RETENTION_DAYS=%r illisible, "
                "aucune purge n'est effectuee", brut,
            )
            return 0
        return jours if jours > 0 else 0

    @api.model
    def _purger(self):
        """Supprime les appels et les traces d'audit hors rétention.

        Appelée par une tâche planifiée quotidienne. Les deux modèles suivent
        la MÊME durée : conserver un journal d'audit plus longtemps que les
        données qu'il décrit produirait des traces orphelines, et l'inverse
        laisserait des appels sans trace de leur remise.
        """
        jours = self._jours_de_retention()
        if not jours:
            _logger.info("Call Tracker : aucune retention configuree, rien a purger")
            return 0

        limite = fields.Datetime.now() - timedelta(days=jours)

        appels = self.sudo().search([('started_at', '<', limite)])
        traces = self.env['call.tracker.audit'].sudo().search(
            [('create_date', '<', limite)]
        )
        nombre = len(appels) + len(traces)

        appels.unlink()
        traces.unlink()

        _logger.info(
            "Call Tracker : purge a %d jours — %d appel(s) et %d trace(s) supprimes",
            jours, len(appels), len(traces),
        )
        return nombre

    # ── Fiche renvoyée à l'app (Caller ID) ───────────────────────────────────

    @api.model
    def fiche_contact(self, numero):
        """Quatre champs, pas un de plus, pour l'affichage à la sonnerie.

        ⚠️ **La liste blanche est ici, en dur, et nulle part ailleurs.** Elle
        n'est pas une conséquence des droits d'un compte : le contrôleur
        travaille en ``sudo()``, il a donc accès à TOUT le contact. C'est ce
        code, et lui seul, qui décide que le courriel, l'adresse, le chiffre
        d'affaires et l'historique complet ne sortent pas — conformément au
        §3.1 de la spec, qui interdit explicitement de s'en remettre aux ACL
        d'Odoo pour ce filtrage.

        Retourne ``None`` si le numéro ne correspond à rien.
        """
        cle = chiffres_significatifs(numero)
        if not cle:
            return None

        partenaire = self._chercher_partenaire(cle, numero)
        piste = self._chercher_piste(cle, partenaire, numero)
        if not partenaire and not piste:
            return None

        return {
            'name': partenaire.name or piste.contact_name or piste.name or '',
            'company': self._societe(partenaire, piste),
            'last_notes': self._derniere_note(partenaire, piste),
            'crm_stage': piste.stage_id.name or '' if piste else '',
        }

    @api.model
    def _societe(self, partenaire, piste):
        if partenaire:
            # `parent_id` pour un contact rattaché à une société,
            # `company_name` pour une société saisie à plat sur la fiche.
            return partenaire.parent_id.name or partenaire.company_name or ''
        return piste.partner_name or '' if piste else ''

    @api.model
    def _derniere_note(self, partenaire, piste):
        """Dernier commentaire du fil de discussion, en texte brut et tronqué.

        C'est le seul champ de la fiche dont le contenu est libre, donc le seul
        qui puisse contenir n'importe quoi. Trois précautions, et chacune a sa
        raison :

        - seuls les messages de type ``comment`` sont lus. Les notifications
          automatiques (changement d'étape, courriel envoyé) rempliraient
          l'écran de bruit à chaque sonnerie. ⚠️ **Ce filtre porte plus qu'il
          n'y paraît depuis que tout appel est tracé au fil** : les appels sans
          note y sont publiés en ``notification`` précisément pour ne pas
          passer ici. L'élargir ferait afficher « Appel sortant — +213… » à la
          place de la dernière note utile, et le Caller ID perdrait sa raison
          d'être sans qu'aucune erreur ne se produise ;
        - le HTML est converti en texte : un fil Odoo est du HTML, et l'envoyer
          tel quel ferait afficher des balises sur un téléphone ;
        - la troncature à 200 caractères borne ce qui sort du CRM. Un
          commercial a besoin d'un rappel de contexte avant de décrocher, pas
          d'un dossier complet.
        """
        enregistrement = piste or partenaire
        if not enregistrement:
            return ''

        message = self.env['mail.message'].search(
            [
                ('model', '=', enregistrement._name),
                ('res_id', '=', enregistrement.id),
                ('message_type', '=', 'comment'),
                ('body', '!=', False),
            ],
            order='date desc', limit=1,
        )
        if not message:
            return ''

        texte = html2plaintext(message.body or '').strip()
        return texte[:200]
