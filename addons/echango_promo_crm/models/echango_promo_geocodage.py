# -*- coding: utf-8 -*-
"""L'appariement d'un nom de wilaya vers un `res.country.state` d'Odoo.

⚠️ **Le géocodage inverse ne se fait plus ici depuis le 2026-09-05.** Deux
implémentations Nominatim indépendantes coexistaient dans l'écosystème (ce
module et le BFF d'echango-delivery). Le référentiel géographique appartient
au service transverse `echango-geo` ; le commerçant appartient à echango
Promo, qui résout sa position en `ville`/`wilaya` **au moment où elle est
posée** et transmet le résultat dans l'instantané nocturne
(`ville`, `wilaya`, `geocodage_statut` — voir `controllers/main.py`).

Ce qui a disparu d'ici : `_interroger_nominatim`, le throttle d'une requête
par seconde, `QuotaNominatimDepasse` et la gestion du 429, les lots de 25, le
seuil de dérive de 200 m, la tâche planifiée `_cron_geocoder`. echango Promo
étant le seul écrivain de la position, il n'y a plus de dérive à détecter ici.

Ce qui **reste**, parce que c'est spécifique à Odoo et hors du périmètre
d'`echango-geo` (§4 de ses specs — « rend un nom de wilaya en texte propre,
jamais un identifiant d'une base tierce ») : `_etat_correspondant` et sa table
d'alias, qui rapprochent le nom reçu du `res.country.state` natif.
"""
import logging
import unicodedata

from odoo import fields, models

_logger = logging.getLogger(__name__)

#: Préfixes et suffixes administratifs que Nominatim ajoute selon la complétude
#: de la donnée OSM : « Emirate of Dubai », « Wilaya de Djelfa ». Comparés sur
#: la forme déjà normalisée (sans espace ni accent), donc écrits pareil.
AFFIXES_ETAT = (
    'emirateof', 'wilayade', 'wilayad', 'provincede', 'provinceof',
    'governorateof', 'gouvernoratde',
)
SUFFIXES_ETAT = ('emirate', 'governorate', 'gouvernorat', 'province', 'wilaya')

#: ⚠️ **Le nom officiel ne suffit pas à apparier.** `echango-geo` demande
#: `accept-language=fr` à Nominatim, mais c'est une *préférence*, pas une
#: garantie : « Dubaï » en français, « Dubai » en anglais, « Abu Dhabi » là où
#: la donnée OSM n'est pas traduite. Un appariement sur le seul nom échouerait
#: en silence : l'État resterait vide et rien ne dirait pourquoi (règle #29).
#:
#: ⚠️ **Les deux pays penchent en sens INVERSE.** Les wilayas viennent du
#: fichier de ce module, en français : ce sont les graphies *anglaises* qu'il
#: faut rattraper. Les émirats viennent d'Odoo, en anglais : ce sont les
#: graphies *françaises* qu'il faut rattraper — alors même qu'on demande le
#: français. Une table écrite dans un seul sens n'en couvrirait que la moitié.
#:
#: Clé : code ISO du pays. Valeur : {forme normalisée → code ISO de l'état}.
#: N'y figurent que les graphies que l'accent-et-casse ne rattrape PAS.
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


class EchangoPromoAccount(models.Model):
    _inherit = 'echango.promo.account'

    #: ⚠️ **Cinq états distincts, pas un booléen** (règle #29). « Pas de
    #: position », « pas encore résolu », « résolu sans résultat » et « échec »
    #: se ressemblent à l'écran — une case vide — et appellent des gestes
    #: opposés. Renseigné par le contrôleur à partir de l'instantané reçu ;
    #: `a_faire`/`erreur` sont transitoires (le reconcile d'echango Promo les
    #: reprend), `sans_resultat` est terminal (point non cartographié).
    geocodage_statut = fields.Selection(
        [('sans_position', "Sans position GPS"),
         ('a_faire', "À géocoder"),
         ('fait', "Géocodé"),
         ('sans_resultat', "Géocodé, sans résultat"),
         ('erreur', "Échec du géocodage")],
        string="Géocodage", default='sans_position', readonly=True, index=True,
    )
    ville_geocodee = fields.Char(string="Ville (géocodée)", readonly=True)
    wilaya_geocodee = fields.Char(string="Wilaya (géocodée)", readonly=True)

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
        jamais rien pour `DZ` ni pour `AE`.

        ⚠️ **La comparaison se fait en Python, pas en SQL.** Un `=ilike`
        rapproche « Setif » de « Sétif » mais **pas** « Abu Dhabi » de
        « Abou Dabi », et `unaccent` n'est pas garanti installé sur la base.
        On charge donc les états du pays — 58 au maximum ici — et on compare
        des formes normalisées.
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
