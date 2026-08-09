# -*- coding: utf-8 -*-
import logging
import os

_logger = logging.getLogger(__name__)

VARIABLE = 'ODOO_ADMIN_PASSWORD'


def post_init_hook(env):
    """Remplace le mot de passe ``admin`` par défaut d'Odoo.

    Appelé une seule fois, à l'installation du module, dans la transaction qui
    installe l'ensemble des modules demandés par ``--init``. Le serveur n'a
    donc à aucun moment répondu avec le couple ``admin`` / ``admin``.

    Signature à un seul argument : c'est celle des hooks depuis Odoo 17. Sur
    une version antérieure, Odoo appellerait ``(cr, registry)`` et l'appel
    échouerait bruyamment — ce qui est le bon comportement, mieux vaut un
    démarrage refusé qu'un mot de passe par défaut laissé en place.
    """
    mot_de_passe = os.environ.get(VARIABLE, '')

    if not mot_de_passe:
        # Interrompre l'installation. La transaction est annulée, le module
        # reste non installé, et l'amorçage réessaiera au prochain lancement.
        # L'alternative — se contenter d'un avertissement — laisserait un CRM
        # accessible en admin/admin derrière un journal que personne ne lit.
        raise ValueError(
            "%s est absente ou vide : impossible de fixer le mot de passe "
            "administrateur. Renseigner la variable dans .env.production, "
            "puis relancer." % VARIABLE
        )

    administrateur = env.ref('base.user_admin')
    administrateur.sudo().write({'password': mot_de_passe})

    # Ne jamais journaliser la valeur elle-même : les journaux du conteneur
    # sont lisibles par quiconque a accès à `docker compose logs`.
    _logger.info(
        "EchangoCrm : mot de passe de l'utilisateur %s appliqué depuis %s",
        administrateur.login,
        VARIABLE,
    )
