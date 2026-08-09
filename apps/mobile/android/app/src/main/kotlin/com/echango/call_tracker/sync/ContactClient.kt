package com.echango.call_tracker.sync

import android.util.Log
import com.echango.call_tracker.data.SecureSettings
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import java.net.URLEncoder

/** Fiche minimale renvoyée par Odoo pour l'affichage à la sonnerie. */
data class FicheContact(
    val name: String,
    val company: String,
    val lastNotes: String,
    val crmStage: String,
)

/**
 * Interroge la route de lecture du Call Tracker.
 *
 * Séparé de [SyncWorker] : celui-ci écrit et peut se permettre d'attendre,
 * alors qu'ici on est sur le chemin d'une sonnerie. Les délais d'attente sont
 * donc courts — une fiche qui arrive après que l'utilisateur a décroché
 * n'apporte plus rien.
 */
object ContactClient {

    private const val TAG = "CallTracker"
    private const val CHEMIN = "/call_tracker/contact/"

    fun chercher(reglages: SecureSettings, numero: String): FicheContact? {
        if (!reglages.configured) return null

        var connexion: HttpURLConnection? = null
        return try {
            val cible = URL(
                reglages.serverUrl.trimEnd('/') + CHEMIN +
                    URLEncoder.encode(numero, "UTF-8")
            )
            connexion = (cible.openConnection() as HttpURLConnection).apply {
                requestMethod = "GET"
                connectTimeout = 4_000
                readTimeout = 4_000
                setRequestProperty("Authorization", "Bearer ${reglages.token}")
            }
            when (connexion.responseCode) {
                200 -> lire(connexion.inputStream.bufferedReader().readText())
                // 404 est une réponse normale, pas une panne : ce numéro n'est
                // simplement pas au CRM.
                404 -> null
                else -> {
                    Log.w(TAG, "Fiche contact : reponse ${connexion.responseCode}")
                    null
                }
            }
        } catch (erreur: Exception) {
            Log.w(TAG, "Fiche contact injoignable", erreur)
            null
        } finally {
            connexion?.disconnect()
        }
    }

    fun lire(corps: String): FicheContact? = try {
        val json = JSONObject(corps)
        FicheContact(
            name = json.optString("name"),
            company = json.optString("company"),
            lastNotes = json.optString("last_notes"),
            crmStage = json.optString("crm_stage"),
        )
    } catch (_: Exception) {
        null
    }

    fun serialiser(fiche: FicheContact): String = JSONObject()
        .put("name", fiche.name)
        .put("company", fiche.company)
        .put("last_notes", fiche.lastNotes)
        .put("crm_stage", fiche.crmStage)
        .toString()
}
