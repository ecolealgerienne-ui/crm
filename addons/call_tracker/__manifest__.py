# -*- coding: utf-8 -*-
{
    'name': "Call Tracker",
    'version': '19.0.1.0.0',
    'category': 'Sales/CRM',
    'summary': "Journalise les appels remontés par l'app mobile des commerciaux",
    'description': """
Call Tracker
============

Reçoit les appels capturés par l'application mobile Android et les journalise
dans un modèle dédié, rattachés au contact ou à la piste correspondant au
numéro.

**Pourquoi un module plutôt que l'API générique d'Odoo.** Une clé API Odoo
hérite des droits complets de l'utilisateur associé : il n'existe aucun moyen
natif de restreindre un accès externe à « écrire un journal d'appel et lire
quatre champs de contact ». Ce module expose ses propres routes, avec son
propre jeton, révocable indépendamment de tout compte utilisateur. Le jeton
n'a jamais de droits Odoo : c'est le contrôleur qui décide, en interne, de ce
qui est écrit et de ce qui est renvoyé.
""",
    'author': "echango",
    'license': 'LGPL-3',
    'depends': ['crm'],
    'data': [
        # Les groupes d'abord : le CSV d'accès et les règles y font référence.
        'security/call_tracker_groups.xml',
        'security/ir.model.access.csv',
        'security/call_tracker_rules.xml',
        'data/ir_cron.xml',
        'views/call_tracker_token_wizard_views.xml',
        'views/call_tracker_device_views.xml',
        'views/call_tracker_log_views.xml',
        'views/call_tracker_audit_views.xml',
        'views/res_partner_views.xml',
        'views/crm_lead_views.xml',
        'views/call_tracker_menus.xml',
    ],
    'installable': True,
    'application': False,
}
