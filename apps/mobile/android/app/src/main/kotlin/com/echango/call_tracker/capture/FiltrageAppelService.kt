package com.echango.call_tracker.capture

import android.telecom.Call
import android.telecom.CallScreeningService
import android.util.Log
import com.echango.call_tracker.data.SecureSettings
import java.util.Calendar

/**
 * Source du numéro entrant, et **seule qui fonctionne encore**.
 *
 * ⚠️ La voie évidente — `EXTRA_INCOMING_NUMBER` sur la diffusion
 * `PHONE_STATE` — ne marche plus. Android la renvoie VIDE aux applications
 * ordinaires, y compris avec `READ_CALL_LOG` accordée : vérifié sur Android 16
 * le 2026-08-09, la diffusion arrive bien mais sans numéro. Le défaut est
 * silencieux, la sonnerie est détectée et il n'y a simplement personne à
 * afficher.
 *
 * `CallScreeningService` est l'API que le système destine à cet usage. Elle
 * demande un **rôle** que l'utilisateur accorde explicitement
 * (`ROLE_CALL_SCREENING`) — sans exiger de devenir l'application Téléphone par
 * défaut, contrairement à ce que la spec §6 laissait craindre.
 *
 * Ce service ne filtre rien. Il regarde et laisse passer : bloquer un appel
 * n'est pas le sujet, et une réponse mal formée ferait rater des appels.
 */
class FiltrageAppelService : CallScreeningService() {

    override fun onScreenCall(details: Call.Details) {
        // Répondre EN PREMIER, avant tout travail : tant que le service n'a pas
        // répondu, le système retient la sonnerie. Une fiche CRM ne vaut pas
        // un appel retardé, et surtout pas un appel perdu si le réseau traîne.
        respondToCall(details, CallResponse.Builder().build())

        if (details.callDirection != Call.Details.DIRECTION_INCOMING) return

        // ⚠️ La plage horaire vaut ICI aussi, et pas seulement au balayage.
        // Ce service ne journalise rien, mais il déclenche la recherche de
        // fiche — donc une requête vers Odoo, donc une ligne d'audit portant
        // LE NUMÉRO de l'appelant, conservée aussi longtemps que le reste.
        // L'avis d'information promet « rien en dehors de la plage horaire
        // indiquée dans les réglages » : un appel personnel reçu à 23 h partait
        // quand même au serveur. La promesse était fausse, et c'est le seul
        // écran censé dire la vérité au commercial sur sa propre surveillance.
        val reglages = SecureSettings(applicationContext)
        if (!reglages.captureEnabled) return
        if (!reglages.dansLaPlage(heureCourante())) {
            Log.i(TAG, "Hors plage horaire : pas de fiche, pas de requete")
            return
        }

        // `schemeSpecificPart` d'un URI `tel:` : le numéro sans son préfixe.
        val numero = details.handle?.schemeSpecificPart?.trim().orEmpty()
        if (numero.isEmpty()) {
            Log.i(TAG, "Appel entrant sans numero (masque) : pas de fiche")
            return
        }

        Log.i(TAG, "Appel entrant de $numero, recherche de la fiche")
        CallerIdOverlay.montrer(applicationContext, numero)
    }

    private fun heureCourante(): Int =
        Calendar.getInstance().get(Calendar.HOUR_OF_DAY)

    private companion object {
        const val TAG = "CallTracker"
    }
}
