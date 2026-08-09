#!/bin/bash
# =============================================================================
# EchangoCrm — rendu de odoo.conf, puis délégation à l'entrypoint Odoo amont
# =============================================================================
set -euo pipefail

ODOO_RC="${ODOO_RC:-/etc/odoo/odoo.conf}"
TEMPLATE=/etc/odoo/odoo.conf.template

# --- Secrets obligatoires --------------------------------------------------
# Échouer ici, bruyamment, plutôt que de démarrer sur une valeur par défaut :
# un Odoo qui tourne avec un mot de passe maître vide expose la création et la
# suppression de bases à quiconque atteint l'URL.
manquants=()
for var in POSTGRES_PASSWORD ODOO_ADMIN_PASSWD ODOO_DB_NAME; do
  if [ -z "${!var:-}" ]; then
    manquants+=("$var")
  fi
done
if [ ${#manquants[@]} -gt 0 ]; then
  echo "[FATAL] variable(s) absente(s) ou vide(s) dans .env.production : ${manquants[*]}" >&2
  exit 1
fi

# --- Le mot de passe Postgres ne peut pas contenir d'espace ----------------
# Ce n'est pas une préférence de style. L'entrypoint amont relit les valeurs
# `db_*` du fichier rendu avec `cut -d " " -f3` pour reconstruire les
# arguments `--db_password` : un espace dans le mot de passe tronque
# silencieusement la valeur, et l'erreur qui remonte est
# « password authentication failed », qui n'oriente pas du tout vers la vraie
# cause. Voir aussi le commentaire de .env.production.example.
case "$POSTGRES_PASSWORD" in
  *[[:space:]]*)
    echo "[FATAL] POSTGRES_PASSWORD contient un espace — l'entrypoint Odoo amont" >&2
    echo "        tronquerait la valeur (cut -d ' '). Utiliser uniquement des" >&2
    echo "        caractères alphanumériques : openssl rand -hex 24" >&2
    exit 1
    ;;
esac

# --- Rendu du template ------------------------------------------------------
# python3 plutôt qu'envsubst : l'interpréteur est garanti présent (Odoo est
# écrit en Python), gettext-base ne l'est pas. `substitute` lève sur variable
# absente — on préfère un démarrage refusé à un `odoo.conf` contenant le
# littéral « ${ODOO_WORKERS} », qu'Odoo lirait comme une valeur invalide.
python3 - "$TEMPLATE" "$ODOO_RC" <<'PY'
import os, string, sys

source, destination = sys.argv[1], sys.argv[2]

with open(source, encoding="utf-8") as handle:
    template = string.Template(handle.read())

try:
    rendu = template.substitute(os.environ)
except KeyError as absente:
    sys.exit(f"[FATAL] odoo.conf.template reference {absente}, absente de l'environnement")

# 0600 : le fichier porte admin_passwd et le mot de passe Postgres en clair.
descripteur = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
with os.fdopen(descripteur, "w", encoding="utf-8") as handle:
    handle.write(rendu)
PY

exec /entrypoint.sh "$@"
