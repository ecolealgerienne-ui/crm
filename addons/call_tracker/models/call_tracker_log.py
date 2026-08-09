# -*- coding: utf-8 -*-
import logging
import os
import re
from datetime import timedelta

from markupsafe import Markup

from odoo import _, api, fields, models
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
        for valeurs in liste_valeurs:
            valeurs['phone_key'] = chiffres_significatifs(valeurs.get('phone_number'))
        appels = super().create(liste_valeurs)
        appels._rattacher()
        appels._publier_note()
        return appels

    def _publier_note(self):
        """Reporte la note de l'appel dans le fil de discussion du CRM.

        Sans cela, la note resterait enfermée dans un modèle technique que
        personne n'ouvre. Publiée sur la piste — ou à défaut sur le contact —
        elle apparaît là où le commercial travaille, et **elle revient à
        l'app** : c'est ce même fil que lit ``fiche_contact`` pour alimenter
        le Caller ID. La note écrite après un appel s'affiche donc au suivant.

        Type ``comment`` et sous-type ``mt_note`` : une note interne, pas un
        message envoyé au client. Se tromper ici notifierait le contact.
        """
        for appel in self:
            if not appel.note:
                continue
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
                body=Markup('<p>%s</p><p>%s</p>') % (entete, appel.note),
                message_type='comment',
                subtype_xmlid='mail.mt_note',
                # Attribuée au commercial, pas au compte technique : le fil
                # doit dire QUI a passé l'appel.
                author_id=appel.user_id.partner_id.id or False,
            )

    def _rattacher(self):
        """Associe chaque appel au contact et à la piste correspondants.

        Si le numéro n'est connu ni comme contact ni comme piste, une piste est
        créée — décision du 2026-08-09 (spec §10.2).
        """
        for appel in self:
            if not appel.phone_key:
                continue
            partenaire = self._chercher_partenaire(appel.phone_key)
            if partenaire:
                appel.partner_id = partenaire
            piste = self._chercher_piste(appel.phone_key, partenaire)
            appel.lead_id = piste or appel._creer_piste()

    def _creer_piste(self):
        """Crée une piste pour un numéro totalement inconnu.

        ⚠️ Uniquement quand il n'y a NI contact NI piste. Un contact connu sans
        piste ouverte n'est pas un numéro inconnu : lui en créer une
        rouvrirait une affaire à chaque appel de suivi.

        Le doublon se règle tout seul : la piste porte le numéro, donc le
        deuxième appel du même inconnu la retrouve par ``_chercher_piste``.
        """
        self.ensure_one()
        if self.partner_id:
            return self.env['crm.lead']

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
            # Le test porte sur le COMMERCIAL, pas sur `env.user` : l'appel
            # arrive par une route sans session, où `env.user` est un compte
            # technique dont l'appartenance aux groupes ne dit rien de ce que
            # voit l'équipe commerciale.
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

    @api.model
    def _chercher_partenaire(self, cle):
        """Retrouve un ``res.partner`` dont le téléphone finit par la même clé.

        Le rapprochement se fait sur les chiffres du numéro, la mise en forme
        des fiches contact étant libre (espaces, points, indicatif ou non).
        Aucun index ne couvre cette expression : à l'échelle du carnet
        d'adresses d'une PME c'est sans conséquence, mais c'est le premier
        endroit à revoir si le rapprochement ralentit.
        """
        Partenaire = self.env['res.partner']
        condition, parametres = self._condition_telephone('res.partner', cle)
        if not condition:
            return Partenaire
        self.env.cr.execute(
            "SELECT id FROM res_partner WHERE active = true AND (%s) "
            "ORDER BY id LIMIT 1" % condition,
            parametres,
        )
        ligne = self.env.cr.fetchone()
        return Partenaire.browse(ligne[0]) if ligne else Partenaire

    @api.model
    def _chercher_piste(self, cle, partenaire=None):
        """Piste ouverte la plus récente pour ce contact, sinon pour ce numéro."""
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
            "ORDER BY write_date DESC LIMIT 1" % condition,
            parametres,
        )
        ligne = self.env.cr.fetchone()
        return Piste.browse(ligne[0]) if ligne else Piste

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

        partenaire = self._chercher_partenaire(cle)
        piste = self._chercher_piste(cle, partenaire)
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
          l'écran de bruit à chaque sonnerie ;
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
