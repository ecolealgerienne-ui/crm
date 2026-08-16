# -*- coding: utf-8 -*-
"""Supprime la vue SQL `echango_promo_suivi`, qu'Odoo laisse derrière lui.

⚠️ **Odoo ne supprime PAS la table d'un modèle retiré du code.** Mesuré le
2026-08-16 sur la base de développement : à la mise à jour, il efface bien les
23 `ir.model.fields` et l'`ir.model`, puis renonce en INFO — noyé au milieu de
soixante lignes de suppressions :

    The model echango.promo.suivi could not be dropped because it did not exist
    in the registry.

La raison est mécanique : pour supprimer une table il faut savoir si c'en est
une ou si c'est une vue, et cela se lit dans le modèle — qui vient précisément
d'être retiré du code. Le nettoyage arrive donc trop tard pour lui-même.

⚠️ **Conséquence si l'on ne fait rien** : la vue reste en base, sans modèle, sans
écran, sans lecteur — et elle continue de dépendre de `echango_promo_account` et
`res_partner`, dont elle bloquerait un jour une migration de colonne, sans que
personne ne sache d'où elle vient. C'est exactement le défaut que la suppression
de cet écran vise à ne plus laisser traîner.

`CASCADE` : rien ne dépend d'elle aujourd'hui, mais une vue construite sur
celle-ci par un administrateur en base ne doit pas faire échouer la mise à jour
en silence — elle tomberait avec, et le journal le dirait.
"""
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    # Un `if not version` n'est pas nécessaire : Odoo ne joue les migrations
    # que sur une mise à jour, jamais sur une installation neuve — et une
    # installation neuve n'a jamais eu cette vue.
    cr.execute("""
        SELECT table_type FROM information_schema.tables
         WHERE table_schema = 'public' AND table_name = 'echango_promo_suivi'
    """)
    trouvee = cr.fetchone()
    if not trouvee:
        _logger.info("echango_promo_suivi absente de la base, rien a supprimer")
        return

    # ⚠️ On dit ce qu'on a trouvé AVANT d'agir : si un jour ce n'est plus une
    # vue mais une table, le journal portera la trace de ce qu'on a détruit.
    _logger.info("suppression de echango_promo_suivi (%s)", trouvee[0])
    cr.execute("DROP VIEW IF EXISTS echango_promo_suivi CASCADE")
