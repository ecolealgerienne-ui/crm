# -*- coding: utf-8 -*-
"""Le géocodage inverse : d'un point GPS vers un nom de ville.

⚠️ **Pourquoi il faut le faire ici et pas dans Promo.** Le produit n'a plus
aucun découpage administratif depuis le 2026-08-13 : il ne connaît qu'une
position. Sans géocodage, le CRM n'a **aucun** moyen de cibler
géographiquement — et en Odoo Community il n'y a pas de vue carte pour s'en
passer.

⚠️ **Nominatim, appelé une fois par commerçant.** Sa politique d'usage impose
au plus une requête par seconde ; un lot de 174 fiches se traite donc en
plusieurs passages de la tâche planifiée, pas d'un coup. Le géocodage n'est
**pas** refait à chaque synchronisation : seulement quand la position change de
plus de `DERIVE_MAX_KM`.
"""
import json
import logging
import math
import time
import urllib.parse
import urllib.request

from odoo import _, api, fields, models

_logger = logging.getLogger(__name__)

#: Politique d'usage de Nominatim : 1 requête/seconde maximum. On prend une
#: marge — dépasser fait bannir l'adresse IP, et un bannissement se découvre
#: bien après.
PAUSE_ENTRE_APPELS = 1.2

#: Fiches traitées par passage. 25 × 1,2 s ≈ 30 s : assez court pour ne pas
#: bloquer l'ordonnanceur, assez pour absorber un parc de 174 en sept passages.
LOT_PAR_PASSAGE = 25

#: ⚠️ **Un seuil, pas une égalité.** Un point capté à l'intérieur d'un local
#: dérive de 50 à 200 m d'une capture à l'autre : re-géocoder à chaque écart
#: ferait 174 requêtes par nuit pour rien, et finirait par faire bannir l'IP.
DERIVE_MAX_KM = 0.2

URL_NOMINATIM = "https://nominatim.openstreetmap.org/reverse"

#: ⚠️ **`accept-language` n'est pas cosmétique.** Sans lui, Nominatim rend le
#: nom local dans TOUTES ses graphies — « Djelfa ⴵⴻⵍⴼⴰ الجلفة » — et le
#: regroupement par ville produirait autant de groupes que de variantes.
LANGUE = "fr"


def distance_km(lat1, lng1, lat2, lng2):
    """Distance approchée entre deux points, en kilomètres (haversine)."""
    rayon = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2))
         * math.sin(dlng / 2) ** 2)
    return 2 * rayon * math.asin(math.sqrt(a))


class EchangoPromoAccount(models.Model):
    _inherit = 'echango.promo.account'

    #: ⚠️ **Trois absences différentes, trois valeurs différentes.** « Pas de
    #: position », « pas encore géocodé » et « géocodé sans résultat » se
    #: ressemblent à l'écran — une case vide — et appellent trois gestes
    #: opposés : demander la position au commerçant, attendre, ou saisir la
    #: ville à la main. Les confondre, c'est la règle #29.
    geocodage_statut = fields.Selection(
        [('sans_position', "Sans position GPS"),
         ('a_faire', "À géocoder"),
         ('fait', "Géocodé"),
         ('sans_resultat', "Géocodé, sans résultat"),
         ('erreur', "Échec du géocodage")],
        string="Géocodage", default='a_faire', readonly=True, index=True,
    )
    ville_geocodee = fields.Char(string="Ville (géocodée)", readonly=True)
    wilaya_geocodee = fields.Char(string="Wilaya (géocodée)", readonly=True)
    geocodage_le = fields.Datetime(string="Géocodé le", readonly=True)

    #: La position **effectivement géocodée**, pour savoir si la nouvelle a
    #: assez bougé pour justifier un second appel.
    geocodage_latitude = fields.Float(digits=(10, 6), readonly=True,
                                      aggregator=False)
    geocodage_longitude = fields.Float(digits=(10, 6), readonly=True,
                                       aggregator=False)

    def _statut_geocodage_attendu(self):
        """Ce que l'état devrait être, au vu de la position reçue."""
        self.ensure_one()
        if not self.latitude or not self.longitude:
            return 'sans_position'
        if self.geocodage_statut in ('fait', 'sans_resultat'):
            derive = distance_km(self.geocodage_latitude,
                                 self.geocodage_longitude,
                                 self.latitude, self.longitude)
            return 'a_faire' if derive > DERIVE_MAX_KM else self.geocodage_statut
        return 'a_faire'

    def _marquer_a_geocoder(self):
        """Appelé après chaque lot : ré-arme ce qui a bougé.

        ⚠️ Ne ré-arme **que** ce qui a bougé de plus de 200 m. Sans ce seuil,
        chaque nuit relancerait 174 requêtes Nominatim pour des dérives de
        capture GPS — et ferait bannir l'adresse IP du serveur.
        """
        for compte in self:
            attendu = compte._statut_geocodage_attendu()
            if attendu != compte.geocodage_statut:
                compte.geocodage_statut = attendu

    @api.model
    def _cron_geocoder(self):
        return self._geocoder_lot(LOT_PAR_PASSAGE)

    @api.model
    def _geocoder_lot(self, limite):
        """Géocode au plus `limite` fiches, une par une, en respectant la pause.

        Rend le nombre de fiches traitées — pas le nombre de succès : un
        « sans résultat » est un traitement, pas un échec, et le confondre
        ferait boucler la tâche sur les mêmes points indéfiniment.
        """
        a_faire = self.search([('geocodage_statut', '=', 'a_faire'),
                               ('latitude', '!=', 0),
                               ('longitude', '!=', 0)], limit=limite)
        traitees = 0
        for compte in a_faire:
            adresse = self._interroger_nominatim(compte.latitude,
                                                 compte.longitude)
            if adresse is None:
                compte.geocodage_statut = 'erreur'
            else:
                ville = (adresse.get('city') or adresse.get('town')
                         or adresse.get('village') or adresse.get('municipality')
                         or adresse.get('county'))
                compte.write({
                    'ville_geocodee': ville or False,
                    'wilaya_geocodee': adresse.get('state') or False,
                    'geocodage_statut': 'fait' if ville else 'sans_resultat',
                    'geocodage_le': fields.Datetime.now(),
                    'geocodage_latitude': compte.latitude,
                    'geocodage_longitude': compte.longitude,
                })
                if ville:
                    # ⚠️ On n'écrit QUE la ville sur le partenaire, jamais les
                    # coordonnées : `base_geolocalize`, s'il est installé,
                    # remet `partner_latitude`/`partner_longitude` à 0 dès
                    # qu'un champ d'adresse change. Nos coordonnées vivent sur
                    # CE modèle, hors de sa portée.
                    compte.partner_id.write({'city': ville})
            traitees += 1
            self.env.cr.commit()
            time.sleep(PAUSE_ENTRE_APPELS)
        if traitees:
            _logger.info("echango_promo_crm : %d fiche(s) géocodée(s)", traitees)
        return traitees

    def _interroger_nominatim(self, lat, lng):
        """L'adresse d'un point, ou `None` si l'appel a échoué.

        ⚠️ **`None` et un dictionnaire vide ne disent pas la même chose** : le
        premier est un échec réseau (à réessayer), le second un point sans
        adresse connue (à ne pas réessayer indéfiniment). Les confondre ferait
        soit boucler, soit abandonner des fiches réparables.
        """
        parametres = urllib.parse.urlencode({
            'format': 'jsonv2', 'lat': lat, 'lon': lng,
            'zoom': 10, 'accept-language': LANGUE,
        })
        requete = urllib.request.Request(
            '%s?%s' % (URL_NOMINATIM, parametres),
            headers={'User-Agent': 'echango-promo-crm/1.0 (+echango.com)'})
        try:
            with urllib.request.urlopen(requete, timeout=20) as reponse:
                return json.loads(reponse.read()).get('address', {})
        except Exception as erreur:  # noqa: BLE001 — réseau, quota, format
            _logger.warning("echango_promo_crm : géocodage refusé (%s)", erreur)
            return None

    def action_geocoder_maintenant(self):
        """Bouton : géocoder ces fiches sans attendre la tâche planifiée."""
        self._marquer_a_geocoder()
        traitees = self._geocoder_lot(len(self))
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'message': _("%s fiche(s) traitée(s).", traitees),
                'type': 'success' if traitees else 'warning',
                'sticky': False,
            },
        }
