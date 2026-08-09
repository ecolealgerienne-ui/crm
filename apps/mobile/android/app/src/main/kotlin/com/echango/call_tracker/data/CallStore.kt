package com.echango.call_tracker.data

import android.content.ContentValues
import android.content.Context
import android.database.sqlite.SQLiteDatabase
import android.database.sqlite.SQLiteOpenHelper
import java.util.UUID

data class CallEvent(
    val id: Long,
    val clientEventId: String,
    val phoneNumber: String,
    val direction: String,
    val durationSeconds: Int,
    val startedAtMillis: Long,
    val syncStatus: String,
    val lastError: String?,
    val attempts: Int,
)

/**
 * File locale persistante des appels capturés.
 *
 * SQLiteOpenHelper plutôt que Room : une seule table de neuf colonnes, et
 * l'annotation processor de Room ajouterait une étape de génération au build
 * pour un DAO qui tient en cinquante lignes.
 *
 * Cette file est le cœur de la résilience réseau : un appel capturé y est
 * inscrit AVANT toute tentative d'envoi, et n'en sort qu'une fois Odoo l'ayant
 * accusé. Perdre le réseau, fermer l'application ou redémarrer le téléphone ne
 * perd donc aucun appel.
 */
class CallStore(context: Context) : SQLiteOpenHelper(context, NOM, null, VERSION) {

    override fun onCreate(db: SQLiteDatabase) {
        db.execSQL(
            """
            CREATE TABLE $TABLE (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_event_id TEXT NOT NULL UNIQUE,
                phone_number TEXT NOT NULL,
                direction TEXT NOT NULL,
                duration_seconds INTEGER NOT NULL DEFAULT 0,
                started_at_millis INTEGER NOT NULL,
                sync_status TEXT NOT NULL DEFAULT '$EN_ATTENTE',
                last_error TEXT,
                attempts INTEGER NOT NULL DEFAULT 0
            )
            """.trimIndent()
        )
        // Clé naturelle d'un appel : ce numéro, à cet instant précis.
        //
        // ⚠️ Indispensable, et pas une ceinture de sécurité théorique :
        // PHONE_STATE est diffusé plusieurs fois pour un même appel, et le
        // worker peut aussi être relancé par WorkManager après un échec
        // réseau. Sans cette contrainte, le même appel serait inséré autant de
        // fois qu'il y a de déclenchements, chacun avec son propre
        // client_event_id — donc autant d'appels distincts aux yeux d'Odoo,
        // que son idempotence à lui ne pourrait pas rattraper.
        db.execSQL(
            "CREATE UNIQUE INDEX ${TABLE}_naturel ON $TABLE (phone_number, started_at_millis)"
        )
        db.execSQL("CREATE INDEX ${TABLE}_statut ON $TABLE (sync_status)")
    }

    override fun onUpgrade(db: SQLiteDatabase, ancienne: Int, nouvelle: Int) {
        // Version 1 : rien à migrer. Une file d'attente n'est pas une archive —
        // si un jour une migration est impossible, la reconstruire ne perd que
        // les appels non encore remis, pas l'historique, qui vit dans Odoo.
    }

    /**
     * Insère un appel s'il n'est pas déjà en file.
     * Retourne `true` si l'appel a bien été ajouté.
     */
    fun inserer(
        phoneNumber: String,
        direction: String,
        durationSeconds: Int,
        startedAtMillis: Long,
    ): Boolean {
        val valeurs = ContentValues().apply {
            put("client_event_id", UUID.randomUUID().toString())
            put("phone_number", phoneNumber)
            put("direction", direction)
            put("duration_seconds", durationSeconds)
            put("started_at_millis", startedAtMillis)
            put("sync_status", EN_ATTENTE)
        }
        // CONFLICT_IGNORE : une insertion en double n'est pas une anomalie,
        // c'est le fonctionnement attendu d'un receveur diffusé plusieurs fois.
        val ligne = writableDatabase.insertWithOnConflict(
            TABLE, null, valeurs, SQLiteDatabase.CONFLICT_IGNORE
        )
        return ligne != -1L
    }

    fun aEnvoyer(limite: Int = 50): List<CallEvent> =
        lire("sync_status = ?", arrayOf(EN_ATTENTE), "started_at_millis ASC", limite)

    fun derniers(limite: Int = 200): List<CallEvent> =
        lire(null, null, "started_at_millis DESC", limite)

    fun nombreEnAttente(): Int {
        readableDatabase.rawQuery(
            "SELECT COUNT(*) FROM $TABLE WHERE sync_status = ?", arrayOf(EN_ATTENTE)
        ).use { curseur ->
            return if (curseur.moveToFirst()) curseur.getInt(0) else 0
        }
    }

    fun marquerEnvoye(id: Long) {
        writableDatabase.execSQL(
            "UPDATE $TABLE SET sync_status = ?, last_error = NULL WHERE id = ?",
            arrayOf(ENVOYE, id),
        )
    }

    /** Échec définitif : la charge utile est refusée, réessayer ne changera rien. */
    fun marquerEchecDefinitif(id: Long, raison: String) {
        writableDatabase.execSQL(
            "UPDATE $TABLE SET sync_status = ?, last_error = ?, attempts = attempts + 1 WHERE id = ?",
            arrayOf(ECHEC, raison.take(300), id),
        )
    }

    /**
     * Échec temporaire : l'appel RESTE en attente.
     *
     * Réseau coupé, serveur indisponible, jeton pas encore saisi — autant de
     * situations qui se résolvent d'elles-mêmes ou d'un réglage. Les basculer
     * en échec définitif obligerait à une reprise manuelle pour un incident
     * passager, et le motif est conservé pour que l'utilisateur sache pourquoi
     * sa file ne se vide pas.
     */
    fun noterEchecTemporaire(id: Long, raison: String) {
        writableDatabase.execSQL(
            "UPDATE $TABLE SET last_error = ?, attempts = attempts + 1 WHERE id = ?",
            arrayOf(raison.take(300), id),
        )
    }

    private fun lire(
        selection: String?,
        arguments: Array<String>?,
        ordre: String,
        limite: Int,
    ): List<CallEvent> {
        val resultats = mutableListOf<CallEvent>()
        readableDatabase.query(
            TABLE, null, selection, arguments, null, null, ordre, limite.toString()
        ).use { c ->
            val iId = c.getColumnIndexOrThrow("id")
            val iEvt = c.getColumnIndexOrThrow("client_event_id")
            val iNum = c.getColumnIndexOrThrow("phone_number")
            val iDir = c.getColumnIndexOrThrow("direction")
            val iDur = c.getColumnIndexOrThrow("duration_seconds")
            val iDate = c.getColumnIndexOrThrow("started_at_millis")
            val iStatut = c.getColumnIndexOrThrow("sync_status")
            val iErr = c.getColumnIndexOrThrow("last_error")
            val iTent = c.getColumnIndexOrThrow("attempts")
            while (c.moveToNext()) {
                resultats += CallEvent(
                    id = c.getLong(iId),
                    clientEventId = c.getString(iEvt),
                    phoneNumber = c.getString(iNum),
                    direction = c.getString(iDir),
                    durationSeconds = c.getInt(iDur),
                    startedAtMillis = c.getLong(iDate),
                    syncStatus = c.getString(iStatut),
                    lastError = if (c.isNull(iErr)) null else c.getString(iErr),
                    attempts = c.getInt(iTent),
                )
            }
        }
        return resultats
    }

    companion object {
        private const val NOM = "call_tracker.db"
        private const val VERSION = 1
        private const val TABLE = "call_event"

        const val EN_ATTENTE = "pending"
        const val ENVOYE = "sent"
        const val ECHEC = "failed"

        const val ENTRANT = "inbound"
        const val SORTANT = "outbound"
        const val MANQUE = "missed"
    }
}
