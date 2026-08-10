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
    /**
     * Vide pour la fiche de sonnerie — on connaît déjà le numéro, c'est lui
     * qui a servi à la trouver. Renseigné dans les résultats de recherche,
     * où il est indispensable : sans lui on ne sait ni lequel choisir, ni
     * quoi composer en tapant dessus.
     */
    val phone: String = "",
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
    private const val CHEMIN_RECHERCHE = "/call_tracker/contacts/"

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

    /**
     * Contacts dont le numéro contient ce fragment.
     *
     * Distinct de [chercher], qui part d'un numéro complet et rend UNE fiche
     * pour la sonnerie. Ici on part d'un bout de numéro et on rend une liste,
     * pour la recherche manuelle.
     *
     * **Sans cache, volontairement.** [ContactCache] est indexé par numéro
     * complet ; un fragment n'en est pas un, et mettre en cache des listes de
     * résultats ferait afficher un carnet périmé — un contact créé il y a
     * cinq minutes resterait introuvable. Le cache sert la sonnerie, où la
     * même fiche revient souvent ; une recherche manuelle est rare et
     * délibérée, elle peut payer son aller-retour.
     */
    fun rechercher(reglages: SecureSettings, fragment: String): List<FicheContact> {
        if (!reglages.configured) return emptyList()

        var connexion: HttpURLConnection? = null
        return try {
            val cible = URL(
                reglages.serverUrl.trimEnd('/') + CHEMIN_RECHERCHE +
                    URLEncoder.encode(fragment, "UTF-8")
            )
            connexion = (cible.openConnection() as HttpURLConnection).apply {
                requestMethod = "GET"
                connectTimeout = 6_000
                readTimeout = 6_000
                setRequestProperty("Authorization", "Bearer ${reglages.token}")
            }
            when (connexion.responseCode) {
                200 -> lireListe(connexion.inputStream.bufferedReader().readText())
                // 400 = fragment trop court, 404/autres = rien à montrer. Dans
                // tous les cas une liste vide : c'est l'écran qui décide du
                // message, à partir de ce que l'utilisateur a tapé.
                else -> emptyList()
            }
        } catch (erreur: Exception) {
            Log.w(TAG, "Recherche de contacts injoignable", erreur)
            emptyList()
        } finally {
            connexion?.disconnect()
        }
    }

    private fun lireListe(corps: String): List<FicheContact> = try {
        val tableau = JSONObject(corps).optJSONArray("results")
        buildList {
            for (i in 0 until (tableau?.length() ?: 0)) {
                val o = tableau!!.getJSONObject(i)
                add(
                    FicheContact(
                        name = o.optString("name"),
                        company = o.optString("company"),
                        lastNotes = "",
                        crmStage = o.optString("crm_stage"),
                        phone = o.optString("phone"),
                    )
                )
            }
        }
    } catch (erreur: Exception) {
        Log.w(TAG, "Liste de contacts illisible", erreur)
        emptyList()
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
