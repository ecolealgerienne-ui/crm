# =============================================================================
# EchangoCrm — image Odoo
# =============================================================================
# Image officielle Odoo, presque nue. Le seul ajout est un entrypoint qui rend
# `odoo.conf` à partir d'un template au démarrage.
#
# Pourquoi ne pas simplement monter un `odoo.conf` en volume : le mot de passe
# maître (`admin_passwd`, celui qui autorise création / suppression /
# duplication de base) ne peut vivre QUE dans le fichier de configuration —
# Odoo n'offre aucune variable d'environnement ni option CLI équivalente. Un
# `odoo.conf` versionné porterait donc ce secret dans le dépôt. Le template
# reste versionné (relisible, diffable), les valeurs viennent de
# `.env.production`, et le fichier rendu ne quitte jamais le conteneur.
# =============================================================================

ARG ODOO_IMAGE_TAG=19
FROM odoo:${ODOO_IMAGE_TAG}

USER root

COPY odoo.conf.template /etc/odoo/odoo.conf.template
COPY entrypoint-echangocrm.sh /usr/local/bin/entrypoint-echangocrm.sh

# /etc/odoo appartient à root dans l'image amont, et le conteneur tourne en
# utilisateur `odoo` : sans ce chown, le rendu du template échoue en
# « Permission denied » au premier démarrage.
RUN chmod 0755 /usr/local/bin/entrypoint-echangocrm.sh \
 && chown -R odoo:odoo /etc/odoo

USER odoo

# Notre entrypoint rend la configuration puis délègue à celui de l'image
# amont (/entrypoint.sh), qui attend Postgres et lance Odoo. On ne le
# remplace pas : il porte `wait-for-psql.py` et la construction des arguments
# `--db_*`, autant de comportement amont qu'on n'a aucune raison de réécrire.
ENTRYPOINT ["/usr/local/bin/entrypoint-echangocrm.sh"]
CMD ["odoo"]
