# -*- coding: utf-8 -*-
{
    'name': "echango Promo — suivi commerçants",
    'version': '19.0.1.0.0',
    'category': 'Sales/CRM',
    'summary': "Reçoit l'instantané nocturne des commerçants d'echango Promo",
    'description': """
echango Promo → EchangoCrm
==========================

Reçoit chaque nuit l'état des commerçants d'echango Promo : dernière
publication, promos en ligne et visibles, motif de blocage, portée. Le
contrat d'échange est **unique et vit dans l'autre dépôt** —
`docs/SPEC_INTEGRATION_ECHANGOCRM.md` d'echangopromo. Ne pas le recopier ici :
deux copies d'un contrat divergent au premier changement.

**Pourquoi un contrôleur plutôt que l'API générique d'Odoo.** Même raison que
`call_tracker` : une clé API Odoo hérite des droits complets de son
utilisateur, et il n'existe aucun moyen natif de restreindre un accès externe à
« écrire des fiches de suivi ». Ce module expose ses propres routes, avec son
propre jeton, révocable indépendamment de tout compte. Le jeton ne porte aucun
droit Odoo : c'est le contrôleur qui décide de ce qui est écrit.

**Ce que ce module ne fait pas.** Il n'écrit jamais vers echango Promo. Un
commerçant bloqué se débloque dans Promo, pas ici — dupliquer ses écrans
créerait deux endroits où valider un registre.
""",
    'author': "echango",
    'license': 'LGPL-3',
    'depends': [
        'crm',
        # ⚠️ Déclaré explicitement bien qu'`auto_install` : `phone_sanitized`
        # en vient, et une dépendance implicite n'est pas une dépendance —
        # elle disparaît à la première montée de version du parent.
        'phone_validation',
    ],
    'data': [
        # Les groupes d'abord : le CSV d'accès et les règles y font référence.
        'security/echango_promo_groups.xml',
        'security/ir.model.access.csv',
        'security/echango_promo_rules.xml',
        # ⚠️ Aucun équivalent pour les Émirats : Odoo livre déjà ses 7 émirats
        # (vérifié le 2026-08-15), en anglais et avec les mêmes codes ISO. Un
        # fichier de référence de plus violait `res_country_state_name_code_uniq`
        # et empêchait purement et simplement l'installation du module. C'est
        # `ALIAS_ETATS` qui rattrape l'écart de langue, pas une seconde copie
        # des données.
        'data/res_country_state_dz.xml',
        'data/ir_cron.xml',
        'views/echango_promo_source_views.xml',
        'views/echango_promo_token_wizard_views.xml',
        'views/echango_promo_account_views.xml',
        'views/echango_promo_suivi_views.xml',
        'views/echango_promo_campagne_views.xml',
        'views/echango_promo_commercants_views.xml',
        'views/echango_promo_audit_views.xml',
        'views/res_partner_views.xml',
        'views/echango_promo_menus.xml',
    ],
    'installable': True,
    'application': False,
}
