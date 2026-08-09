package com.echango.call_tracker.capture

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.provider.CallLog
import android.util.Log
import androidx.core.content.ContextCompat
import com.echango.call_tracker.data.CallStore
import com.echango.call_tracker.data.SecureSettings
import com.echango.call_tracker.sync.SyncWorker
import java.util.Calendar

/**
 * Lit le journal d'appels du système et verse les nouveaux appels dans la file.
 *
 * **Pourquoi lire `CallLog` plutôt que chronométrer l'appel soi-même.**
 * `PHONE_STATE` annonce les changements d'état, mais ne donne ni la durée, ni
 * le numéro d'un appel entrant sur les versions récentes d'Android. Le journal
 * système, lui, porte les deux, déjà consolidés. Le receveur ne sert donc qu'à
 * savoir *quand* aller lire.
 */
object CallLogScanner {

    private const val TAG = "CallTracker"

    /** Nombre d'appels versés dans la file. */
    fun balayer(context: Context): Int {
        val reglages = SecureSettings(context)
        if (!reglages.captureEnabled) return 0

        if (ContextCompat.checkSelfPermission(context, Manifest.permission.READ_CALL_LOG)
            != PackageManager.PERMISSION_GRANTED
        ) {
            Log.w(TAG, "READ_CALL_LOG absente : balayage impossible")
            return 0
        }

        val store = CallStore(context)
        val depuis = reglages.lastScanMillis
        var plusRecent = depuis
        var verses = 0

        val projection = arrayOf(
            CallLog.Calls.NUMBER,
            CallLog.Calls.TYPE,
            CallLog.Calls.DATE,
            CallLog.Calls.DURATION,
        )

        context.contentResolver.query(
            CallLog.Calls.CONTENT_URI,
            projection,
            "${CallLog.Calls.DATE} > ?",
            arrayOf(depuis.toString()),
            "${CallLog.Calls.DATE} ASC",
        )?.use { c ->
            val iNum = c.getColumnIndexOrThrow(CallLog.Calls.NUMBER)
            val iType = c.getColumnIndexOrThrow(CallLog.Calls.TYPE)
            val iDate = c.getColumnIndexOrThrow(CallLog.Calls.DATE)
            val iDur = c.getColumnIndexOrThrow(CallLog.Calls.DURATION)

            while (c.moveToNext()) {
                val date = c.getLong(iDate)
                if (date > plusRecent) plusRecent = date

                val numero = c.getString(iNum).orEmpty().trim()
                if (numero.isEmpty()) continue

                val direction = when (c.getInt(iType)) {
                    CallLog.Calls.INCOMING_TYPE -> CallStore.ENTRANT
                    CallLog.Calls.OUTGOING_TYPE -> CallStore.SORTANT
                    // Manqué, rejeté et bloqué sont tous « pas de conversation ».
                    // Les distinguer dans Odoo n'apporterait rien au suivi
                    // commercial, qui ne retient qu'une chose : personne n'a
                    // décroché.
                    CallLog.Calls.MISSED_TYPE,
                    CallLog.Calls.REJECTED_TYPE,
                    CallLog.Calls.BLOCKED_TYPE -> CallStore.MANQUE
                    // Messagerie vocale, transfert, refus externe : hors sujet.
                    else -> continue
                }

                if (!reglages.dansLaPlage(heureLocaleDe(date))) continue

                val id = store.inserer(
                    numero, direction, c.getInt(iDur), date,
                    attenteNoteMillis = InviteNote.DELAI_NOTE_MILLIS,
                )
                if (id == -1L) continue
                verses++
                InviteNote.proposer(context, id, numero)
            }
        }

        // Curseur avancé même si rien n'a été versé : les appels hors plage
        // horaire ou de type ignoré ont bien été examinés, et les réexaminer à
        // chaque balayage ferait grossir le travail indéfiniment.
        if (plusRecent > depuis) reglages.lastScanMillis = plusRecent

        if (verses > 0) {
            Log.i(TAG, "$verses appel(s) verses dans la file")
            // Les appels versés attendent une note : ils ne partiront pas au
            // passage courant du worker. Sans ce rendez-vous, ils resteraient
            // en file jusqu'au prochain appel — un commercial qui n'appelle
            // plus de la journée ne verrait rien remonter.
            SyncWorker.planifier(
                context,
                delaiSecondes = InviteNote.DELAI_NOTE_MILLIS / 1000 + 5,
            )
        }
        return verses
    }

    private fun heureLocaleDe(millis: Long): Int =
        Calendar.getInstance().apply { timeInMillis = millis }.get(Calendar.HOUR_OF_DAY)
}
