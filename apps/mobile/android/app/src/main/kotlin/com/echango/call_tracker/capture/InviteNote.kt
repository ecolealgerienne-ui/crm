package com.echango.call_tracker.capture

import android.Manifest
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import androidx.core.content.ContextCompat
import com.echango.call_tracker.MainActivity

/**
 * Invite le commercial à noter ce qui vient d'être dit.
 *
 * Une notification, et non un écran qui s'impose : l'app n'est presque jamais
 * au premier plan quand un appel se termine, et surgir par-dessus l'écran
 * d'accueil juste après un raccrochage serait une intrusion. La notification
 * attend, elle.
 */
object InviteNote {

    const val EXTRA_ID_APPEL = "call_tracker_note_call_id"

    private const val CANAL = "call_tracker_notes"
    private const val TAG_NOTIFICATION = "call_tracker_note"

    /** Durée pendant laquelle l'appel est retenu, le temps d'une note. */
    const val DELAI_NOTE_MILLIS = 2 * 60 * 1000L

    fun proposer(context: Context, idAppel: Long, numero: String) {
        if (!autorise(context)) return

        creerCanal(context)

        val intention = Intent(context, MainActivity::class.java).apply {
            flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP
            putExtra(EXTRA_ID_APPEL, idAppel)
        }
        val enAttente = PendingIntent.getActivity(
            context,
            // `idAppel` en code de requête : sans lui, deux appels successifs
            // partageraient le même PendingIntent et le second réutiliserait
            // l'extra du premier — la note atterrirait sur le mauvais appel.
            idAppel.toInt(),
            intention,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
        )

        val notification = NotificationCompat.Builder(context, CANAL)
            .setSmallIcon(android.R.drawable.sym_action_chat)
            .setContentTitle("Ajouter une note ?")
            .setContentText(numero)
            .setPriority(NotificationCompat.PRIORITY_DEFAULT)
            .setAutoCancel(true)
            // Disparaît d'elle-même à l'échéance de la retenue : une invite
            // périmée, sur un appel déjà parti, ne ferait qu'induire en erreur.
            .setTimeoutAfter(DELAI_NOTE_MILLIS)
            .setContentIntent(enAttente)
            .build()

        NotificationManagerCompat.from(context)
            .notify(TAG_NOTIFICATION, idAppel.toInt(), notification)
    }

    fun retirer(context: Context, idAppel: Long) {
        NotificationManagerCompat.from(context).cancel(TAG_NOTIFICATION, idAppel.toInt())
    }

    /**
     * Depuis Android 13, notifier demande une permission accordée par
     * l'utilisateur. Sans elle on ne notifie pas — et surtout, on ne fait pas
     * échouer la capture pour autant : l'appel est journalisé et part sans
     * note, ce qui reste le comportement utile.
     */
    private fun autorise(context: Context): Boolean {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.TIRAMISU) return true
        return ContextCompat.checkSelfPermission(
            context, Manifest.permission.POST_NOTIFICATIONS
        ) == PackageManager.PERMISSION_GRANTED
    }

    private fun creerCanal(context: Context) {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return
        val gestionnaire = context.getSystemService(NotificationManager::class.java)
        if (gestionnaire.getNotificationChannel(CANAL) != null) return
        gestionnaire.createNotificationChannel(
            NotificationChannel(
                CANAL,
                "Notes après appel",
                // IMPORTANCE_DEFAULT et non HIGH : l'invite ne doit pas
                // s'imposer en surimpression ni sonner. Elle propose, elle
                // n'interrompt pas.
                NotificationManager.IMPORTANCE_DEFAULT,
            ).apply {
                description = "Propose de noter ce qui s'est dit, juste après un appel."
                setShowBadge(false)
            }
        )
    }
}
