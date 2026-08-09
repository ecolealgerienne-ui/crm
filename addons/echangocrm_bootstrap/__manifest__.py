# -*- coding: utf-8 -*-
{
    'name': "EchangoCrm — amorçage",
    'version': '19.0.1.0.0',
    'category': 'Technical',
    'summary': "Applique le mot de passe administrateur depuis l'environnement",
    'description': """
Module d'amorçage d'EchangoCrm
==============================

Odoo crée l'utilisateur ``admin`` avec le mot de passe ``admin``. Sur une
instance publiée sur Internet, cela laisse le CRM ouvert à quiconque connaît
l'URL, entre la création de la base et le premier changement manuel.

Ce module ferme cette fenêtre : son ``post_init_hook`` applique le mot de passe
fourni par la variable d'environnement ``ODOO_ADMIN_PASSWORD``, dans la
transaction même qui installe les modules. Le serveur ne répond donc jamais
avec le mot de passe par défaut.

Il n'ajoute aucun modèle, aucune vue, aucune donnée. Il ne s'exécute qu'à
l'installation : changer la variable plus tard n'a aucun effet, le mot de passe
se modifie alors depuis l'interface (Préférences), là où il doit l'être.
""",
    'author': "echango",
    'license': 'LGPL-3',
    'depends': ['base'],
    'post_init_hook': 'post_init_hook',
    'installable': True,
    'auto_install': False,
    'application': False,
}
