package com.echango.call_tracker.data

import android.content.Context
import android.content.SharedPreferences
import android.util.Log
import androidx.security.crypto.EncryptedSharedPreferences
import androidx.security.crypto.MasterKeys

/**
 * Réglages de l'appareil, dont le jeton d'authentification vers Odoo.
 *
 * Rangés côté natif et non côté Flutter : le worker d'envoi tourne alors que
 * le moteur Flutter n'existe pas. Une configuration accessible seulement
 * depuis Dart serait illisible au moment précis où elle sert.
 */
class SecureSettings(context: Context) {

    private val prefs: SharedPreferences = ouvrir(context)

    var serverUrl: String
        get() = prefs.getString(CLE_URL, "").orEmpty()
        set(value) = prefs.edit().putString(CLE_URL, value).apply()

    var token: String
        get() = prefs.getString(CLE_JETON, "").orEmpty()
        set(value) = prefs.edit().putString(CLE_JETON, value).apply()

    var captureEnabled: Boolean
        get() = prefs.getBoolean(CLE_ACTIF, false)
        set(value) = prefs.edit().putBoolean(CLE_ACTIF, value).apply()

    var fromHour: Int
        get() = prefs.getInt(CLE_DE, 8)
        set(value) = prefs.edit().putInt(CLE_DE, value).apply()

    var toHour: Int
        get() = prefs.getInt(CLE_A, 19)
        set(value) = prefs.edit().putInt(CLE_A, value).apply()

    /**
     * Horodatage du dernier balayage du journal d'appels.
     *
     * Sert de curseur : sans lui, chaque balayage relirait tout l'historique du
     * téléphone. La contrainte d'unicité de la file empêcherait les doublons,
     * mais on parcourrait des milliers de lignes à chaque appel.
     */
    var lastScanMillis: Long
        get() = prefs.getLong(CLE_DERNIER_SCAN, 0L)
        set(value) = prefs.edit().putLong(CLE_DERNIER_SCAN, value).apply()

    /**
     * Durée de conservation des appels côté Odoo, telle que le serveur
     * l'annonce à chaque envoi accepté.
     *
     * Lue et non codée en dur : elle est fixée par le `.env` du serveur, et
     * une valeur recopiée dans l'application finirait par mentir à l'écran
     * d'information le jour où l'exploitant la change.
     *
     * `0` signifie « pas encore connue » — aucun appel n'a encore été accepté.
     * L'écran d'information dit alors que la durée est fixée par l'employeur,
     * sans avancer de chiffre. Zéro côté serveur veut dire « aucune purge »,
     * ce qui se dit aussi, et différemment.
     */
    var retentionDays: Int
        get() = prefs.getInt(CLE_RETENTION, 0)
        set(value) = prefs.edit().putInt(CLE_RETENTION, value).apply()

    /** Le serveur a-t-il déjà annoncé sa politique de conservation ? */
    var retentionKnown: Boolean
        get() = prefs.getBoolean(CLE_RETENTION_CONNUE, false)
        set(value) = prefs.edit().putBoolean(CLE_RETENTION_CONNUE, value).apply()

    val configured: Boolean
        get() = serverUrl.isNotBlank() && token.isNotBlank()

    /**
     * L'appel est-il dans la plage horaire de capture ?
     *
     * `de == a` signifie « toute la journée ». Une plage qui enjambe minuit
     * (22 → 6) est acceptée : un commercial de garde n'a pas à voir sa plage
     * refusée parce qu'elle traverse minuit.
     */
    fun dansLaPlage(heureLocale: Int): Boolean {
        val de = fromHour
        val a = toHour
        return when {
            de == a -> true
            de < a -> heureLocale in de until a
            else -> heureLocale >= de || heureLocale < a
        }
    }

    private companion object {
        const val FICHIER = "call_tracker_settings"
        const val CLE_URL = "server_url"
        const val CLE_JETON = "token"
        const val CLE_ACTIF = "capture_enabled"
        const val CLE_DE = "from_hour"
        const val CLE_A = "to_hour"
        const val CLE_DERNIER_SCAN = "last_scan_millis"
        const val CLE_RETENTION = "retention_days"
        const val CLE_RETENTION_CONNUE = "retention_known"

        /**
         * Repli assumé sur des SharedPreferences ordinaires.
         *
         * Le Keystore matériel est défaillant sur une partie du parc Android —
         * ROMs constructeur, appareils reconditionnés — et
         * `EncryptedSharedPreferences` y lève au moment de l'ouverture. Laisser
         * remonter l'exception rendrait l'application inutilisable sur ces
         * téléphones : ni réglages, ni capture, sur un défaut qui ne concerne
         * qu'une couche de protection supplémentaire. Le répertoire de
         * l'application reste inaccessible aux autres applications dans les
         * deux cas ; le chiffrement protège en plus contre une extraction hors
         * ligne, et c'est cela seul que le repli abandonne.
         */
        @Suppress("DEPRECATION")
        fun ouvrir(context: Context): SharedPreferences = try {
            // API de security-crypto 1.0.0, la dernière version STABLE.
            // `MasterKey.Builder` et la surcharge `create(context, …)` qui
            // l'accompagne n'existent qu'à partir de la 1.1.0, encore en
            // alpha — pas ce qu'on veut sous un secret d'authentification en
            // production. D'où `MasterKeys`, marqué déprécié dans les versions
            // futures mais parfaitement fonctionnel ici.
            val alias = MasterKeys.getOrCreate(MasterKeys.AES256_GCM_SPEC)
            EncryptedSharedPreferences.create(
                FICHIER,
                alias,
                context,
                EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV,
                EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM,
            )
        } catch (erreur: Exception) {
            Log.w(
                "CallTracker",
                "Keystore indisponible, repli sur des preferences non chiffrees",
                erreur,
            )
            context.getSharedPreferences("${FICHIER}_clair", Context.MODE_PRIVATE)
        }
    }
}
