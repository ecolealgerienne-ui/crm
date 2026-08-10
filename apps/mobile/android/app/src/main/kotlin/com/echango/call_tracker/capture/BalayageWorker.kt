package com.echango.call_tracker.capture

import android.content.Context
import android.util.Log
import androidx.work.CoroutineWorker
import androidx.work.Data
import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.ExistingWorkPolicy
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.WorkerParameters
import com.echango.call_tracker.data.CallStore
import com.echango.call_tracker.data.SecureSettings
import com.echango.call_tracker.sync.SyncWorker
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.util.concurrent.TimeUnit

/**
 * Lit le journal d'appels et remplit la file locale. **Sans réseau.**
 *
 * Ce worker existe parce que le balayage vivait dans [SyncWorker], qui porte
 * une contrainte réseau. Deux défauts en découlaient, tous deux silencieux :
 *
 * **1. Hors réseau, rien n'était capturé.** WorkManager ne démarre pas un
 * travail dont la contrainte n'est pas satisfaite : `CallLog` n'était pas lu,
 * la file locale restait vide, aucune invite de note n'était proposée. La file
 * était pourtant documentée comme le rempart — « un appel capturé y est
 * inscrit AVANT toute tentative d'envoi ». Elle l'était en réalité *après le
 * retour du réseau*, et tout reposait entre-temps sur le journal du système,
 * qu'un utilisateur peut vider d'un geste. Une journée en zone blanche
 * ressortait ensuite d'un bloc, avec quinze notifications « Ajouter une
 * note ? » dont la plus ancienne portait sur un appel du matin.
 *
 * **2. Le rendez-vous de fin de journée était jeté.** Le balayage planifie un
 * envoi différé pour les appels retenus en attente de note. Il le faisait
 * depuis l'intérieur du worker d'envoi, sous le même nom unique, en `KEEP` :
 * WorkManager voyait un travail non terminé sous ce nom — celui en train de
 * s'exécuter — et jetait la demande. Le dernier appel de la journée restait en
 * file jusqu'au lendemain.
 *
 * Deux noms uniques distincts suffisent à fermer les deux : le balayage ne
 * peut plus bloquer l'envoi, et l'envoi ne peut plus empêcher le balayage.
 */
class BalayageWorker(
    context: Context,
    parametres: WorkerParameters,
) : CoroutineWorker(context, parametres) {

    override suspend fun doWork(): Result = withContext(Dispatchers.IO) {
        try {
            CallLogScanner.balayer(applicationContext)
        } catch (erreur: Exception) {
            // Un balayage qui échoue ne doit pas emporter la planification
            // périodique : `failure()` retirerait ce travail de la file, et la
            // capture s'arrêterait jusqu'au prochain redémarrage.
            Log.e(TAG, "Balayage en echec", erreur)
        }

        // La purge locale suit la même durée que celle qu'Odoo applique et que
        // l'écran d'information annonce. La faire ici plutôt qu'à l'envoi la
        // rend indépendante du réseau : une base qui grossit sans fin ne doit
        // pas attendre que le serveur soit joignable pour être bornée.
        val reglages = SecureSettings(applicationContext)
        val enAttente = CallStore(applicationContext).use { store ->
            store.purger(if (reglages.retentionKnown) reglages.retentionDays else 0)
            store.nombreEnAttente()
        }
        if (enAttente > 0) {
            if (inputData.getBoolean(REINITIALISER_ATTENTE, false)) {
                // Passage périodique : on force, ce qui remet à zéro le
                // compteur de tentatives de WorkManager. Sans cela, après une
                // indisponibilité du serveur le backoff exponentiel sature à
                // cinq heures, et chaque nouvelle demande en `KEEP` est jetée
                // tant qu'elle dure — le lundi matin, réseau parfait, les
                // appels partaient jusqu'à cinq heures après avoir eu lieu.
                // C'est aussi ce que `delivery_lag_minutes` aurait mesuré :
                // une caractéristique du backoff, lue comme une
                // caractéristique du téléphone.
                SyncWorker.forcer(applicationContext)
            } else {
                SyncWorker.planifier(applicationContext)
            }
        }
        Result.success()
    }

    companion object {
        private const val TAG = "CallTracker"

        /** Nom unique du balayage, distinct de celui de l'envoi. */
        private const val TRAVAIL = "call_tracker_scan"
        private const val TRAVAIL_PERIODIQUE = "call_tracker_scan_periodique"

        /** Voir [doWork] : réservé au passage périodique. */
        private const val REINITIALISER_ATTENTE = "reinitialiser_attente"

        /**
         * Balaye une fois, après un délai.
         *
         * `REPLACE` et non `KEEP`, à l'inverse de l'envoi : plusieurs
         * diffusions de `PHONE_STATE` pour un même appel doivent bel et bien
         * repousser l'échéance, puisque le système n'écrit la ligne du journal
         * qu'au raccrochage. Repartir du dernier changement d'état, c'est lire
         * au bon moment ; et un `REPLACE` ne peut jamais être jeté.
         *
         * **Aucune contrainte** : lire un `ContentProvider` local et écrire
         * dans SQLite ne demandent ni réseau, ni batterie, ni rien.
         */
        fun planifier(context: Context, delaiSecondes: Long = 0) {
            val requete = OneTimeWorkRequestBuilder<BalayageWorker>()
                .setInitialDelay(delaiSecondes, TimeUnit.SECONDS)
                .build()
            WorkManager.getInstance(context)
                .enqueueUniqueWork(TRAVAIL, ExistingWorkPolicy.REPLACE, requete)
        }

        /**
         * Filet de fond : balaye régulièrement, quoi qu'il arrive par ailleurs.
         *
         * C'est la seule protection contre les surcouches constructeur qui
         * gèlent l'application, et contre toute diffusion `PHONE_STATE` qui ne
         * serait pas délivrée. Quinze minutes est le plancher de WorkManager
         * pour un travail périodique.
         *
         * `KEEP` : replanifier à chaque ouverture de l'application remettrait
         * le compteur à zéro et repousserait indéfiniment le passage suivant.
         */
        fun planifierPeriodique(context: Context) {
            val requete = PeriodicWorkRequestBuilder<BalayageWorker>(15, TimeUnit.MINUTES)
                .setInputData(
                    Data.Builder().putBoolean(REINITIALISER_ATTENTE, true).build()
                )
                .build()
            WorkManager.getInstance(context).enqueueUniquePeriodicWork(
                TRAVAIL_PERIODIQUE, ExistingPeriodicWorkPolicy.KEEP, requete,
            )
        }
    }
}
