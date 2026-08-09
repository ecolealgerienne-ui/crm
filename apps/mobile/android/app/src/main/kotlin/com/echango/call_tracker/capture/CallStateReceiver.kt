package com.echango.call_tracker.capture

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.telephony.TelephonyManager
import android.util.Log
import com.echango.call_tracker.sync.SyncWorker

/**
 * Détecte la fin d'un appel et déclenche la lecture du journal.
 *
 * Ce receveur ne lit RIEN lui-même. Un `BroadcastReceiver` dispose d'une
 * dizaine de secondes avant d'être tué, et le système écrit dans `CallLog` de
 * façon asynchrone : lire ici trouverait souvent un journal pas encore à jour.
 * Il se contente donc de planifier le travail, que WorkManager mènera à son
 * terme même si le processus disparaît entre-temps.
 */
class CallStateReceiver : BroadcastReceiver() {

    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action != TelephonyManager.ACTION_PHONE_STATE_CHANGED) return

        val etat = intent.getStringExtra(TelephonyManager.EXTRA_STATE) ?: return
        val precedent = dernierEtat

        dernierEtat = etat

        // Seule la transition « le téléphone se libère » nous intéresse : c'est
        // à ce moment que l'appel est terminé, donc que sa durée est connue et
        // que le journal système va être écrit.
        //
        // Le test sur l'état précédent élimine les diffusions IDLE → IDLE, que
        // le système émet notamment au démarrage et après un appel déjà traité.
        // Sans lui, chaque diffusion parasite planifierait un balayage.
        val appelTermine = etat == TelephonyManager.EXTRA_STATE_IDLE &&
            (precedent == TelephonyManager.EXTRA_STATE_OFFHOOK ||
                precedent == TelephonyManager.EXTRA_STATE_RINGING)

        if (!appelTermine) return

        Log.i("CallTracker", "Fin d'appel detectee, balayage planifie")
        SyncWorker.planifier(context, delaiSecondes = DELAI_ECRITURE_JOURNAL)
    }

    private companion object {
        /**
         * Laisse au système le temps d'écrire l'appel dans `CallLog`.
         *
         * Cinq secondes est un compromis mesuré ailleurs dans l'écosystème
         * Android : l'écriture est quasi immédiate sur la plupart des
         * appareils, mais peut traîner sur les surcouches constructeur. Et le
         * délai est sans conséquence sur le résultat — un appel manqué par ce
         * balayage-ci sera rattrapé par le suivant, le curseur
         * `lastScanMillis` ne progressant que sur ce qui a été lu.
         */
        const val DELAI_ECRITURE_JOURNAL = 5L

        /**
         * État précédent, en mémoire de processus.
         *
         * Volontairement pas persisté : si le processus meurt entre deux
         * diffusions, on retombe sur IDLE et on rate au pire le déclenchement
         * d'un balayage — que le prochain appel, l'ouverture de
         * l'application ou le redémarrage rattraperont, puisque le journal
         * système, lui, garde tout.
         */
        @Volatile
        var dernierEtat: String? = null
    }
}
