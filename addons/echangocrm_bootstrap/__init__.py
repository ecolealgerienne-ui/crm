# -*- coding: utf-8 -*-
# Le nom `post_init_hook` doit être résoluble depuis le paquet du module :
# c'est ainsi qu'Odoo retrouve la fonction nommée dans __manifest__.py.
from .hooks import post_init_hook
