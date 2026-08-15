# -*- coding: utf-8 -*-
"""Les deux routes par lesquelles echango Promo pousse son instantané.

``type='http'`` et non ``type='json'`` : le second impose l'enveloppe JSON-RPC
d'Odoo (erreurs renvoyées en HTTP 200). L'émetteur veut du JSON nu et des codes
HTTP qui veulent dire quelque chose. *(En 19.0, ``type='json'`` est de surcroît
un alias déprécié de ``type='jsonrpc'``.)*

``auth='public'`` : l'authentification réelle est faite ici, par jeton, et les
accès à la base passent en ``sudo()``. Le jeton ne porte **aucun** droit Odoo :
c'est ce fichier qui décide de ce qui est écrit.

⚠️ **``public`` et non ``none``.** Avec ``auth='none'``, Odoo ne lie aucun
utilisateur et ``env.uid`` vaut ``None`` ; ``sudo()`` lève le contrôle d'accès
mais **conserve l'uid**, il ne le répare pas. Le défaut ne surgit qu'au *flush*
de fin de transaction, sous la forme d'un ``ValueError: Expected singleton:
res.users()`` dont la trace ne mentionne ni authentification ni contrôleur.

⚠️ **``readonly=False``, et son absence ne casse rien de visible.** Odoo 19 sert
d'abord chaque requête sur un curseur en LECTURE SEULE et ne rejoue en écriture
qu'après avoir vu l'``INSERT`` échouer. L'upsert étant idempotent, le lot
passerait quand même — mais tout le contrôleur s'exécuterait **deux fois**, avec
une exception au journal à chaque page.
"""
import json
import logging
from datetime import datetime, timedelta, timezone

from odoo import fields, http
from odoo.http import Response, request

_logger = logging.getLogger(__name__)

#: Liste blanche stricte. Tout champ absent d'ici fait **rejeter** la fiche au
#: lieu d'être ignoré : un champ inattendu signale un désaccord de version entre
#: les deux dépôts, et l'ignorer en silence produirait des fiches amputées que
#: personne ne remarquerait.
CHAMPS_FICHE = {
    'promo_uuid', 'nom', 'adresse', 'categorie', 'telephone_e164', 'pays',
    'latitude', 'longitude', 'origine', 'agent_createur_id', 'date_creation',
    'suspendu_le', 'supprime_le', 'consentement_le', 'est_active',
    'date_derniere_publication', 'promos_sans_publication',
    'promos_deja_publiees', 'promos_en_ligne', 'promos_visibles',
    'promos_publiees_30j', 'promos_masquees', 'signalements_90j',
    'nouveaux_visiteurs_fiche_30j', 'nouveaux_visiteurs_promos_30j',
    'plafond_effectif', 'plafond_propre', 'registre_statut', 'peut_publier',
    'motif_blocage',
}
CHAMPS_OBLIGATOIRES = {'promo_uuid', 'nom', 'telephone_e164', 'pays'}

CHAMPS_LOT = {'lot', 'genere_le', 'total_attendu', 'page', 'pages', 'items'}
CHAMPS_ACK = {'lot', 'total_envoye', 'total_attendu'}

#: Bornes. Une route publique sans borne est une route ouverte : le module
#: voisin borne jusqu'aux valeurs unitaires, pour la même raison.
FICHES_MAX = 500
TEXTE_MAX = 300
ENTIER_MAX = 10_000_000
#: Tolérance sur un horodatage à venir — une heure absorbe la dérive ordinaire
#: d'une horloge serveur sans laisser passer une date aberrante.
AVANCE_MAX = timedelta(hours=1)


class ErreurCharge(ValueError):
    """Charge utile invalide — porte le message renvoyé à l'émetteur."""


def repondre(charge, statut=200):
    return Response(json.dumps(charge), status=statut,
                    content_type='application/json; charset=utf-8')


def _texte(valeur, champ, obligatoire=False):
    if valeur is None:
        if obligatoire:
            raise ErreurCharge("%s est obligatoire" % champ)
        return False
    if not isinstance(valeur, str):
        raise ErreurCharge("%s doit être une chaîne" % champ)
    if len(valeur) > TEXTE_MAX:
        raise ErreurCharge("%s dépasse %d caractères" % (champ, TEXTE_MAX))
    return valeur


def _entier(valeur, champ):
    if valeur is None:
        return 0
    if isinstance(valeur, bool) or not isinstance(valeur, int):
        raise ErreurCharge("%s doit être un entier" % champ)
    if not 0 <= valeur <= ENTIER_MAX:
        raise ErreurCharge("%s hors bornes" % champ)
    return valeur


def _horodatage(valeur, champ):
    """ISO 8601 → naïf UTC, la forme qu'Odoo stocke.

    ⚠️ Une date **future** est refusée au-delà d'une heure : elle signale une
    horloge déréglée à la source, et une fiche datée de demain fausserait tout
    calcul d'ancienneté sans que rien ne le signale.
    """
    if valeur in (None, False, ''):
        return False
    if not isinstance(valeur, str):
        raise ErreurCharge("%s doit être une date ISO" % champ)
    try:
        lu = datetime.fromisoformat(valeur.replace('Z', '+00:00'))
    except ValueError:
        raise ErreurCharge("%s illisible (ISO 8601 attendu)" % champ)
    if lu.tzinfo is None:
        lu = lu.replace(tzinfo=timezone.utc)
    if lu > datetime.now(timezone.utc) + AVANCE_MAX:
        raise ErreurCharge("%s est dans le futur" % champ)
    return lu.astimezone(timezone.utc).replace(tzinfo=None)


def _lire_fiche(brut):
    if not isinstance(brut, dict):
        raise ErreurCharge("chaque fiche doit être un objet JSON")
    inconnus = set(brut) - CHAMPS_FICHE
    if inconnus:
        raise ErreurCharge("champs non reconnus : %s" % ', '.join(sorted(inconnus)))
    manquants = CHAMPS_OBLIGATOIRES - set(brut)
    if manquants:
        raise ErreurCharge("champs obligatoires absents : %s"
                           % ', '.join(sorted(manquants)))
    return brut


class EchangoPromoController(http.Controller):

    # ── Authentification ────────────────────────────────────────────────────

    def _authentifier(self):
        """La source dont l'empreinte correspond au jeton présenté.

        ⚠️ `active` est revérifié à **chaque** requête et il n'y a aucun cache :
        c'est ce qui rend une révocation immédiate.
        """
        jeton = request.httprequest.headers.get('X-Echango-Token', '')
        if not jeton:
            return None
        empreinte = request.env['echango.promo.source'].empreinte(jeton)
        return request.env['echango.promo.source'].sudo().search(
            [('token_hash', '=', empreinte), ('active', '=', True)], limit=1)

    def _refuser(self, route, detail, statut=401, source=None, batch=None):
        request.env['echango.promo.audit'].tracer(
            request.env, source_id=source.id if source else False, batch=batch,
            route=route, accepte=False, detail=detail[:300],
            ip=request.httprequest.remote_addr)
        return repondre({'erreur': detail}, statut)

    # ── Réception d'une page ────────────────────────────────────────────────

    @http.route('/echango_promo/merchants/sync', type='http', auth='public',
                methods=['POST'], csrf=False, readonly=False)
    def sync(self, **_kw):
        source = self._authentifier()
        if not source:
            return self._refuser('sync', "jeton absent ou révoqué")

        try:
            charge = json.loads(request.httprequest.get_data() or b'{}')
            if not isinstance(charge, dict):
                raise ErreurCharge("objet JSON attendu")
            inconnus = set(charge) - CHAMPS_LOT
            if inconnus:
                raise ErreurCharge("champs de lot non reconnus : %s"
                                   % ', '.join(sorted(inconnus)))
            lot = _texte(charge.get('lot'), 'lot', obligatoire=True)
            items = charge.get('items')
            if not isinstance(items, list):
                raise ErreurCharge("items doit être une liste")
            if len(items) > FICHES_MAX:
                raise ErreurCharge("au plus %d fiches par page" % FICHES_MAX)
            genere_le = _horodatage(charge.get('genere_le'), 'genere_le')
        except (ValueError, UnicodeDecodeError) as erreur:
            return self._refuser('sync', str(erreur), 400, source)

        pris, refusees, details = 0, 0, []
        for brut in items:
            # ⚠️ **Un savepoint par fiche.** Sur 200 objets, un seul invalide ne
            # doit ni perdre le lot, ni passer inaperçu : sans cela, la première
            # fiche fautive annulerait les 199 autres.
            try:
                with request.env.cr.savepoint():
                    fiche = _lire_fiche(brut)
                    self._poser(source, fiche, genere_le, lot)
                pris += 1
            except Exception as erreur:  # noqa: BLE001 — voir la docstring
                refusees += 1
                if len(details) < 5:
                    details.append('%s: %s' % (
                        (brut or {}).get('promo_uuid', '?'), erreur))

        source.sudo().write({
            'last_seen': fields.Datetime.now(),
            'last_batch': lot,
        })
        request.env['echango.promo.audit'].tracer(
            request.env, source_id=source.id, batch=lot, route='sync',
            accepte=refusees == 0, fiches=pris, refusees=refusees,
            detail='; '.join(details)[:300] or 'ok',
            ip=request.httprequest.remote_addr)

        return repondre({'prises': pris, 'refusees': refusees,
                         'details': details})

    # ── Acquittement de fin de lot ──────────────────────────────────────────

    @http.route('/echango_promo/merchants/ack', type='http', auth='public',
                methods=['POST'], csrf=False, readonly=False)
    def ack(self, **_kw):
        """Clôt le lot, et **c'est lui seul qui autorise l'archivage**.

        ⚠️ Sans acquittement, « ce commerçant n'est plus envoyé » et « l'export
        s'est arrêté à la page 3 » sont indiscernables — et archiver sur
        l'absence viderait le portefeuille au premier export interrompu.
        """
        source = self._authentifier()
        if not source:
            return self._refuser('ack', "jeton absent ou révoqué")

        try:
            charge = json.loads(request.httprequest.get_data() or b'{}')
            inconnus = set(charge) - CHAMPS_ACK
            if inconnus:
                raise ErreurCharge("champs non reconnus : %s"
                                   % ', '.join(sorted(inconnus)))
            lot = _texte(charge.get('lot'), 'lot', obligatoire=True)
            envoye = _entier(charge.get('total_envoye'), 'total_envoye')
            attendu = _entier(charge.get('total_attendu'), 'total_attendu')
        except (ValueError, UnicodeDecodeError) as erreur:
            return self._refuser('ack', str(erreur), 400, source)

        if envoye != attendu:
            # ⚠️ **On refuse d'archiver sur un lot incomplet.** Le lot reste
            # reçu — les fiches posées sont bonnes — mais rien n'est retiré.
            request.env['echango.promo.audit'].tracer(
                request.env, source_id=source.id, batch=lot, route='ack',
                accepte=False, fiches=envoye,
                detail="lot incomplet (%d envoyées / %d attendues) — "
                       "aucun archivage" % (envoye, attendu),
                ip=request.httprequest.remote_addr)
            return repondre({'archives': 0, 'raison': 'lot incomplet'})

        Compte = request.env['echango.promo.account'].sudo()
        orphelins = Compte.search([('last_batch', '!=', lot)])
        archives = 0
        for compte in orphelins:
            if compte.partner_id.active:
                compte.partner_id.sudo().write({'active': False})
                archives += 1

        source.sudo().write({'last_count': envoye})
        request.env['echango.promo.audit'].tracer(
            request.env, source_id=source.id, batch=lot, route='ack',
            accepte=True, fiches=envoye,
            detail="%d fiche(s) archivée(s)" % archives,
            ip=request.httprequest.remote_addr)
        return repondre({'archives': archives})

    # ── L'écriture ──────────────────────────────────────────────────────────

    def _poser(self, source, fiche, genere_le, lot):
        """Crée ou met à jour la fiche de suivi, et **sème** le partenaire.

        ⚠️ **`res.partner` est semé à la création, puis jamais réécrit** — à une
        exception : le téléphone, qui est la clé de rapprochement des appels
        entrants et appartient à Promo. Le nom et l'adresse corrigés à la main
        par un commercial survivent donc à la nuit suivante ; l'écart avec ce
        que Promo envoie reste visible sur la fiche de suivi.
        """
        Compte = request.env['echango.promo.account'].sudo()
        Partenaire = request.env['res.partner'].sudo()

        valeurs = {
            'promo_uuid': fiche['promo_uuid'],
            'nom_promo': _texte(fiche.get('nom'), 'nom', obligatoire=True),
            'adresse_promo': _texte(fiche.get('adresse'), 'adresse'),
            'categorie': _texte(fiche.get('categorie'), 'categorie'),
            'telephone_e164': _texte(fiche.get('telephone_e164'),
                                     'telephone_e164', obligatoire=True),
            'pays': _texte(fiche.get('pays'), 'pays', obligatoire=True),
            'latitude': fiche.get('latitude') or 0.0,
            'longitude': fiche.get('longitude') or 0.0,
            'origine': _texte(fiche.get('origine'), 'origine'),
            'agent_createur_id': _texte(fiche.get('agent_createur_id'),
                                        'agent_createur_id'),
            'date_creation': _horodatage(fiche.get('date_creation'),
                                         'date_creation'),
            'suspendu_le': _horodatage(fiche.get('suspendu_le'), 'suspendu_le'),
            'supprime_le': _horodatage(fiche.get('supprime_le'), 'supprime_le'),
            'consentement_le': _horodatage(fiche.get('consentement_le'),
                                           'consentement_le'),
            'est_active': bool(fiche.get('est_active')),
            'date_derniere_publication': _horodatage(
                fiche.get('date_derniere_publication'),
                'date_derniere_publication'),
            'promos_sans_publication': _entier(
                fiche.get('promos_sans_publication'), 'promos_sans_publication'),
            'promos_deja_publiees': _entier(fiche.get('promos_deja_publiees'),
                                            'promos_deja_publiees'),
            'promos_en_ligne': _entier(fiche.get('promos_en_ligne'),
                                       'promos_en_ligne'),
            'promos_visibles': _entier(fiche.get('promos_visibles'),
                                       'promos_visibles'),
            'promos_publiees_30j': _entier(fiche.get('promos_publiees_30j'),
                                           'promos_publiees_30j'),
            'promos_masquees': _entier(fiche.get('promos_masquees'),
                                       'promos_masquees'),
            'signalements_90j': _entier(fiche.get('signalements_90j'),
                                        'signalements_90j'),
            'nouveaux_visiteurs_fiche_30j': _entier(
                fiche.get('nouveaux_visiteurs_fiche_30j'),
                'nouveaux_visiteurs_fiche_30j'),
            'nouveaux_visiteurs_promos_30j': _entier(
                fiche.get('nouveaux_visiteurs_promos_30j'),
                'nouveaux_visiteurs_promos_30j'),
            'plafond_effectif': _entier(fiche.get('plafond_effectif'),
                                        'plafond_effectif'),
            'plafond_propre': _entier(fiche.get('plafond_propre'),
                                      'plafond_propre'),
            'registre_statut': _texte(fiche.get('registre_statut'),
                                      'registre_statut'),
            'peut_publier': bool(fiche.get('peut_publier')),
            'motif_blocage': _texte(fiche.get('motif_blocage'),
                                    'motif_blocage'),
            'genere_le': genere_le,
            'derniere_synchro': fields.Datetime.now(),
            'source_id': source.id,
            'last_batch': lot,
        }

        existant = Compte.search([('promo_uuid', '=', fiche['promo_uuid'])],
                                 limit=1)
        if existant:
            existant.write(valeurs)
            # ⚠️ Ré-armé APRÈS l'écriture, et seulement si la position a bougé
            # de plus de 200 m : sans ce seuil, chaque nuit relancerait une
            # requête Nominatim par commerçant, pour des dérives de capture GPS.
            existant._marquer_a_geocoder()
            # Le téléphone appartient à Promo : il est la clé de rapprochement
            # des appels entrants, et un commercial n'a pas à le corriger.
            existant.partner_id.write({
                'phone': valeurs['telephone_e164'],
                'active': True,
            })
            return existant

        pays = request.env['res.country'].sudo().search(
            [('code', '=', valeurs['pays'])], limit=1)
        partenaire = Partenaire.create({
            'name': valeurs['nom_promo'],
            # ⚠️ `is_company` garantit `commercial_partner_id = self`, donc une
            # ligne par commerce dans la Couverture du portefeuille du Call
            # Tracker. Sans lui, un commerce rattaché à un parent compterait
            # pour ce parent.
            'is_company': True,
            'phone': valeurs['telephone_e164'],
            'street': valeurs['adresse_promo'] or False,
            # ⚠️ **`country_id` est obligatoire, pas recommandé.**
            # `_phone_get_country` retombe sur le pays de la SOCIÉTÉ Odoo quand
            # la fiche n'en porte pas : un commerçant étranger recevrait alors
            # un `phone_sanitized` fabriqué avec le mauvais indicatif, et le
            # garde-fou pays du rapprochement d'appels mordrait à l'envers.
            'country_id': pays.id or False,
            'category_id': [(4, self._tag_provenance().id)],
        })
        valeurs['partner_id'] = partenaire.id
        compte = Compte.create(valeurs)
        compte._marquer_a_geocoder()
        return compte

    def _tag_provenance(self):
        """L'étiquette « echango Promo », créée une fois.

        ⚠️ C'est un **confort de lecture** dans la liste Contacts native, pas la
        provenance : celle-ci est portée par `promo_uuid`, immuable. Filtrer sur
        l'étiquette perdrait les fiches dont quelqu'un l'aurait retirée.
        """
        Categorie = request.env['res.partner.category'].sudo()
        tag = Categorie.search([('name', '=', 'echango Promo')], limit=1)
        return tag or Categorie.create({'name': 'echango Promo'})
