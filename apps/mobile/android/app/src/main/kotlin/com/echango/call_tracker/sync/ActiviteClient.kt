package com.echango.call_tracker.sync

import android.content.Context
import android.util.Log
import com.echango.call_tracker.data.SecureSettings
import org.json.JSONArray
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL

/** Un appel programmé dans le CRM, tel que l'application l'affiche. */
data class ActiviteAppel(
    val id: Long,
    val client: String,
    val phone: String,
    val deadline: String,
    /** `overdue`, `today` ou `planned` — calculé par Odoo, jamais ici. */
    val state: String,
    val summary: String,
    val note: String,
)

/**
 * Les appels à passer, et leur clôture.
 *
 * **Avec cache local, contrairement à la recherche.** Toute l'application est
 * bâtie sur « ça marche sans réseau » : la capture met en file et réessaie.
 * Une liste de tâches est l'inverse — elle ne peut que lire. Sans copie
 * locale, un commercial dans un sous-sol verrait une liste vide et conclurait
 * que l'outil ment ; il retournerait à son papier, et n'en reviendrait pas.
 *
 * Le cache n'a donc pas de durée de validité : il n'expire jamais. Une liste
 * d'hier vaut infiniment mieux qu'un écran vide, **à condition de dire qu'elle
 * date d'hier** — d'où l'horodatage, qui est affiché.
 */
object ActiviteClient {

    private const val TAG = "CallTracker"
    private const val CHEMIN = "/call_tracker/activities"
    private const val FICHIER = "call_tracker_activites"
    private const val CLE_LISTE = "liste"
    private const val CLE_DATE = "recuperee_le"

    /** Rafraîchit depuis le serveur. Rend `false` si le réseau n'a pas répondu. */
    fun rafraichir(context: Context): Boolean {
        val reglages = SecureSettings(context)
        if (!reglages.configured) return false

        var connexion: HttpURLConnection? = null
        return try {
            val cible = URL(reglages.serverUrl.trimEnd('/') + CHEMIN)
            connexion = (cible.openConnection() as HttpURLConnection).apply {
                requestMethod = "GET"
                connectTimeout = 8_000
                readTimeout = 8_000
                setRequestProperty("Authorization", "Bearer ${reglages.token}")
            }
            if (connexion.responseCode != 200) return false
            val corps = connexion.inputStream.bufferedReader().readText()
            // Ne remplace le cache qu'une fois la réponse LUE et valide : une
            // coupure au milieu du transfert ne doit pas vider la liste de
            // quelqu'un qui est en train de travailler.
            val liste = JSONObject(corps).optJSONArray("results") ?: JSONArray()
            context.getSharedPreferences(FICHIER, Context.MODE_PRIVATE).edit()
                .putString(CLE_LISTE, liste.toString())
                .putLong(CLE_DATE, System.currentTimeMillis())
                .apply()
            true
        } catch (erreur: Exception) {
            Log.w(TAG, "Appels a passer : serveur injoignable", erreur)
            false
        } finally {
            connexion?.disconnect()
        }
    }

    fun lireCache(context: Context): List<ActiviteAppel> {
        val brut = context.getSharedPreferences(FICHIER, Context.MODE_PRIVATE)
            .getString(CLE_LISTE, null) ?: return emptyList()
        return try {
            val tableau = JSONArray(brut)
            buildList {
                for (i in 0 until tableau.length()) {
                    val o = tableau.getJSONObject(i)
                    add(
                        ActiviteAppel(
                            id = o.optLong("id"),
                            client = o.optString("client"),
                            phone = o.optString("phone"),
                            deadline = o.optString("deadline"),
                            state = o.optString("state"),
                            summary = o.optString("summary"),
                            note = o.optString("note"),
                        )
                    )
                }
            }
        } catch (erreur: Exception) {
            Log.w(TAG, "Cache des activites illisible", erreur)
            emptyList()
        }
    }

    /** Millisecondes de la dernière récupération réussie, ou 0. */
    fun dateDuCache(context: Context): Long =
        context.getSharedPreferences(FICHIER, Context.MODE_PRIVATE)
            .getLong(CLE_DATE, 0L)

    /**
     * Clôture une activité côté serveur.
     *
     * **Pas de clôture optimiste hors ligne.** Retirer la ligne de l'écran
     * sans que le serveur l'ait enregistrée ferait disparaître une tâche que
     * personne n'a faite — et le commercial, lui, croirait l'avoir cochée.
     * Mieux vaut un bouton qui refuse de marcher qu'une tâche perdue.
     */
    fun cloturer(context: Context, id: Long): Boolean {
        val reglages = SecureSettings(context)
        if (!reglages.configured) return false

        var connexion: HttpURLConnection? = null
        return try {
            val cible = URL(reglages.serverUrl.trimEnd('/') + "/call_tracker/activity/$id/done")
            connexion = (cible.openConnection() as HttpURLConnection).apply {
                requestMethod = "POST"
                connectTimeout = 8_000
                readTimeout = 8_000
                doOutput = true
                setRequestProperty("Content-Type", "application/json; charset=utf-8")
                setRequestProperty("Authorization", "Bearer ${reglages.token}")
            }
            connexion.outputStream.use { it.write("{}".toByteArray()) }
            val ok = connexion.responseCode == 200
            if (ok) rafraichir(context)
            ok
        } catch (erreur: Exception) {
            Log.w(TAG, "Cloture d'activite impossible", erreur)
            false
        } finally {
            connexion?.disconnect()
        }
    }
}
