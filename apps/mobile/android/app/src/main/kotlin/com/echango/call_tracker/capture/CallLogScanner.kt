package com.echango.call_tracker.capture

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.os.Build
import android.provider.CallLog
import android.telephony.TelephonyManager
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

        // Filet de sécurité sur l'invariant « on ne remonte jamais avant
        // l'activation ». Le curseur est normalement posé à l'activation de la
        // capture (voir MainActivity), mais un chemin oublié — restauration de
        // sauvegarde, préférences recopiées, provisionnement automatisé —
        // laisserait un zéro. Et un zéro ici ne fait pas rien : il verse dans
        // le CRM tout l'historique d'appels du téléphone, vie privée comprise,
        // sans qu'aucune erreur ne le signale.
        //
        // L'invariant est donc vérifié là où il est CONSOMMÉ, pas seulement là
        // où il est établi. Ce balayage-ci ne remonte rien : il pose le repère.
        //
        // Le second cas — un curseur DANS LE FUTUR — est le symétrique exact,
        // et il est plus vicieux encore. Une horloge fausse au moment de
        // l'activation (batterie à plat, SIM qui ne fournit pas encore l'heure
        // réseau, date avancée à la main) pose le repère en 2036 ; le NTP
        // corrige une minute plus tard, et `DATE > curseur` n'est plus jamais
        // vrai. La capture est morte, définitivement, et TOUT indique le
        // contraire : « Tout est synchronisé », zéro en attente, aucune
        // erreur. Le curseur ne redescendant jamais tout seul, rien ne peut
        // rattraper cela.
        //
        // Le ramener à maintenant plutôt qu'en arrière respecte l'invariant :
        // on ne remonte toujours rien du passé.
        val maintenant = System.currentTimeMillis()
        if (reglages.lastScanMillis == 0L ||
            reglages.lastScanMillis > maintenant + TOLERANCE_HORLOGE_MILLIS
        ) {
            Log.w(TAG, "Curseur repose a maintenant (etait ${reglages.lastScanMillis})")
            reglages.lastScanMillis = maintenant
            return 0
        }

        // Un appel en cours a peut-être déjà sa ligne dans le journal, mais
        // avec une durée nulle : plusieurs surcouches l'écrivent au décrochage
        // et la complètent au raccrochage. La lire maintenant figerait une
        // conversation de quarante minutes à zéro seconde — et l'index unique
        // sur (numéro, début) interdirait ensuite toute correction. Attendre
        // ne coûte rien : le balayage suivant a lieu quinze secondes après la
        // fin de l'appel.
        if (unAppelEstEnCours(context)) {
            Log.i(TAG, "Appel en cours : balayage differe")
            return 0
        }

        val depuis = reglages.lastScanMillis
        var plusRecent = depuis
        var verses = 0

        val projection = arrayOf(
            CallLog.Calls.NUMBER,
            CallLog.Calls.TYPE,
            CallLog.Calls.DATE,
            CallLog.Calls.DURATION,
        )

        // ⚠️ `use` : ce worker passe toutes les quinze minutes, et une base
        // laissée ouverte à chaque passage fuit une connexion SQLite. Le reste
        // du code ferme systématiquement ; ce chemin-ci ne le faisait pas.
        CallStore(context).use { store ->
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
        }

        // Curseur avancé même si rien n'a été versé : les appels hors plage
        // horaire ou de type ignoré ont bien été examinés, et les réexaminer à
        // chaque balayage ferait grossir le travail indéfiniment.
        //
        // ⚠️ Mais JAMAIS jusqu'à la frontière du présent, et c'est ce qui
        // manquait. `CallLog.Calls.DATE` est l'instant de DÉBUT de l'appel,
        // alors que la ligne n'est écrite qu'à sa fin. Un appel commencé à
        // 10 h 00 et raccroché à 10 h 45 apparaît donc APRÈS un appel manqué
        // de 10 h 10, dont la ligne, elle, était immédiate. Un balayage
        // intercalé portait le curseur à 10 h 10 ; la ligne de 10 h 00
        // arrivait ensuite et ne repassait plus jamais le filtre `DATE >`.
        // C'était le plus long appel de la matinée, et il disparaissait sans
        // trace. Garder une marge de recouvrement le rattrape ; les relectures
        // sont sans effet, l'index unique (numéro, début) les absorbe.
        //
        // Le `maxOf(depuis, …)` n'est pas facultatif : sans lui, un balayage
        // sur un journal vide ferait RECULER le curseur avant l'instant
        // d'activation, et déverserait dans le CRM tout l'historique
        // pré-activation — le défaut du 2026-08-10, dans l'autre sens.
        val plafond = maintenant - RECOUVREMENT_MILLIS
        val nouveau = maxOf(depuis, minOf(plusRecent, plafond))
        if (nouveau > depuis) reglages.lastScanMillis = nouveau

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

    private fun unAppelEstEnCours(context: Context): Boolean {
        if (ContextCompat.checkSelfPermission(context, Manifest.permission.READ_PHONE_STATE)
            != PackageManager.PERMISSION_GRANTED
        ) {
            // Sans l'autorisation, on ne sait pas : on balaye, comme avant.
            return false
        }
        val telephonie = context.getSystemService(Context.TELEPHONY_SERVICE) as? TelephonyManager
            ?: return false
        val etat = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            telephonie.callStateForSubscription
        } else {
            @Suppress("DEPRECATION")
            telephonie.callState
        }
        return etat != TelephonyManager.CALL_STATE_IDLE
    }

    /**
     * Marge de recouvrement du curseur. Voir [balayer].
     *
     * Deux heures couvrent largement la durée d'un appel commercial : c'est le
     * temps pendant lequel une ligne peut encore apparaître *derrière* une
     * ligne déjà lue.
     */
    private const val RECOUVREMENT_MILLIS = 2 * 60 * 60 * 1000L

    /**
     * Avance d'horloge tolérée sur le curseur avant de le considérer aberrant.
     *
     * Une minute : le curseur est posé à partir de la même horloge que celle
     * qui le relit, donc l'écart normal est nul. Ce qu'on cherche ici, c'est
     * l'écart de plusieurs jours d'une horloge qui a été corrigée après coup.
     */
    private const val TOLERANCE_HORLOGE_MILLIS = 60 * 1000L
}
