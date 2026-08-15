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
import unicodedata
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

#: Préfixes et suffixes administratifs que Nominatim ajoute selon la complétude
#: de la donnée OSM : « Emirate of Dubai », « Wilaya de Djelfa ». Comparés sur
#: la forme déjà normalisée (sans espace ni accent), donc écrits pareil.
AFFIXES_ETAT = (
    'emirateof', 'wilayade', 'wilayad', 'provincede', 'provinceof',
    'governorateof', 'gouvernoratde',
)
SUFFIXES_ETAT = ('emirate', 'governorate', 'gouvernorat', 'province', 'wilaya')

#: ⚠️ **Le nom officiel ne suffit pas à apparier.** Nominatim rend « Dubaï » en
#: français, « Dubai » en anglais, et « Abu Dhabi » là où la donnée OSM n'est
#: pas traduite — `accept-language=fr` est une *préférence*, pas une garantie.
#: Un appariement sur le seul nom échouerait donc en silence : l'État resterait
#: vide et rien ne dirait pourquoi (règle #29).
#:
#: ⚠️ **Les deux pays penchent en sens INVERSE, et c'est tout l'intérêt de
#: cette table.** Les wilayas viennent du fichier de ce module, écrites en
#: français : ce sont les graphies *anglaises* qu'il faut rattraper. Les
#: émirats viennent d'Odoo, écrits en anglais (« Abu Dhabi », « Ras
#: al-Khaimah ») : ce sont les graphies *françaises* qu'il faut rattraper —
#: alors même qu'on demande `accept-language=fr`. Une table écrite dans un
#: seul sens n'en couvrirait que la moitié.
#:
#: Clé : code ISO du pays. Valeur : {forme normalisée → code ISO de l'état}.
#: Les formes sont normalisées par `normaliser_nom_etat` — les écrire ici sous
#: cette forme évite de dépendre de l'orthographe exacte.
#:
#: N'y figurent que les graphies que l'accent-et-casse ne rattrape PAS.
#: « Sétif » ↔ « Setif » ou « Dubaï » ↔ « Dubai » se règlent tout seuls.
ALIAS_ETATS = {
    # Base Odoo : Ajman, Abu Dhabi, Dubai, Fujairah, Ras al-Khaimah, Sharjah,
    # Umm al-Quwain.
    'AE': {
        'aboudabi': 'AZ', 'aboudhabi': 'AZ', 'abouzabi': 'AZ',
        'abuzaby': 'AZ', 'abuzabi': 'AZ',
        'doubai': 'DU', 'dubayy': 'DU',
        'charjah': 'SH', 'chardjah': 'SH', 'ashshariqah': 'SH',
        'shariqah': 'SH',
        'adjman': 'AJ', 'ajman': 'AJ',
        'oummalqaiwain': 'UQ', 'ummalquwain': 'UQ', 'ummalqaywayn': 'UQ',
        'raselkhaimah': 'RK', 'rasalkhaimah': 'RK', 'rasalkhaymah': 'RK',
        'fujaira': 'FU', 'foujairah': 'FU', 'alfujayrah': 'FU',
    },
    # Base : `data/res_country_state_dz.xml` de ce module, en français.
    'DZ': {
        'algiers': '16', 'aljazair': '16',
        'wahran': '31',
        'bougie': '06',
        'elgolea': '58', 'meniaa': '58',
        'tamanghasset': '11',
    },
}


class QuotaNominatimDepasse(Exception):
    """Nominatim a répondu 429 : arrêter le lot, ne pas insister."""


def normaliser_nom_etat(nom):
    """La forme sur laquelle deux noms d'état se comparent.

    Minuscules, accents retirés, **tout séparateur supprimé** — espaces,
    apostrophes, tirets. « M'Sila », « M Sila » et « Msila » deviennent le même
    « msila », « Sidi Bel-Abbès » devient « sidibelabbes ».

    ⚠️ **Supprimer les séparateurs plutôt que de les normaliser** est délibéré :
    c'est sur eux que les graphies divergent le plus (« Ras Al Khaimah » /
    « Ras al-Khaimah » / « RasAlKhaimah »), et le risque de confondre deux
    états distincts d'un même pays par ce biais est nul — on ne compare jamais
    qu'à l'intérieur d'un pays.

    Rend `''` pour une entrée vide, jamais `None` : une chaîne vide ne peut
    apparier aucun état, alors qu'un `None` ferait planter la comparaison.
    """
    if not nom:
        return ''
    sans_accent = ''.join(
        c for c in unicodedata.normalize('NFD', nom)
        if unicodedata.category(c) != 'Mn'
    )
    reduit = ''.join(c for c in sans_accent.lower() if c.isalnum())
    for affixe in AFFIXES_ETAT:
        if reduit.startswith(affixe) and len(reduit) > len(affixe):
            reduit = reduit[len(affixe):]
            break
    for suffixe in SUFFIXES_ETAT:
        if reduit.endswith(suffixe) and len(reduit) > len(suffixe):
            reduit = reduit[:-len(suffixe)]
            break
    return reduit


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
        avec_position = [('latitude', '!=', 0), ('longitude', '!=', 0)]
        a_faire = self.search(
            [('geocodage_statut', '=', 'a_faire')] + avec_position,
            limit=limite)
        # ⚠️ **`erreur` n'est PAS un état terminal, et le croire perdait 61
        # fiches.** Ses causes sont transitoires par nature — réseau coupé,
        # Nominatim en 429, délai dépassé. Ne chercher que `a_faire` laissait
        # ces fiches sans ville *pour toujours*, alors qu'un simple second
        # passage les résout. Elles viennent APRÈS le travail neuf : une panne
        # persistante ne doit pas monopoliser le lot.
        if len(a_faire) < limite:
            a_faire |= self.search(
                [('geocodage_statut', '=', 'erreur')] + avec_position,
                limit=limite - len(a_faire))
        traitees = 0
        for compte in a_faire:
            try:
                adresse = self._interroger_nominatim(compte.latitude,
                                                     compte.longitude)
            except QuotaNominatimDepasse:
                # ⚠️ **On s'arrête, on n'enchaîne pas.** Insister sous 429,
                # c'est transformer une limitation temporaire en bannissement
                # d'IP — et le bannissement se découvre des jours après. Les
                # fiches non traitées gardent leur état : le passage suivant
                # les reprendra.
                _logger.warning(
                    "echango_promo_crm : quota Nominatim atteint, lot "
                    "interrompu après %d fiche(s)", traitees)
                break
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
                    # ⚠️ On n'écrit QUE l'adresse sur le partenaire, jamais les
                    # coordonnées : `base_geolocalize`, s'il est installé,
                    # remet `partner_latitude`/`partner_longitude` à 0 dès
                    # qu'un champ d'adresse change. Nos coordonnées vivent sur
                    # CE modèle, hors de sa portée.
                    adresse_partenaire = {'city': ville}
                    etat = compte._etat_correspondant(adresse.get('state'))
                    if etat:
                        adresse_partenaire['state_id'] = etat.id
                    compte.partner_id.write(adresse_partenaire)
            traitees += 1
            self._valider_progression()
            time.sleep(PAUSE_ENTRE_APPELS)
        if traitees:
            _logger.info("echango_promo_crm : %d fiche(s) géocodée(s)", traitees)
        return traitees

    def _valider_progression(self):
        """Grave ce qui vient d'être géocodé, fiche par fiche.

        ⚠️ **Un lot de 25 fiches dure 30 secondes de réseau.** Sans validation
        intermédiaire, une coupure à la 24ᵉ perdrait les 23 précédentes — et
        les ferait toutes redemander au passage suivant, ce qui est justement
        la façon de se faire bannir par Nominatim.

        ⚠️ **Cette méthode existe pour être remplaçable en test**, parce
        qu'Odoo interdit `cr.commit()` dans un `TransactionCase` : il casserait
        le retour arrière de fin de test. Ce qui n'est donc PAS couvert par les
        bancs, et qu'il faut savoir : la durabilité intermédiaire elle-même.
        Toute la logique au-dessus — reprise des échecs, arrêt sur quota,
        appariement d'état — l'est.
        """
        self.env.cr.commit()

    def _etat_correspondant(self, nom_etat):
        """L'`res.country.state` qui porte ce nom, dans le pays du commerçant.

        ⚠️ **Rien n'est créé ici.** Un état inventé à la volée polluerait une
        table de référence partagée par tout Odoo — et les positions
        aberrantes en fabriqueraient : le décor porte quatre commerces à
        « Mountain View, Californie », la position par défaut de l'émulateur
        Android. Le nom de wilaya reste dans `wilaya_geocodee` quoi qu'il
        arrive ; c'est l'État natif qui reste vide quand on ne le connaît pas.

        ⚠️ **Odoo ne livre AUCUNE wilaya algérienne ni AUCUN émirat** : sans
        les fichiers de référence de ce module, cette recherche ne trouverait
        jamais rien pour `DZ` ni pour `AE`, et l'« État » d'une fiche
        algérienne ou émiratie resterait vide pour toujours — sans que rien ne
        dise pourquoi. Vérifié le 2026-08-15 : `res_country_state` portait
        zéro ligne pour ces deux pays.

        ⚠️ **La comparaison se fait en Python, pas en SQL.** Un `=ilike`
        rapproche « Setif » de « Sétif » mais **pas** « Abu Dhabi » de
        « Abou Dabi », et `unaccent` n'est pas garanti installé sur la base.
        On charge donc les états du pays — 58 au maximum ici — et on compare
        des formes normalisées. Une recherche par pays, pas une par nom : le
        coût est le même et la tolérance est celle qu'il faut.
        """
        self.ensure_one()
        pays = self.partner_id.country_id
        if not nom_etat or not pays:
            return self.env['res.country.state']

        cherche = normaliser_nom_etat(nom_etat)
        if not cherche:
            return self.env['res.country.state']

        etats = self.env['res.country.state'].search([
            ('country_id', '=', pays.id)])
        for etat in etats:
            if normaliser_nom_etat(etat.name) == cherche:
                return etat

        code = ALIAS_ETATS.get(pays.code, {}).get(cherche)
        if code:
            for etat in etats:
                if etat.code == code:
                    return etat
            # ⚠️ Un alias qui désigne un état absent de la base est une erreur
            # de CE fichier, pas une donnée manquante : le dire, sinon la
            # faute se confond avec un géocodage qui n'a rien trouvé.
            _logger.warning(
                "echango_promo_crm : alias « %s » → %s/%s, mais aucun état de "
                "ce code en base", nom_etat, pays.code, code)
        return self.env['res.country.state']

    def _interroger_nominatim(self, lat, lng):
        """L'adresse d'un point, ou `None` si l'appel a échoué.

        ⚠️ **`None` et un dictionnaire vide ne disent pas la même chose** : le
        premier est un échec réseau (à réessayer), le second un point sans
        adresse connue (à ne pas réessayer indéfiniment). Les confondre ferait
        soit boucler, soit abandonner des fiches réparables.

        ⚠️ **Et un 429 n'est ni l'un ni l'autre** : c'est le service qui dit
        « trop vite ». Il lève `QuotaNominatimDepasse` plutôt que de rendre
        `None`, parce que la seule réaction juste est d'arrêter le lot — le
        marquer en `erreur` comme un échec ordinaire ferait enchaîner
        vingt-quatre appels de plus, tous refusés, et changerait une
        limitation en bannissement.
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
        except urllib.error.HTTPError as erreur:
            if erreur.code == 429:
                raise QuotaNominatimDepasse() from erreur
            _logger.warning("echango_promo_crm : géocodage refusé (HTTP %s)",
                            erreur.code)
            return None
        except Exception as erreur:  # noqa: BLE001 — réseau, format
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
