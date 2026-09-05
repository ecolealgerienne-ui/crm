# -*- coding: utf-8 -*-
"""Bascule du géocodage inverse vers echango-geo (2026-09-05).

Ce module ne géocode plus : echango Promo résout la position d'un commerçant
en `ville`/`wilaya` au moment où elle est posée et le transmet dans
l'instantané. Deux nettoyages qu'Odoo ne fait pas seul :

1. **Le cron `cron_echango_promo_geocodage`.** Le fichier `data/ir_cron.xml`
   est `noupdate="1"` : retirer le record de l'XML ne le supprime pas en
   base. Sans ce `unlink`, Odoo tenterait toutes les 15 minutes d'appeler
   `model._cron_geocoder()`, méthode qui n'existe plus → une exception au
   journal à chaque passage.

2. **Les colonnes de détection de dérive** — `geocodage_le`,
   `geocodage_latitude`, `geocodage_longitude`. Elles servaient au seuil des
   200 m, que le cron portait. echango Promo étant désormais le seul écrivain
   de la position et re-géocodant à chaque changement, il n'y a plus de
   dérive à mesurer ici. Odoo retire l'`ir.model.fields` mais **jamais la
   colonne** d'un champ supprimé du code (même mécanique que
   `19.0.1.1.0/post-migration.py`).
"""
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    # ── 1. Le cron orphelin ────────────────────────────────────────────────
    cr.execute("""
        DELETE FROM ir_cron
         WHERE id IN (
            SELECT res_id FROM ir_model_data
             WHERE module = 'echango_promo_crm'
               AND name = 'cron_echango_promo_geocodage'
               AND model = 'ir.cron'
         )
    """)
    if cr.rowcount:
        _logger.info("cron_echango_promo_geocodage supprime (%d ligne)",
                     cr.rowcount)
    cr.execute("""
        DELETE FROM ir_model_data
         WHERE module = 'echango_promo_crm'
           AND name = 'cron_echango_promo_geocodage'
    """)

    # ── 2. Les colonnes de dérive ─────────────────────────────────────────
    for colonne in ('geocodage_le', 'geocodage_latitude', 'geocodage_longitude'):
        cr.execute("""
            SELECT 1 FROM information_schema.columns
             WHERE table_name = 'echango_promo_account' AND column_name = %s
        """, (colonne,))
        if cr.fetchone():
            _logger.info("suppression de echango_promo_account.%s", colonne)
            cr.execute(
                'ALTER TABLE echango_promo_account DROP COLUMN "%s"' % colonne)
