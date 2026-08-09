package com.echango.call_tracker.capture

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import com.echango.call_tracker.sync.SyncWorker

/**
 * Relance la remise des appels restés en file après un redémarrage.
 *
 * WorkManager reprogramme ses tâches au démarrage, mais un appel capturé
 * pendant que le réseau était coupé, suivi d'une extinction du téléphone, ne
 * serait relancé qu'à l'appel suivant. Or c'est exactement le scénario du
 * commercial en déplacement : zone blanche, batterie à plat, rallumage le
 * lendemain.
 */
class BootReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action != Intent.ACTION_BOOT_COMPLETED) return
        SyncWorker.planifier(context)
    }
}
