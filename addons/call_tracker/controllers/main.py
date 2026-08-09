# -*- coding: utf-8 -*-
"""Routes exposées à l'application mobile.

``type='http'`` et non ``type='json'`` : le second impose l'enveloppe JSON-RPC
d'Odoo (``{"jsonrpc": "2.0", "params": {...}}``, réponse enrobée, erreurs
renvoyées en HTTP 200). Un client mobile veut du JSON nu et des codes HTTP qui
veulent dire quelque chose ; on lit donc le corps et on écrit la réponse
nous-mêmes.

``auth='none'`` : aucune session Odoo n'est ouverte. L'authentification est
faite ici, par jeton d'appareil, et les écritures passent en ``sudo()``. C'est
le point central du module — le jeton présenté par l'app ne porte AUCUN droit
Odoo, il ne fait que désigner un appareil. Ce qui est écrit, et ce qui est
renvoyé, est décidé par ce fichier, jamais par les droits d'un compte.
"""
import json
import logging
from datetime import datetime, timezone

import psycopg2

from odoo import fields, http
from odoo.http import Response, request

_logger = logging.getLogger(__name__)

DIRECTIONS = ('inbound', 'outbound', 'missed')

# Liste blanche stricte. Tout champ absent d'ici fait rejeter la requête au
# lieu d'être ignoré : un champ inattendu signale un désaccord de version
# entre l'app et le serveur, et l'ignorer silencieusement ferait journaliser
# des appels amputés sans que personne ne le remarque.
CHAMPS_ATTENDUS = {
    'client_event_id',
    'phone_number',
    'direction',
    'duration_seconds',
    'started_at',
}
CHAMPS_OBLIGATOIRES = CHAMPS_ATTENDUS - {'duration_seconds'}

# Durée au-delà de laquelle un appel est considéré comme une erreur de saisie
# plutôt qu'une communication (24 h).
DUREE_MAX = 86400


def repondre(charge, statut=200):
    return Response(
        json.dumps(charge),
        status=statut,
        content_type='application/json; charset=utf-8',
    )


class ErreurCharge(ValueError):
    """Charge utile invalide — porte le message renvoyé au client."""


def _lire_charge(corps):
    try:
        charge = json.loads(corps or b'{}')
    except (ValueError, UnicodeDecodeError):
        raise ErreurCharge("corps de requête illisible, JSON attendu")
    if not isinstance(charge, dict):
        raise ErreurCharge("objet JSON attendu")

    inconnus = set(charge) - CHAMPS_ATTENDUS
    if inconnus:
        raise ErreurCharge("champs non reconnus : %s" % ', '.join(sorted(inconnus)))
    manquants = CHAMPS_OBLIGATOIRES - set(charge)
    if manquants:
        raise ErreurCharge("champs obligatoires absents : %s" % ', '.join(sorted(manquants)))

    identifiant = charge['client_event_id']
    if not isinstance(identifiant, str) or not identifiant.strip():
        raise ErreurCharge("client_event_id doit être une chaîne non vide")

    numero = charge['phone_number']
    if not isinstance(numero, str) or not numero.strip():
        raise ErreurCharge("phone_number doit être une chaîne non vide")

    direction = charge['direction']
    if direction not in DIRECTIONS:
        raise ErreurCharge("direction doit valoir %s" % ', '.join(DIRECTIONS))

    duree = charge.get('duration_seconds', 0)
    if not isinstance(duree, int) or isinstance(duree, bool) or not 0 <= duree <= DUREE_MAX:
        raise ErreurCharge("duration_seconds doit être un entier entre 0 et %d" % DUREE_MAX)

    return {
        'client_event_id': identifiant.strip(),
        'phone_number': numero.strip(),
        'direction': direction,
        'duration_seconds': duree,
        'started_at': _lire_horodatage(charge['started_at']),
    }


def _lire_horodatage(valeur):
    """Convertit un ISO 8601 en datetime naïf UTC, la forme stockée par Odoo.

    Un horodatage sans fuseau est refusé : le téléphone d'un commercial peut
    être sur n'importe quel fuseau, et l'interpréter comme de l'UTC décalerait
    les appels de plusieurs heures sans que rien ne le signale.
    """
    if not isinstance(valeur, str):
        raise ErreurCharge("started_at doit être une chaîne ISO 8601")
    texte = valeur.strip().replace('Z', '+00:00')
    try:
        moment = datetime.fromisoformat(texte)
    except ValueError:
        raise ErreurCharge("started_at illisible, ISO 8601 attendu (ex. 2026-08-09T14:32:00Z)")
    if moment.tzinfo is None:
        raise ErreurCharge("started_at doit porter un fuseau horaire (suffixe Z ou +HH:MM)")
    return moment.astimezone(timezone.utc).replace(tzinfo=None)


class CallTrackerController(http.Controller):

    @http.route(
        '/call_tracker/log_call',
        type='http', auth='none', methods=['POST'], csrf=False, save_session=False,
        # Odoo 19 sert d'abord chaque requête sur un curseur en LECTURE SEULE,
        # et ne rejoue en écriture qu'après avoir vu échouer l'INSERT. Sans ce
        # drapeau, chaque appel journalisé exécute donc le contrôleur DEUX
        # fois — validation, recherche de doublon, rapprochement — et laisse
        # une trace d'exception dans les journaux, pour un endpoint dont
        # l'écriture est la raison d'être.
        readonly=False,
    )
    def log_call(self, **_kwargs):
        appareil = self._authentifier()
        if not appareil:
            return repondre({'status': 'unauthorized'}, 401)

        try:
            valeurs = _lire_charge(request.httprequest.get_data())
        except ErreurCharge as erreur:
            return repondre({'status': 'invalid', 'detail': str(erreur)}, 400)

        Appel = request.env['call.tracker.log'].sudo()

        # Rejeu d'un appel déjà reçu : on répond 200, pas une erreur. L'app
        # doit pouvoir retirer l'événement de sa file locale — un 4xx la
        # ferait réessayer indéfiniment le seul cas où tout va bien.
        existant = Appel.search([('client_event_id', '=', valeurs['client_event_id'])], limit=1)
        if existant:
            return repondre(self._resultat(existant, 'duplicate'))

        valeurs.update(device_id=appareil.id, user_id=appareil.user_id.id)
        try:
            # Point de reprise : deux réessais concurrents de l'app peuvent
            # franchir ensemble le search ci-dessus. L'index unique tranche, et
            # sans savepoint la transaction entière serait perdue.
            with request.env.cr.savepoint():
                appel = Appel.create(valeurs)
        except psycopg2.errors.UniqueViolation:
            appel = Appel.search([('client_event_id', '=', valeurs['client_event_id'])], limit=1)
            return repondre(self._resultat(appel, 'duplicate'))

        appareil.sudo().write({'last_seen': fields.Datetime.now()})
        return repondre(self._resultat(appel, 'logged'), 201)

    @http.route(
        '/call_tracker/contact/<path:numero>',
        type='http', auth='none', methods=['GET'], csrf=False, save_session=False,
        # Lecture pure : le curseur en lecture seule d'Odoo 19 convient, et le
        # déclarer évite qu'une écriture s'y glisse par inadvertance.
        readonly=True,
    )
    def contact(self, numero, **_kwargs):
        """Fiche minimale pour l'affichage à la sonnerie (Caller ID).

        `<path:numero>` et non `<string:numero>` : un numéro international
        s'écrit `+213555000000`, et le `+` comme les espaces d'une saisie
        recopiée traversent mal un segment d'URL classique.
        """
        if not self._authentifier():
            return repondre({'status': 'unauthorized'}, 401)

        fiche = request.env['call.tracker.log'].sudo().fiche_contact(numero)
        if not fiche:
            # 404 et non un objet vide : l'app doit pouvoir distinguer
            # « inconnu au CRM » de « connu mais sans information », qui
            # s'affichent différemment à l'écran.
            return repondre({'status': 'not_found'}, 404)
        return repondre({'status': 'found', **fiche})

    def _authentifier(self):
        entete = request.httprequest.headers.get('Authorization', '')
        if not entete.startswith('Bearer '):
            return None
        appareil = request.env['call.tracker.device']._resoudre_par_jeton(entete[7:].strip())
        # `active` est un champ spécial d'Odoo : un search ordinaire écarte
        # déjà les enregistrements archivés, mais on le revérifie ici pour que
        # la révocation ne dépende pas de ce comportement implicite.
        return appareil if appareil and appareil.active else None

    def _resultat(self, appel, statut):
        """Réponse minimale : de quoi confirmer, rien de plus.

        Pas de nom de contact ni de libellé de piste — l'app n'en a pas besoin
        pour accuser réception, et une route d'écriture n'a pas à devenir une
        fuite de lecture.
        """
        if appel.lead_id:
            rattachement = 'crm.lead,%d' % appel.lead_id.id
        elif appel.partner_id:
            rattachement = 'res.partner,%d' % appel.partner_id.id
        else:
            rattachement = None
        return {
            'status': statut,
            'call_id': appel.id,
            'linked_record': rattachement,
        }
