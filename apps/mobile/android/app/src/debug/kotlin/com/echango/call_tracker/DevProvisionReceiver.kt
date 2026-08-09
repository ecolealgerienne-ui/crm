package com.echango.call_tracker

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.util.Log
import com.echango.call_tracker.data.SecureSettings
import com.echango.call_tracker.sync.SyncWorker

/**
 * Provisionnement de l'appareil en ligne de commande — **DÉBOGAGE UNIQUEMENT**.
 *
 * Ce fichier vit dans `src/debug/`. Il n'est pas compilé dans une variante de
 * release : le code n'existe simplement pas dans l'APK distribué. C'est la
 * seule forme acceptable pour un point d'entrée qui écrit un jeton
 * d'authentification sans aucune vérification — dans un APK de production, ce
 * serait une porte ouverte que n'importe quelle application installée pourrait
 * pousser.
 *
 * Sert à rendre le banc d'essai reproductible : régler l'adresse et le jeton à
 * la main dans l'interface à chaque réinstallation rend le test pénible, donc
 * rare, donc inutile.
 *
 *     adb shell am broadcast \
 *       -a com.echango.call_tracker.DEV_PROVISION \
 *       -n com.echango.call_tracker/.DevProvisionReceiver \
 *       --es url "http://10.0.2.2:8169" \
 *       --es token "<jeton>" \
 *       --ez enabled true
 */
class DevProvisionReceiver : BroadcastReceiver() {

    override fun onReceive(context: Context, intent: Intent) {
        val reglages = SecureSettings(context)

        intent.getStringExtra("url")?.let { reglages.serverUrl = it }
        intent.getStringExtra("token")?.let { reglages.token = it }
        if (intent.hasExtra("enabled")) {
            reglages.captureEnabled = intent.getBooleanExtra("enabled", false)
        }
        if (intent.hasExtra("fromHour")) {
            reglages.fromHour = intent.getIntExtra("fromHour", 0)
        }
        if (intent.hasExtra("toHour")) {
            reglages.toHour = intent.getIntExtra("toHour", 24)
        }
        // Repart de zéro : sans cela, un appel simulé avant le
        // provisionnement resterait derrière le curseur et ne serait
        // jamais lu.
        if (intent.getBooleanExtra("resetCursor", false)) {
            reglages.lastScanMillis = 0
        }

        Log.i(
            "CallTracker",
            "DEV provision : url=${reglages.serverUrl} " +
                "jeton=${if (reglages.token.isBlank()) "absent" else "present"} " +
                "capture=${reglages.captureEnabled} " +
                "plage=${reglages.fromHour}-${reglages.toHour}",
        )

        SyncWorker.forcer(context)
    }
}
