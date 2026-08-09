package com.echango.call_tracker.sync

import android.content.Context
import android.util.Log
import androidx.work.Constraints
import androidx.work.CoroutineWorker
import androidx.work.ExistingWorkPolicy
import androidx.work.NetworkType
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.WorkerParameters
import com.echango.call_tracker.capture.CallLogScanner
import com.echango.call_tracker.data.CallStore
import com.echango.call_tracker.data.SecureSettings
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import java.util.TimeZone
import java.util.concurrent.TimeUnit

/**
 * Balaie le journal d'appels, puis remet à Odoo tout ce qui est en attente.
 *
 * Un seul worker pour les deux étapes : elles ont exactement le même
 * déclencheur (un appel vient de finir, ou l'utilisateur demande une
 * synchronisation), et les séparer imposerait de garantir leur ordre à travers
 * deux planifications indépendantes.
 *
 * `CoroutineWorker` et non `Worker` : l'envoi est bloquant sur le réseau, et
 * WorkManager donne dix minutes avant de tuer la tâche.
 */
class SyncWorker(
    context: Context,
    parametres: WorkerParameters,
) : CoroutineWorker(context, parametres) {

    override suspend fun doWork(): Result = withContext(Dispatchers.IO) {
        CallLogScanner.balayer(applicationContext)

        val reglages = SecureSettings(applicationContext)
        val store = CallStore(applicationContext)
        val aEnvoyer = store.aEnvoyer()
        if (aEnvoyer.isEmpty()) return@withContext Result.success()

        if (!reglages.configured) {
            // Rien à réessayer tant que l'utilisateur n'a pas renseigné
            // l'adresse et le jeton. Un `retry()` ici ferait tourner WorkManager
            // en boucle sur un problème que seul un humain peut résoudre.
            aEnvoyer.forEach {
                store.noterEchecTemporaire(it.id, "Adresse ou jeton non configure")
            }
            return@withContext Result.success()
        }

        val cible = URL(reglages.serverUrl.trimEnd('/') + CHEMIN)
        var aReessayer = false

        for (appel in aEnvoyer) {
            when (val issue = envoyer(cible, reglages.token, appel.toJson())) {
                is Issue.Accepte -> {
                    store.marquerEnvoye(appel.id)
                    // L'invite de note d'un appel déjà remis n'a plus d'objet.
                    com.echango.call_tracker.capture.InviteNote
                        .retirer(applicationContext, appel.id)
                }
                is Issue.RefusDefinitif -> store.marquerEchecDefinitif(appel.id, issue.raison)
                is Issue.Temporaire -> {
                    store.noterEchecTemporaire(appel.id, issue.raison)
                    aReessayer = true
                    // Inutile d'épuiser la file : si le serveur est
                    // injoignable ou le jeton refusé, l'appel suivant échouera
                    // pour la même raison. On rend la main à WorkManager, qui
                    // sait attendre.
                    break
                }
            }
        }

        if (aReessayer) Result.retry() else Result.success()
    }

    private fun envoyer(cible: URL, jeton: String, corps: JSONObject): Issue {
        var connexion: HttpURLConnection? = null
        return try {
            connexion = (cible.openConnection() as HttpURLConnection).apply {
                requestMethod = "POST"
                connectTimeout = 15_000
                readTimeout = 20_000
                doOutput = true
                setRequestProperty("Content-Type", "application/json; charset=utf-8")
                setRequestProperty("Authorization", "Bearer $jeton")
            }
            connexion.outputStream.use { it.write(corps.toString().toByteArray(Charsets.UTF_8)) }

            when (val code = connexion.responseCode) {
                // 200 couvre le rejeu d'un appel déjà reçu : l'addon Odoo
                // répond « duplicate » avec un succès, précisément pour que la
                // file locale puisse se vider au lieu de réessayer sans fin.
                200, 201 -> Issue.Accepte
                400 -> Issue.RefusDefinitif(lireErreur(connexion) ?: "Charge utile refusee (400)")
                401 -> Issue.Temporaire("Jeton refuse (401)")
                else -> Issue.Temporaire("Reponse serveur $code")
            }
        } catch (erreur: Exception) {
            Log.w(TAG, "Envoi impossible", erreur)
            Issue.Temporaire(erreur.message ?: erreur.javaClass.simpleName)
        } finally {
            connexion?.disconnect()
        }
    }

    private fun lireErreur(connexion: HttpURLConnection): String? = try {
        connexion.errorStream?.bufferedReader()?.use {
            JSONObject(it.readText()).optString("detail").ifBlank { null }
        }
    } catch (_: Exception) {
        null
    }

    private sealed interface Issue {
        data object Accepte : Issue
        data class RefusDefinitif(val raison: String) : Issue
        data class Temporaire(val raison: String) : Issue
    }

    companion object {
        private const val TAG = "CallTracker"
        private const val CHEMIN = "/call_tracker/log_call"
        private const val TRAVAIL = "call_tracker_sync"

        /**
         * Planifie un balayage puis un envoi.
         *
         * `delai` de quelques secondes après un appel : le système écrit dans
         * `CallLog` de façon asynchrone, et lire à l'instant où le téléphone
         * repasse au repos ne trouve rien. C'est le défaut le plus courant de
         * ce type de capture, et il est silencieux — l'appel n'est pas
         * journalisé, sans la moindre erreur.
         *
         * `KEEP` et non `REPLACE` : plusieurs diffusions de PHONE_STATE pour un
         * même appel ne doivent pas repousser indéfiniment l'échéance.
         */
        fun planifier(context: Context, delaiSecondes: Long = 0) {
            val requete = OneTimeWorkRequestBuilder<SyncWorker>()
                .setConstraints(
                    Constraints.Builder()
                        .setRequiredNetworkType(NetworkType.CONNECTED)
                        .build()
                )
                .setInitialDelay(delaiSecondes, TimeUnit.SECONDS)
                .setBackoffCriteria(
                    androidx.work.BackoffPolicy.EXPONENTIAL,
                    30, TimeUnit.SECONDS,
                )
                .build()

            WorkManager.getInstance(context)
                .enqueueUniqueWork(TRAVAIL, ExistingWorkPolicy.KEEP, requete)
        }

        /** Demande explicite de l'utilisateur : elle passe devant une attente en cours. */
        fun forcer(context: Context) {
            val requete = OneTimeWorkRequestBuilder<SyncWorker>()
                .setConstraints(
                    Constraints.Builder()
                        .setRequiredNetworkType(NetworkType.CONNECTED)
                        .build()
                )
                .build()
            WorkManager.getInstance(context)
                .enqueueUniqueWork(TRAVAIL, ExistingWorkPolicy.REPLACE, requete)
        }
    }
}

/**
 * Sérialise un appel selon le contrat de l'addon Odoo.
 *
 * ⚠️ La liste des champs est **fermée** côté serveur : le contrôleur rejette
 * toute clé qu'il ne connaît pas. Ajouter un champ ici sans le déclarer
 * là-bas fait échouer l'envoi de TOUS les appels avec un 400, pas seulement
 * de ceux qui portent la nouveauté.
 */
private fun com.echango.call_tracker.data.CallEvent.toJson(): JSONObject = JSONObject().apply {
    put("client_event_id", clientEventId)
    put("phone_number", phoneNumber)
    put("direction", direction)
    put("duration_seconds", durationSeconds)
    put("started_at", iso8601Utc(startedAtMillis))
    // Absente quand il n'y a pas de note : le serveur accepte le champ mais ne
    // l'exige pas, et envoyer une chaîne vide ferait écrire une note vide.
    if (!note.isNullOrBlank()) put("note", note)
}

/**
 * ISO 8601 en UTC, suffixe `Z` explicite.
 *
 * Le serveur **refuse** un horodatage sans fuseau, et il a raison de le faire :
 * le téléphone d'un commercial peut être sur n'importe quel fuseau, et
 * l'interpréter comme de l'UTC décalerait les appels de plusieurs heures sans
 * que rien ne le signale.
 */
private fun iso8601Utc(millis: Long): String {
    val format = SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss'Z'", Locale.US)
    format.timeZone = TimeZone.getTimeZone("UTC")
    return format.format(Date(millis))
}
