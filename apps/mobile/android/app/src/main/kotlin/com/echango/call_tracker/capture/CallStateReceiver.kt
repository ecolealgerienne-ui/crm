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
 * La fiche CRM à la sonnerie ne passe PAS par ici : voir
 * [FiltrageAppelService]. Ce receveur ne sert plus qu'à deux choses — savoir
 * qu'un appel s'est terminé, et retirer la surimpression.
 *
 * Ce receveur ne lit jamais `CallLog` lui-même. Un `BroadcastReceiver` dispose
 * d'une dizaine de secondes avant d'être tué, et le système écrit dans le
 * journal de façon asynchrone : lire ici trouverait souvent un journal pas
 * encore à jour. Il planifie donc le travail, que WorkManager mènera à son
 * terme même si le processus disparaît entre-temps.
 */
class CallStateReceiver : BroadcastReceiver() {

    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action != TelephonyManager.ACTION_PHONE_STATE_CHANGED) return

        val etat = intent.getStringExtra(TelephonyManager.EXTRA_STATE) ?: return
        val precedent = dernierEtat
        dernierEtat = etat

        when (etat) {
            // Rien à faire à la sonnerie : c'est FiltrageAppelService qui
            // fournit le numéro et déclenche la fiche. Voir sa docstring —
            // EXTRA_INCOMING_NUMBER arrive vide sur les Android récents.
            TelephonyManager.EXTRA_STATE_RINGING -> Unit
            TelephonyManager.EXTRA_STATE_IDLE -> aLaFin(context, precedent)
            // OFFHOOK : l'utilisateur a décroché, ou un appel sortant commence.
            // La fiche a fait son office, elle laisse la place à l'écran d'appel.
            TelephonyManager.EXTRA_STATE_OFFHOOK -> CallerIdOverlay.cacher(context)
        }
    }

    private fun aLaFin(context: Context, precedent: String?) {
        CallerIdOverlay.cacher(context)

        // Seule la transition « le téléphone se libère après un appel »
        // intéresse la journalisation : c'est à ce moment que la durée est
        // connue et que le journal système va être écrit.
        //
        // Le test sur l'état précédent élimine les diffusions IDLE → IDLE, que
        // le système émet notamment au démarrage. Sans lui, chaque diffusion
        // parasite planifierait un balayage.
        val appelTermine = precedent == TelephonyManager.EXTRA_STATE_OFFHOOK ||
            precedent == TelephonyManager.EXTRA_STATE_RINGING
        if (!appelTermine) return

        Log.i(TAG, "Fin d'appel detectee, balayage planifie")
        SyncWorker.planifier(context, delaiSecondes = DELAI_ECRITURE_JOURNAL)
    }

    private companion object {
        const val TAG = "CallTracker"

        /**
         * Laisse au système le temps d'écrire l'appel dans `CallLog`.
         *
         * Cinq secondes : l'écriture est quasi immédiate sur la plupart des
         * appareils, mais peut traîner sur les surcouches constructeur. Le
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
         * d'un balayage — que le prochain appel, l'ouverture de l'application
         * ou le redémarrage rattraperont, puisque le journal système, lui,
         * garde tout.
         */
        @Volatile
        var dernierEtat: String? = null
    }
}
