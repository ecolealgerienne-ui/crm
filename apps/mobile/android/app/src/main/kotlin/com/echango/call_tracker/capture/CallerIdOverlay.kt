package com.echango.call_tracker.capture

import android.content.Context
import android.graphics.PixelFormat
import android.os.Build
import android.os.Handler
import android.os.Looper
import android.provider.Settings
import android.util.Log
import android.view.Gravity
import android.view.LayoutInflater
import android.view.View
import android.view.WindowManager
import android.widget.TextView
import com.echango.call_tracker.R
import com.echango.call_tracker.data.ContactCache
import com.echango.call_tracker.data.SecureSettings
import com.echango.call_tracker.sync.ContactClient
import com.echango.call_tracker.sync.FicheContact
import kotlin.concurrent.thread

/**
 * Affiche la fiche CRM du correspondant pendant que le téléphone sonne.
 *
 * Une vue posée par `WindowManager`, et non une activité : une activité
 * lancée à la sonnerie prendrait le dessus sur l'écran d'appel du système,
 * empêchant de décrocher. La surimpression se contente de se poser au-dessus.
 *
 * ⚠️ **Le bandeau s'affiche AVANT de connaître la fiche**, avec le numéro
 * seul, puis se complète. L'inverse — attendre la réponse d'Odoo pour
 * afficher — ferait apparaître la fiche après que l'utilisateur a décroché,
 * c'est-à-dire trop tard pour servir à quoi que ce soit.
 */
object CallerIdOverlay {

    private const val TAG = "CallTracker"

    /** Hauteur approximative de la carte d'appel entrant du système. */
    private const val DECALAGE_DP = 170

    private var vue: View? = null
    private val surLeFilPrincipal = Handler(Looper.getMainLooper())

    fun autorise(context: Context): Boolean = Settings.canDrawOverlays(context)

    fun montrer(context: Context, numero: String) {
        if (!autorise(context)) {
            Log.i(TAG, "Surimpression non autorisee, fiche CRM non affichee")
            return
        }
        surLeFilPrincipal.post { poser(context, numero) }
        thread(name = "call-tracker-fiche") { remplir(context, numero) }
    }

    fun cacher(context: Context) {
        surLeFilPrincipal.post {
            val actuelle = vue ?: return@post
            vue = null
            try {
                gestionnaire(context).removeView(actuelle)
            } catch (erreur: Exception) {
                // La vue a pu être retirée par le système (rotation, mort du
                // processus). Rien à réparer, et surtout rien qui justifie de
                // faire tomber le receveur d'appels.
                Log.w(TAG, "Retrait de la surimpression", erreur)
            }
        }
    }

    private fun poser(context: Context, numero: String) {
        if (vue != null) return

        val nouvelle = LayoutInflater.from(context)
            .inflate(R.layout.overlay_caller_id, null)
        nouvelle.findViewById<TextView>(R.id.nom).text = numero
        nouvelle.findViewById<TextView>(R.id.societe).apply {
            text = context.getString(R.string.overlay_recherche)
            visibility = View.VISIBLE
        }

        val parametres = WindowManager.LayoutParams(
            WindowManager.LayoutParams.MATCH_PARENT,
            WindowManager.LayoutParams.WRAP_CONTENT,
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O)
                WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY
            else
                @Suppress("DEPRECATION")
                WindowManager.LayoutParams.TYPE_PHONE,
            // NOT_FOCUSABLE est indispensable : sans lui, la surimpression
            // capte les touches et l'utilisateur ne peut plus décrocher.
            WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE or
                WindowManager.LayoutParams.FLAG_NOT_TOUCH_MODAL or
                WindowManager.LayoutParams.FLAG_SHOW_WHEN_LOCKED,
            PixelFormat.TRANSLUCENT,
        ).apply {
            gravity = Gravity.TOP
            // ⚠️ Décalé SOUS la notification d'appel entrant du système.
            //
            // À y = 80 le bandeau était bien dessiné mais entièrement masqué
            // par la carte « Décliner / Répondre », qui occupe le haut de
            // l'écran — constaté à l'essai le 2026-08-09, et invisible dans les
            // journaux puisque tout fonctionnait par ailleurs. Exprimé en dp
            // pour tenir sur les écrans de densités différentes.
            y = (DECALAGE_DP * context.resources.displayMetrics.density).toInt()
        }

        try {
            gestionnaire(context).addView(nouvelle, parametres)
            vue = nouvelle
        } catch (erreur: Exception) {
            Log.w(TAG, "Surimpression impossible", erreur)
        }
    }

    /** Interroge le cache puis, à défaut, Odoo. Toujours hors du fil principal. */
    private fun remplir(context: Context, numero: String) {
        val cache = ContactCache(context)
        if (cache.estConnuInconnu(numero)) {
            cacher(context)
            return
        }

        val fiche = cache.lire(numero) ?: run {
            val recue = ContactClient.chercher(SecureSettings(context), numero)
            if (recue != null) cache.ecrire(numero, recue) else cache.marquerInconnu(numero)
            recue
        }

        if (fiche == null) {
            // Rien à dire sur ce numéro : le bandeau disparaît plutôt que
            // d'afficher « inconnu », qui n'apprend rien et occupe l'écran.
            cacher(context)
            return
        }
        surLeFilPrincipal.post { afficher(fiche) }
    }

    private fun afficher(fiche: FicheContact) {
        val actuelle = vue ?: return
        actuelle.findViewById<TextView>(R.id.nom).text = fiche.name

        actuelle.findViewById<TextView>(R.id.societe).apply {
            text = fiche.company
            visibility = if (fiche.company.isBlank()) View.GONE else View.VISIBLE
        }
        actuelle.findViewById<TextView>(R.id.etape).apply {
            text = fiche.crmStage
            visibility = if (fiche.crmStage.isBlank()) View.GONE else View.VISIBLE
        }
        actuelle.findViewById<TextView>(R.id.note).apply {
            text = fiche.lastNotes
            visibility = if (fiche.lastNotes.isBlank()) View.GONE else View.VISIBLE
        }
    }

    private fun gestionnaire(context: Context) =
        context.applicationContext.getSystemService(Context.WINDOW_SERVICE) as WindowManager
}
