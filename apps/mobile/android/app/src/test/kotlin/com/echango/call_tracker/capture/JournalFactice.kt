package com.echango.call_tracker.capture

import android.content.ContentProvider
import android.content.ContentValues
import android.database.Cursor
import android.database.MatrixCursor
import android.net.Uri
import android.provider.CallLog

/**
 * Journal d'appels en mémoire, pour les tests du curseur de balayage.
 *
 * Ne comprend qu'une seule requête — celle que [CallLogScanner] émet, à savoir
 * `DATE > ?` trié par `DATE ASC`. C'est délibéré : un faux provider qui
 * interpréterait du SQL générique serait plus compliqué que le code testé, et
 * n'apporterait aucune garantie de plus.
 */
class JournalFactice : ContentProvider() {

    data class Ligne(
        val numero: String,
        val type: Int,
        val date: Long,
        val duree: Int,
    )

    override fun onCreate(): Boolean = true

    override fun query(
        uri: Uri,
        projection: Array<out String>?,
        selection: String?,
        selectionArgs: Array<out String>?,
        sortOrder: String?,
    ): Cursor {
        val depuis = selectionArgs?.firstOrNull()?.toLongOrNull() ?: 0L
        val curseur = MatrixCursor(
            arrayOf(
                CallLog.Calls.NUMBER,
                CallLog.Calls.TYPE,
                CallLog.Calls.DATE,
                CallLog.Calls.DURATION,
            )
        )
        lignes.filter { it.date > depuis }
            .sortedBy { it.date }
            .forEach { curseur.addRow(arrayOf(it.numero, it.type, it.date, it.duree)) }
        return curseur
    }

    override fun getType(uri: Uri): String? = null
    override fun insert(uri: Uri, values: ContentValues?): Uri? = null
    override fun delete(uri: Uri, selection: String?, args: Array<out String>?): Int = 0
    override fun update(
        uri: Uri,
        values: ContentValues?,
        selection: String?,
        args: Array<out String>?,
    ): Int = 0

    companion object {
        /** Partagé : le provider est instancié par le framework, pas par le test. */
        val lignes = mutableListOf<Ligne>()

        fun vider() = lignes.clear()

        fun ajouter(date: Long, numero: String = "+213555000000", duree: Int = 30) {
            lignes += Ligne(numero, CallLog.Calls.OUTGOING_TYPE, date, duree)
        }
    }
}
