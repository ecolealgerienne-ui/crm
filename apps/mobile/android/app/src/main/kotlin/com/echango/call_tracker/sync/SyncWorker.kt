package com.echango.call_tracker.sync

import android.content.Context
import android.os.Build
import android.util.Log
import androidx.work.Constraints
import androidx.work.CoroutineWorker
import androidx.work.ExistingWorkPolicy
import androidx.work.NetworkType
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.WorkerParameters
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
 * Remet à Odoo tout ce qui attend dans la file locale.
 *
 * ⚠️ **Ce worker ne balaie plus le journal d'appels** — c'est le rôle de
 * [BalayageWorker], et la séparation n'est pas un rangement. Le balayage
 * héritait ici de la contrainte réseau : hors réseau, rien n'était capturé, et
 * la file locale — présentée partout comme le rempart — ne se remplissait
 * qu'après le retour du réseau. Le second effet était plus retors : le
 * balayage planifiait l'envoi différé des appels retenus pour une note, sous
 * CE nom unique, depuis l'intérieur de CE worker en cours d'exécution — donc
 * en `KEEP`, donc jeté. Voir [BalayageWorker] pour le détail.
 *
 * `CoroutineWorker` et non `Worker` : l'envoi est bloquant sur le réseau, et
 * WorkManager donne dix minutes avant de tuer la tâche.
 */
class SyncWorker(
    context: Context,
    parametres: WorkerParameters,
) : CoroutineWorker(context, parametres) {

    override suspend fun doWork(): Result = withContext(Dispatchers.IO) {
        try {
            envoyerLaFile()
        } catch (erreur: Exception) {
            // Sans cette enveloppe, une adresse mal formée (préférences
            // restaurées, provisionnement automatisé) faisait échouer le
            // worker AVANT d'avoir rien inscrit : la file ne partait pas, et
            // l'écran n'affichait aucun motif. Le motif est ce qui manquait le
            // plus à ce dispositif — autant ne pas le perdre là où il naît.
            Log.e(TAG, "Envoi interrompu", erreur)
            val message = erreur.message ?: erreur.javaClass.simpleName
            CallStore(applicationContext).use { store ->
                store.aEnvoyer().forEach { store.noterEchecTemporaire(it.id, message) }
            }
            Result.retry()
        }
    }

    private suspend fun envoyerLaFile(): Result {
        val reglages = SecureSettings(applicationContext)
        val store = CallStore(applicationContext)
        val aEnvoyer = store.aEnvoyer(LIMITE)
        if (aEnvoyer.isEmpty()) return Result.success()

        if (!reglages.configured) {
            // Rien à réessayer tant que l'utilisateur n'a pas renseigné
            // l'adresse et le jeton. Un `retry()` ici ferait tourner WorkManager
            // en boucle sur un problème que seul un humain peut résoudre.
            aEnvoyer.forEach {
                store.noterEchecTemporaire(it.id, "Adresse ou jeton non configure")
            }
            return Result.success()
        }

        val cible = URL(reglages.serverUrl.trimEnd('/') + CHEMIN)
        var aReessayer = false

        for (appel in aEnvoyer) {
            when (val issue = envoyer(cible, reglages.token, appel.toJson(), reglages)) {
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

        if (aReessayer) return Result.retry()

        // Le lot est plafonné. Sans ce réenchaînement, 180 appels accumulés
        // pendant une coupure partaient par tranches de 50, une tranche par
        // déclencheur — et le bandeau « 130 en attente » persistait après un
        // appui sur « Synchroniser maintenant », ce qui se lit comme une panne.
        if (aEnvoyer.size == LIMITE && store.nombreEnAttente() > 0) {
            forcer(applicationContext)
        }
        return Result.success()
    }

    private fun envoyer(
        cible: URL,
        jeton: String,
        corps: JSONObject,
        reglages: SecureSettings,
    ): Issue {
        var connexion: HttpURLConnection? = null
        return try {
            connexion = (cible.openConnection() as HttpURLConnection).apply {
                requestMethod = "POST"
                connectTimeout = 15_000
                readTimeout = 20_000
                doOutput = true
                setRequestProperty("Content-Type", "application/json; charset=utf-8")
                setRequestProperty("Authorization", "Bearer $jeton")
                // Ce que l'appareil declare de lui-meme, pour expliquer les
                // delais de remise : les surcouches constructeur n'ont pas
                // toutes le meme appetit pour suspendre les applications, et
                // sans le modele on ne peut pas savoir laquelle decroche.
                //
                // En EN-TETES et non dans la charge utile : celle-ci a une
                // liste blanche stricte cote Odoo, et y ajouter des cles
                // ferait echouer l'envoi de TOUS les appels contre un serveur
                // plus ancien. Un en-tete inconnu, lui, est simplement ignore.
                setRequestProperty("X-Device-Model", "${Build.MANUFACTURER} ${Build.MODEL}")
                setRequestProperty("X-Device-Os", "Android ${Build.VERSION.RELEASE}")
            }
            connexion.outputStream.use { it.write(corps.toString().toByteArray(Charsets.UTF_8)) }

            when (val code = connexion.responseCode) {
                // 200 couvre le rejeu d'un appel déjà reçu : l'addon Odoo
                // répond « duplicate » avec un succès, précisément pour que la
                // file locale puisse se vider au lieu de réessayer sans fin.
                200, 201 -> {
                    releverRetention(connexion, reglages)
                    Issue.Accepte
                }
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

    /**
     * Relève la durée de conservation annoncée par le serveur.
     *
     * C'est elle qu'affiche l'écran d'information de l'application. La coder
     * en dur ici garantirait qu'un jour l'écran annonce trois ans quand le
     * serveur en garde cinq, et un avis de confidentialité faux est pire que
     * pas d'avis du tout.
     *
     * Silencieuse en cas d'échec, et **volontairement** : un serveur d'une
     * version antérieure ne renvoie pas ce champ. Faire échouer l'envoi pour
     * une information d'affichage arrêterait la capture sur un détail.
     */
    private fun releverRetention(connexion: HttpURLConnection, reglages: SecureSettings) {
        try {
            val corps = connexion.inputStream.bufferedReader().use { it.readText() }
            val reponse = JSONObject(corps)
            if (!reponse.has(CHAMP_RETENTION)) return
            reglages.retentionDays = reponse.getInt(CHAMP_RETENTION)
            reglages.retentionKnown = true
        } catch (erreur: Exception) {
            Log.d(TAG, "Duree de conservation non lisible dans la reponse", erreur)
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
        private const val CHAMP_RETENTION = "retention_days"
        private const val TRAVAIL = "call_tracker_sync"

        /** Appels remis par passage. Voir le réenchaînement dans [envoyerLaFile]. */
        private const val LIMITE = 50

        /**
         * Planifie un envoi.
         *
         * `KEEP` et non `REPLACE` : un envoi déjà en attente de réessai sait ce
         * qu'il fait, et le redemander sans cesse remettrait son compteur de
         * tentatives à zéro — on martèlerait un serveur indisponible.
         *
         * ⚠️ Ne jamais appeler ceci depuis l'intérieur de ce worker : sous le
         * même nom unique, `KEEP` voit le travail en cours comme « non
         * terminé » et jette la demande sans rien dire. C'est le défaut qui
         * faisait dormir le dernier appel de la journée jusqu'au lendemain.
         * Le balayage, qui a besoin de poser ce rendez-vous, vit désormais
         * dans un travail portant un autre nom.
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
