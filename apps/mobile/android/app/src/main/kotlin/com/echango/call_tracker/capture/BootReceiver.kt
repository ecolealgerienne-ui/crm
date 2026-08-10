package com.echango.call_tracker.capture

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import com.echango.call_tracker.sync.SyncWorker

/**
 * Remet en route la capture et la remise après un redémarrage.
 *
 * WorkManager reprogramme ses tâches au démarrage, mais un appel capturé
 * pendant que le réseau était coupé, suivi d'une extinction du téléphone, ne
 * serait relancé qu'à l'appel suivant. Or c'est exactement le scénario du
 * commercial en déplacement : zone blanche, batterie à plat, rallumage le
 * lendemain.
 *
 * Le balayage périodique est reposé ici parce que c'est le seul filet contre
 * les surcouches constructeur ; `KEEP` fait que le reposer sans cesse ne coûte
 * rien.
 */
class BootReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        // Plusieurs surcouches (HTC, Xiaomi) émettent leur propre action lors
        // d'un démarrage rapide, et jamais `BOOT_COMPLETED` : n'écouter que
        // cette dernière laissait la capture éteinte jusqu'au premier appel.
        if (intent.action !in ACTIONS_DEMARRAGE) return
        BalayageWorker.planifierPeriodique(context)
        BalayageWorker.planifier(context)
        SyncWorker.planifier(context)
    }

    private companion object {
        val ACTIONS_DEMARRAGE = setOf(
            Intent.ACTION_BOOT_COMPLETED,
            Intent.ACTION_LOCKED_BOOT_COMPLETED,
            "android.intent.action.QUICKBOOT_POWERON",
            "com.htc.intent.action.QUICKBOOT_POWERON",
        )
    }
}
