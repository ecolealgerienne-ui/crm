package com.echango.call_tracker

import android.annotation.SuppressLint
import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.PowerManager
import android.provider.Settings
import com.echango.call_tracker.data.CallStore
import com.echango.call_tracker.data.SecureSettings
import com.echango.call_tracker.sync.SyncWorker
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodCall
import io.flutter.plugin.common.MethodChannel

/**
 * Pont entre l'interface Flutter et la couche de capture.
 *
 * Ce canal ne transporte que de la lecture d'état et des réglages. La capture
 * et l'envoi n'y passent jamais : ils doivent fonctionner alors que cette
 * activité n'existe pas.
 */
class MainActivity : FlutterActivity() {

    override fun configureFlutterEngine(moteur: FlutterEngine) {
        super.configureFlutterEngine(moteur)

        MethodChannel(moteur.dartExecutor.binaryMessenger, CANAL)
            .setMethodCallHandler { appel, reponse -> traiter(appel, reponse) }
    }

    private fun traiter(appel: MethodCall, reponse: MethodChannel.Result) {
        val reglages = SecureSettings(applicationContext)

        when (appel.method) {
            "getSettings" -> reponse.success(
                mapOf(
                    "serverUrl" to reglages.serverUrl,
                    // Le jeton lui-même ne franchit jamais ce canal : le faire
                    // remonter jusqu'à Dart l'exposerait aux journaux, aux
                    // captures d'écran et aux outils d'inspection Flutter, sans
                    // qu'aucun écran n'ait besoin de le lire.
                    "hasToken" to reglages.token.isNotBlank(),
                    "captureEnabled" to reglages.captureEnabled,
                    "fromHour" to reglages.fromHour,
                    "toHour" to reglages.toHour,
                )
            )

            "saveSettings" -> {
                reglages.serverUrl = appel.argument<String>("serverUrl").orEmpty().trim()
                // Absent = inchangé. C'est ce qui permet à l'écran de réglages
                // de laisser le champ vide sans effacer un jeton déjà en place.
                appel.argument<String>("token")?.let { reglages.token = it.trim() }
                reglages.captureEnabled = appel.argument<Boolean>("captureEnabled") ?: false
                reglages.fromHour = appel.argument<Int>("fromHour") ?: 8
                reglages.toHour = appel.argument<Int>("toHour") ?: 19

                // Un jeton qui vient d'être saisi débloque une file en attente :
                // autant réessayer tout de suite plutôt qu'au prochain appel.
                SyncWorker.forcer(applicationContext)
                reponse.success(null)
            }

            "listCalls" -> {
                val limite = appel.argument<Int>("limit") ?: 200
                reponse.success(
                    CallStore(applicationContext).derniers(limite).map {
                        mapOf(
                            "id" to it.id.toInt(),
                            "clientEventId" to it.clientEventId,
                            "phoneNumber" to it.phoneNumber,
                            "direction" to it.direction,
                            "durationSeconds" to it.durationSeconds,
                            "startedAtMillis" to it.startedAtMillis,
                            "syncStatus" to it.syncStatus,
                            "lastError" to it.lastError,
                            "attempts" to it.attempts,
                        )
                    }
                )
            }

            "pendingCount" ->
                reponse.success(CallStore(applicationContext).nombreEnAttente())

            "syncNow" -> {
                SyncWorker.forcer(applicationContext)
                reponse.success(null)
            }

            "isBatteryOptimised" -> reponse.success(batterieOptimisee())

            "requestIgnoreBatteryOptimisations" -> {
                demanderExclusionBatterie()
                reponse.success(null)
            }

            else -> reponse.notImplemented()
        }
    }

    private fun batterieOptimisee(): Boolean {
        val gestionnaire = getSystemService(Context.POWER_SERVICE) as PowerManager
        return !gestionnaire.isIgnoringBatteryOptimizations(packageName)
    }

    /**
     * Ouvre la demande système d'exclusion de l'optimisation de batterie.
     *
     * C'est la seule parade au mode de défaillance le plus courant de ce genre
     * d'application : le système suspend les processus en arrière-plan, et la
     * capture s'arrête sans le moindre message. Les surcouches Samsung et
     * Xiaomi sont particulièrement agressives sur ce point.
     */
    @SuppressLint("BatteryLife")
    private fun demanderExclusionBatterie() {
        startActivity(
            Intent(
                Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS,
                Uri.parse("package:$packageName"),
            )
        )
    }

    private companion object {
        const val CANAL = "com.echango.call_tracker/capture"
    }
}
