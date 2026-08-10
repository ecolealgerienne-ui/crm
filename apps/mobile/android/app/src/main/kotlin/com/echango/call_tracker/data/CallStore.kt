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
    val note: String?,
    /** Époque en millisecondes jusqu'à laquelle l'appel attend une note. */
    val awaitingNoteUntil: Long,
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
                attempts INTEGER NOT NULL DEFAULT 0,
                note TEXT,
                awaiting_note_until INTEGER NOT NULL DEFAULT 0
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
        // Migration plutôt que reconstruction : la file peut contenir des
        // appels pas encore remis au moment d'une mise à jour de l'app, et les
        // effacer perdrait précisément ce qu'elle sert à protéger.
        if (ancienne < 2) {
            db.execSQL("ALTER TABLE $TABLE ADD COLUMN note TEXT")
            db.execSQL(
                "ALTER TABLE $TABLE ADD COLUMN awaiting_note_until INTEGER NOT NULL DEFAULT 0"
            )
        }
    }

    /**
     * Insère un appel s'il n'est pas déjà en file.
     * Retourne l'identifiant local créé, ou `-1` si l'appel était déjà connu.
     *
     * `attenteNoteMillis` retient l'appel un court moment avant qu'il ne
     * devienne éligible à l'envoi : le temps que le commercial saisisse sa
     * note. Sans cette retenue, l'appel partirait dans les secondes suivant le
     * raccrochage et la note n'aurait plus de véhicule.
     */
    fun inserer(
        phoneNumber: String,
        direction: String,
        durationSeconds: Int,
        startedAtMillis: Long,
        attenteNoteMillis: Long = 0,
    ): Long {
        val valeurs = ContentValues().apply {
            put("client_event_id", UUID.randomUUID().toString())
            put("phone_number", phoneNumber)
            put("direction", direction)
            put("duration_seconds", durationSeconds)
            put("started_at_millis", startedAtMillis)
            put("sync_status", EN_ATTENTE)
            put(
                "awaiting_note_until",
                if (attenteNoteMillis > 0) System.currentTimeMillis() + attenteNoteMillis else 0,
            )
        }
        // CONFLICT_IGNORE : une insertion en double n'est pas une anomalie,
        // c'est le fonctionnement attendu d'un receveur diffusé plusieurs fois.
        return writableDatabase.insertWithOnConflict(
            TABLE, null, valeurs, SQLiteDatabase.CONFLICT_IGNORE
        )
    }

    /**
     * Appels prêts à partir.
     *
     * Exclut ceux qui attendent encore une note. La retenue est bornée dans le
     * temps : si le commercial ne répond pas à l'invite, l'appel part sans
     * note plutôt que de rester indéfiniment en file. Une fonctionnalité de
     * confort ne doit pas pouvoir retenir la donnée principale.
     */
    fun aEnvoyer(limite: Int = 50): List<CallEvent> = lire(
        "sync_status = ? AND awaiting_note_until <= ?",
        arrayOf(EN_ATTENTE, System.currentTimeMillis().toString()),
        "started_at_millis ASC",
        limite,
    )

    /** Appels dont l'invite de note est encore ouverte. */
    fun enAttenteDeNote(): List<CallEvent> = lire(
        "sync_status = ? AND awaiting_note_until > ?",
        arrayOf(EN_ATTENTE, System.currentTimeMillis().toString()),
        "started_at_millis DESC",
        20,
    )

    fun parId(id: Long): CallEvent? =
        lire("id = ?", arrayOf(id.toString()), "id DESC", 1).firstOrNull()

    /**
     * Attache la note et libère l'appel : il part à la prochaine occasion.
     *
     * ⚠️ Repasse en attente un appel DÉJÀ REMIS, et ce n'est pas un détail de
     * confort. La retenue de deux minutes qui laisse le temps d'écrire est du
     * même ordre de grandeur que le temps qu'on met à écrire : le commercial
     * qui valide sa note quelques secondes trop tard la voyait enregistrée en
     * base locale, affichée dans sa liste, confirmée par un « Note
     * enregistrée » — et jamais remontée, puisque seuls les `pending` sont
     * envoyés. La perte était silencieuse, et la fenêtre tombe pile au moment
     * où le commercial agit.
     *
     * Le serveur accepte désormais la note en complément d'un appel déjà reçu,
     * sans rien écraser. Le renvoi est donc sûr : il répond « duplicate » et
     * ne fait qu'ajouter ce qui manquait.
     */
    fun enregistrerNote(id: Long, note: String?) {
        // Cadré sur `sent` : un appel en échec DÉFINITIF (horodatage aberrant,
        // charge refusée) ne doit pas être ressuscité par une note — il
        // repartirait pour être refusé à l'identique, en boucle.
        writableDatabase.execSQL(
            "UPDATE $TABLE SET note = ?, awaiting_note_until = 0, " +
                "sync_status = CASE " +
                "WHEN sync_status = ? AND ? IS NOT NULL AND ? <> '' THEN ? " +
                "ELSE sync_status END " +
                "WHERE id = ?",
            arrayOf(note?.take(1000), ENVOYE, note, note, EN_ATTENTE, id),
        )
    }

    /** Renonce à la note : l'appel part tel quel, sans attendre l'échéance. */
    fun ignorerNote(id: Long) {
        writableDatabase.execSQL(
            "UPDATE $TABLE SET awaiting_note_until = 0 WHERE id = ?", arrayOf(id)
        )
    }

    fun derniers(limite: Int = 200): List<CallEvent> =
        lire(null, null, "started_at_millis DESC", limite)

    /**
     * Efface les appels déjà remis et sortis de la durée de conservation.
     *
     * L'écran d'information annonce « les appels sont effacés automatiquement
     * au bout de N jours ». C'était vrai côté Odoo et faux sur le téléphone :
     * rien n'était jamais supprimé ici. Un commercial à trente appels par jour
     * accumulait onze mille lignes par an — numéros et notes comprises — dans
     * un SQLite non chiffré, sur un appareil qui se perd. La durée venait
     * pourtant du serveur et dormait déjà dans les réglages.
     *
     * ⚠️ Seuls les `sent` sont effacés. Un appel encore en file n'a pas été
     * remis : le purger le ferait disparaître pour de bon, alors que la copie
     * locale est justement tout ce qui en reste.
     *
     * Le plafond dur s'applique même sans rétention connue : la base ne doit
     * pas croître sans fin parce que le serveur n'a jamais répondu.
     */
    fun purger(jours: Int, plafond: Int = PLAFOND_LIGNES) {
        if (jours > 0) {
            val limite = System.currentTimeMillis() - jours * 24L * 60 * 60 * 1000
            writableDatabase.execSQL(
                "DELETE FROM $TABLE WHERE sync_status = ? AND started_at_millis < ?",
                arrayOf(ENVOYE, limite),
            )
        }
        writableDatabase.execSQL(
            """
            DELETE FROM $TABLE WHERE sync_status = ? AND id NOT IN (
                SELECT id FROM $TABLE ORDER BY started_at_millis DESC LIMIT ?
            )
            """.trimIndent(),
            arrayOf(ENVOYE, plafond),
        )
    }

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
            val iNote = c.getColumnIndexOrThrow("note")
            val iAttente = c.getColumnIndexOrThrow("awaiting_note_until")
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
                    note = if (c.isNull(iNote)) null else c.getString(iNote),
                    awaitingNoteUntil = c.getLong(iAttente),
                )
            }
        }
        return resultats
    }

    companion object {
        private const val NOM = "call_tracker.db"
        private const val VERSION = 2
        private const val TABLE = "call_event"

        const val EN_ATTENTE = "pending"
        const val ENVOYE = "sent"
        const val ECHEC = "failed"

        /**
         * Appels déjà remis conservés au maximum, rétention ou non.
         *
         * L'écran Appels n'en affiche que 200 : au-delà, ces lignes ne servent
         * plus qu'à faire grossir un fichier que personne ne consulte.
         */
        const val PLAFOND_LIGNES = 500

        const val ENTRANT = "inbound"
        const val SORTANT = "outbound"
        const val MANQUE = "missed"
    }
}
