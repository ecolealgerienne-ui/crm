# -*- coding: utf-8 -*-
"""Routes exposées à l'application mobile.

``type='http'`` et non ``type='json'`` : le second impose l'enveloppe JSON-RPC
d'Odoo (``{"jsonrpc": "2.0", "params": {...}}``, réponse enrobée, erreurs
renvoyées en HTTP 200). Un client mobile veut du JSON nu et des codes HTTP qui
veulent dire quelque chose ; on lit donc le corps et on écrit la réponse
nous-mêmes.

``auth='public'`` : l'authentification réelle est faite ici, par jeton
d'appareil, et les accès à la base passent en ``sudo()``. C'est le point
central du module — le jeton présenté par l'app ne porte AUCUN droit Odoo, il
ne fait que désigner un appareil. Ce qui est écrit, et ce qui est renvoyé, est
décidé par ce fichier, jamais par les droits d'un compte.

⚠️ **``public`` et non ``none``, et la nuance n'est pas cosmétique.** Avec
``auth='none'``, Odoo ne lie aucun utilisateur : ``env.uid`` vaut ``None``. Or
``sudo()`` lève le contrôle d'accès mais **conserve l'uid** — il ne le répare
pas. Le défaut ne se voit pas tout de suite : il surgit au *flush* de fin de
transaction, exécuté dans l'environnement par défaut de la requête, sous la
forme d'un ``ValueError: Expected singleton: res.users()`` dont la trace ne
mentionne ni authentification ni contrôleur. Un environnement parallèle
(``request.env(user=SUPERUSER_ID)``) ne suffit pas non plus, pour la même
raison : le flush n'utilise pas celui-là.

``auth='public'`` lie l'utilisateur public — un compte réel, sans droit
notable. Rien n'est ouvert par ce choix : tout passe toujours par ``sudo()``.
"""
import json
import logging
import re
from datetime import datetime, timedelta, timezone

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
    'note',
}
CHAMPS_OBLIGATOIRES = CHAMPS_ATTENDUS - {'duration_seconds', 'note'}

# Une note prise au pouce sur un téléphone, pas un compte rendu. Au-delà, c'est
# un collage accidentel ou une app qui déraille — mieux vaut refuser que
# stocker.
NOTE_MAX = 1000

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

    note = charge.get('note')
    if note is not None:
        if not isinstance(note, str):
            raise ErreurCharge("note doit être une chaîne")
        if len(note) > NOTE_MAX:
            raise ErreurCharge("note trop longue (%d caractères maximum)" % NOTE_MAX)

    return {
        'client_event_id': identifiant.strip(),
        'phone_number': numero.strip(),
        'direction': direction,
        'duration_seconds': duree,
        'started_at': _lire_horodatage(charge['started_at']),
        'note': (note or '').strip() or False,
    }


#: Tolérance sur un horodatage à venir. Une heure absorbe la dérive ordinaire
#: d'une horloge de téléphone sans laisser passer une date aberrante.
AVANCE_MAX = timedelta(hours=1)

#: Ancienneté maximale quand aucune purge n'est configurée. Dix ans ne
#: protègent de rien d'utile ; ils écartent seulement l'absurde — un appel
#: daté de 1970 par une horloge repartie de zéro.
ANCIENNETE_MAX = timedelta(days=3650)


def _lire_horodatage(valeur):
    """Convertit un ISO 8601 en datetime naïf UTC, la forme stockée par Odoo.

    Un horodatage sans fuseau est refusé : le téléphone d'un commercial peut
    être sur n'importe quel fuseau, et l'interpréter comme de l'UTC décalerait
    les appels de plusieurs heures sans que rien ne le signale.

    Il est aussi borné des deux côtés, et c'est ce qui rend visible la seule
    panne réellement silencieuse du dispositif : une horloge de téléphone
    fausse. Trop ancien, l'appel arrive, se journalise, puis est supprimé par
    la purge au passage suivant du cron avec sa trace d'audit — il aura existé
    sans laisser la moindre trace. Trop récent, il n'est jamais purgé : la
    rétention se compte sur ``started_at``, donc un appel daté de 2999
    survivrait à la fermeture du service.

    Refuser vaut mieux qu'accepter : un 400 est classé « refus définitif » par
    l'application, l'appel bascule en échec et le motif s'affiche à l'écran.
    Le défaut le plus muet du système devient le plus visible.
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

    horodatage = moment.astimezone(timezone.utc).replace(tzinfo=None)
    maintenant = fields.Datetime.now()
    if horodatage > maintenant + AVANCE_MAX:
        raise ErreurCharge(
            "started_at est dans le futur — vérifiez l'heure du téléphone"
        )
    # ⚠️ `_jours_de_retention()` rend 0 pour dire « aucune purge », PAS « une
    # rétention nulle ». Le prendre au pied de la lettre posait le plancher à
    # l'instant présent et refusait absolument tous les appels — y compris
    # celui qui vient de raccrocher. Le sens choisi là-bas (un défaut de
    # configuration ne doit jamais faire disparaître de données) s'inverse ici
    # s'il n'est pas retraduit : le même 0 ferait tout perdre.
    jours = request.env['call.tracker.log'].sudo()._jours_de_retention()
    plancher = maintenant - (timedelta(days=jours) if jours > 0 else ANCIENNETE_MAX)
    if horodatage < plancher:
        raise ErreurCharge(
            "started_at est plus ancien que la durée de conservation — "
            "vérifiez l'heure du téléphone"
        )
    return horodatage


class CallTrackerController(http.Controller):

    @http.route(
        '/call_tracker/log_call',
        type='http', auth='public', methods=['POST'], csrf=False, save_session=False,
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
            self._tracer('log_call', 'unauthorized')
            return repondre({'status': 'unauthorized'}, 401)

        try:
            valeurs = _lire_charge(request.httprequest.get_data())
        except ErreurCharge as erreur:
            self._tracer('log_call', 'invalid', appareil, detail=str(erreur))
            return repondre({'status': 'invalid', 'detail': str(erreur)}, 400)

        Appel = request.env['call.tracker.log'].sudo()

        # Rejeu d'un appel déjà reçu : on répond 200, pas une erreur. L'app
        # doit pouvoir retirer l'événement de sa file locale — un 4xx la
        # ferait réessayer indéfiniment le seul cas où tout va bien.
        existant = Appel.search([('client_event_id', '=', valeurs['client_event_id'])], limit=1)
        if existant:
            self._completer_note(existant, valeurs, appareil)
            return self._repondre_appel(existant, 'duplicate', 200, appareil)

        valeurs.update(device_id=appareil.id, user_id=appareil.user_id.id)
        # AVANT la création : l'appel recopie le modèle depuis l'appareil, et
        # le noter après laisserait le tout premier appel d'une version d'app
        # sans modèle — soit exactement celui d'un téléphone qu'on découvre.
        self._noter_appareil(appareil)
        try:
            # Point de reprise : deux réessais concurrents de l'app peuvent
            # franchir ensemble le search ci-dessus. L'index unique tranche, et
            # sans savepoint la transaction entière serait perdue.
            with request.env.cr.savepoint():
                appel = Appel.create(valeurs)
        except psycopg2.errors.UniqueViolation:
            appel = Appel.search([('client_event_id', '=', valeurs['client_event_id'])], limit=1)
            self._completer_note(appel, valeurs, appareil)
            return self._repondre_appel(appel, 'duplicate', 200, appareil)

        return self._repondre_appel(appel, 'logged', 201, appareil)

    def _completer_note(self, existant, valeurs, appareil):
        """Seul champ qu'un rejeu a le droit d'ajouter : la note.

        ⚠️ Borné à l'appareil qui a remis l'appel. Un `client_event_id` est un
        UUID, donc impraticable à deviner — mais cadrer coûte une comparaison
        et évite qu'un jeton quelconque puisse écrire dans le fil d'un client
        au nom d'un autre commercial.
        """
        if not existant or not valeurs.get('note'):
            return
        if existant.device_id != appareil:
            self._tracer('log_call', 'forbidden', appareil,
                         numero=existant.phone_number)
            return
        existant.completer_note(valeurs['note'])

    def _repondre_appel(self, appel, statut, code, appareil):
        resultat = self._resultat(appel, statut)
        self._tracer(
            'log_call',
            'duplicate' if statut == 'duplicate' else 'ok',
            appareil,
            numero=appel.phone_number,
            linked_record=resultat['linked_record'],
        )
        return repondre(resultat, code)

    @http.route(
        '/call_tracker/contact/<path:numero>',
        type='http', auth='public', methods=['GET'], csrf=False, save_session=False,
        # `readonly=False` alors que la route ne fait que lire une fiche : elle
        # ÉCRIT une trace d'audit, et c'est justement l'intérêt du dispositif.
        # Une consultation ne laisse par nature aucune trace ; sans ce journal,
        # un jeton volé pourrait parcourir le carnet d'adresses numéro par
        # numéro sans que rien n'en subsiste. Le curseur en lecture seule
        # d'Odoo 19 ferait échouer cette écriture.
        readonly=False,
    )
    def contact(self, numero, **_kwargs):
        """Fiche minimale pour l'affichage à la sonnerie (Caller ID).

        `<path:numero>` et non `<string:numero>` : un numéro international
        s'écrit `+213555000000`, et le `+` comme les espaces d'une saisie
        recopiée traversent mal un segment d'URL classique.
        """
        appareil = self._authentifier()
        if not appareil:
            self._tracer('contact_lookup', 'unauthorized', numero=numero)
            return repondre({'status': 'unauthorized'}, 401)

        fiche = request.env['call.tracker.log'].sudo().fiche_contact(numero)
        if not fiche:
            self._tracer('contact_lookup', 'not_found', appareil, numero=numero)
            # 404 et non un objet vide : l'app doit pouvoir distinguer
            # « inconnu au CRM » de « connu mais sans information », qui
            # s'affichent différemment à l'écran.
            return repondre({'status': 'not_found'}, 404)

        self._tracer('contact_lookup', 'ok', appareil, numero=numero)
        return repondre({'status': 'found', **fiche})

    @http.route(
        '/call_tracker/contacts/<path:fragment>',
        type='http', auth='public', methods=['GET'], csrf=False, save_session=False,
        # Écrit une trace d'audit, comme la route de fiche. Ici c'est encore
        # plus nécessaire : une recherche par fragment touche potentiellement
        # tout le carnet d'adresses, et c'est la seule chose qui en restera.
        readonly=False,
    )
    def contacts(self, fragment, **_kwargs):
        """Contacts dont le numéro contient ce fragment.

        Distincte de ``/contact/<numero>``, qui sert la sonnerie : celle-là
        part d'un numéro complet et rend une fiche, celle-ci part d'un bout de
        numéro et rend une liste. Les fusionner reviendrait à donner au Caller
        ID le droit de balayer le carnet, pour aucun gain.

        Le **nombre de résultats** est journalisé autant que le fragment : une
        énumération se reconnaît à sa forme — des recherches courtes en
        rafale, chacune rendant le maximum — et sans ce compte la trace ne
        dirait pas si le carnet a été effleuré ou vidé.
        """
        appareil = self._authentifier()
        if not appareil:
            self._tracer('contact_search', 'unauthorized', numero=fragment)
            return repondre({'status': 'unauthorized'}, 401)

        Appel = request.env['call.tracker.log'].sudo()
        chiffres = re.sub(r'\D', '', fragment or '')
        if len(chiffres) < Appel.FRAGMENT_MIN:
            # 400 et non une liste vide : « trop court » et « aucun résultat »
            # appellent deux messages différents à l'écran, et l'app ne peut
            # pas les distinguer si le serveur répond la même chose.
            self._tracer('contact_search', 'too_short', appareil, numero=fragment)
            return repondre(
                {'status': 'too_short', 'min_digits': Appel.FRAGMENT_MIN}, 400,
            )

        resultats = Appel.rechercher_contacts(
            chiffres, commercial=appareil.user_id,
        )
        self._tracer(
            'contact_search',
            'ok' if resultats else 'not_found',
            appareil,
            numero=chiffres,
            # Le périmètre appliqué accompagne le compte : sans lui, « aucun
            # résultat » ne dit pas si le client n'existe pas ou s'il
            # appartient à un collègue, et le premier réflexe serait de
            # soupçonner une panne.
            detail='%d resultat(s), perimetre %s' % (
                len(resultats), Appel._perimetre_recherche(),
            ),
        )
        return repondre({
            'status': 'found' if resultats else 'not_found',
            'count': len(resultats),
            'results': resultats,
        })

    @http.route(
        '/call_tracker/activities',
        type='http', auth='public', methods=['GET'], csrf=False, save_session=False,
        readonly=False,  # écrit une trace d'audit
    )
    def activities(self, **_kwargs):
        """Les appels programmés dans le CRM pour le commercial de l'appareil.

        La seule route qui rende quelque chose au commercial au lieu de lui
        prendre — et donc la seule qui lui donne une raison d'ouvrir
        l'application. Ce n'est pas anecdotique : une application qu'on
        n'ouvre jamais est une application dont la file d'envoi ne se vide
        pas.

        Aucun paramètre de périmètre : une activité est assignée à un
        utilisateur, et le jeton désigne l'appareil donc le commercial. Le
        cloisonnement est dans la donnée.
        """
        appareil = self._authentifier()
        if not appareil:
            self._tracer('activity_list', 'unauthorized')
            return repondre({'status': 'unauthorized'}, 401)

        activites = request.env['call.tracker.log'].sudo().activites_a_appeler(
            appareil.user_id,
        )
        self._tracer(
            'activity_list', 'ok' if activites else 'not_found', appareil,
            detail='%d activite(s)' % len(activites),
        )
        return repondre({
            'status': 'found' if activites else 'not_found',
            'count': len(activites),
            'results': activites,
        })

    @http.route(
        '/call_tracker/activity/<int:identifiant>/done',
        type='http', auth='public', methods=['POST'], csrf=False, save_session=False,
        readonly=False,
    )
    def activity_done(self, identifiant, **_kwargs):
        """Clôture une activité d'appel.

        ⚠️ L'appartenance est revérifiée côté serveur, dans le modèle. Rien
        n'empêche un jeton volé d'envoyer des identifiants au hasard, et une
        tâche qui disparaît de la liste d'un collègue ne se remarque pas :
        elle s'oublie.

        404 aussi bien pour « inexistante » que pour « pas la vôtre » : les
        distinguer renseignerait sur le portefeuille des autres.
        """
        appareil = self._authentifier()
        if not appareil:
            self._tracer('activity_done', 'unauthorized')
            return repondre({'status': 'unauthorized'}, 401)

        fait = request.env['call.tracker.log'].sudo().cloturer_activite(
            identifiant, appareil.user_id,
        )
        self._tracer(
            'activity_done', 'ok' if fait else 'not_found', appareil,
            detail='activite %d' % identifiant,
        )
        if not fait:
            return repondre({'status': 'not_found'}, 404)
        return repondre({'status': 'done'})

    def _noter_appareil(self, appareil):
        """Horodate l'appareil et relève ce qu'il déclare de lui-même.

        Le modèle et la version d'Android arrivent par des **en-têtes**, pas
        par la charge utile : celle-ci a une liste blanche stricte qui rejette
        tout champ inconnu, et y ajouter des clés ferait échouer l'envoi de
        TOUS les appels d'une version d'app antérieure. Un en-tête absent ne
        casse rien — les anciennes versions continuent simplement sans.

        Écrit seulement ce qui change : un `write` par appel remis, sur tous
        les téléphones, pour recopier deux chaînes identiques, ce serait de
        l'écriture pure pour rien.
        """
        valeurs = {'last_seen': fields.Datetime.now()}
        entetes = request.httprequest.headers
        for champ, entete in (('device_model', 'X-Device-Model'),
                              ('os_version', 'X-Device-Os')):
            annonce = (entetes.get(entete) or '').strip()[:64]
            if annonce and annonce != appareil[champ]:
                valeurs[champ] = annonce
        appareil.sudo().write(valeurs)

    def _tracer(self, action, result, appareil=None, numero=None,
                detail=None, linked_record=None):
        request.env['call.tracker.audit'].sudo().tracer(
            action=action,
            result=result,
            appareil=appareil,
            numero=numero,
            detail=detail,
            linked_record=linked_record,
            ip=request.httprequest.remote_addr,
        )

    def _authentifier(self):
        entete = request.httprequest.headers.get('Authorization', '')
        if not entete.startswith('Bearer '):
            return None
        appareil = request.env['call.tracker.device']._resoudre_par_jeton(
            entete[7:].strip()
        )
        # `active` est un champ spécial d'Odoo : un search ordinaire écarte
        # déjà les enregistrements archivés, mais on le revérifie ici pour que
        # la révocation ne dépende pas de ce comportement implicite.
        return appareil if appareil and appareil.active else None

    def _resultat(self, appel, statut):
        """Réponse minimale : de quoi confirmer, rien de plus.

        Pas de nom de contact ni de libellé de piste — l'app n'en a pas besoin
        pour accuser réception, et une route d'écriture n'a pas à devenir une
        fuite de lecture.

        Une exception à cette économie : ``retention_days``. L'application doit
        pouvoir annoncer au commercial combien de temps ses appels sont
        conservés, or cette durée est fixée par le ``.env`` du serveur. La
        recopier en dur dans l'app serait la garantie qu'un jour l'écran
        d'information dira trois ans quand le serveur en garde cinq — et un
        avis de confidentialité faux est pire que pas d'avis du tout. Ce n'est
        pas une donnée personnelle : c'est la politique de l'instance, que
        celui qui est enregistré a le droit de connaître.
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
            'retention_days': request.env['call.tracker.log']._jours_de_retention(),
        }
