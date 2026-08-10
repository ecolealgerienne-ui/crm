package com.echango.call_tracker

import android.annotation.SuppressLint
import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.PowerManager
import android.provider.Settings
import com.echango.call_tracker.capture.CallerIdOverlay
import com.echango.call_tracker.capture.InviteNote
import com.echango.call_tracker.data.CallStore
import com.echango.call_tracker.data.ContactCache
import com.echango.call_tracker.data.SecureSettings
import com.echango.call_tracker.sync.ActiviteClient
import com.echango.call_tracker.sync.ContactClient
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

    /** Appel dont la notification vient d'être touchée, en attente de lecture. */
    private var idAppelEnAttente: Long? = null

    override fun onCreate(etat: android.os.Bundle?) {
        super.onCreate(etat)
        recupererIdAppel(intent)
    }

    /**
     * L'activité est en `singleTop` : touchée une seconde fois, elle est
     * réutilisée et `onCreate` n'est PAS rappelé. Sans cette surcharge, seule
     * la première notification ouvrirait une invite de note.
     */
    override fun onNewIntent(intention: Intent) {
        super.onNewIntent(intention)
        setIntent(intention)
        recupererIdAppel(intention)
    }

    private fun recupererIdAppel(intention: Intent?) {
        val id = intention?.getLongExtra(InviteNote.EXTRA_ID_APPEL, -1L) ?: -1L
        if (id > 0) idAppelEnAttente = id
    }

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
                    // Politique de conservation annoncée par le serveur, pour
                    // l'écran d'information. `retentionKnown` à faux tant
                    // qu'aucun appel n'a été accepté : l'écran dit alors que
                    // la durée est fixée par l'employeur, sans avancer un
                    // chiffre qu'il ne tient de personne.
                    "retentionDays" to reglages.retentionDays,
                    "retentionKnown" to reglages.retentionKnown,
                )
            )

            "saveSettings" -> {
                reglages.serverUrl = appel.argument<String>("serverUrl").orEmpty().trim()
                // Absent = inchangé. C'est ce qui permet à l'écran de réglages
                // de laisser le champ vide sans effacer un jeton déjà en place.
                appel.argument<String>("token")?.let { reglages.token = it.trim() }

                // ⚠️ **Le suivi commence à l'activation, jamais avant.**
                //
                // Le curseur de balayage vaut 0 tant qu'aucun appel n'a été lu,
                // et le balayage interroge `DATE > curseur`. Sans cette ligne,
                // la première activation verse dans le CRM **tout l'historique
                // d'appels du téléphone** — des années, la vie privée du
                // commercial comprise.
                //
                // Le défaut est invisible en développement : un émulateur neuf
                // n'a qu'une poignée d'appels de test. Il ne se serait vu que
                // sur le premier vrai téléphone, une fois les données parties.
                //
                // Il est aussi contraire à ce que l'avis d'information promet
                // — « l'application transmet vos appels professionnels », au
                // présent — et une collecte rétroactive de cette ampleur ne
                // serait pas proportionnée à la finalité (loi 18-07).
                //
                // Positionné à chaque passage de désactivé à activé, pas
                // seulement au tout premier : couper la capture est un acte
                // délibéré, et la rallumer ne doit pas rattraper ce qu'on avait
                // choisi de ne pas journaliser.
                val etaitActive = reglages.captureEnabled
                reglages.captureEnabled = appel.argument<Boolean>("captureEnabled") ?: false
                if (!etaitActive && reglages.captureEnabled) {
                    reglages.lastScanMillis = System.currentTimeMillis()
                }

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
                    CallStore(applicationContext).use { it.derniers(limite) }.map {
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
                            "note" to it.note,
                            "awaitingNote" to (it.awaitingNoteUntil > System.currentTimeMillis()),
                        )
                    }
                )
            }

            "pendingCount" ->
                reponse.success(CallStore(applicationContext).use { it.nombreEnAttente() })

            "saveNote" -> {
                val id = (appel.argument<Number>("id") ?: 0).toLong()
                CallStore(applicationContext)
                    .use { it.enregistrerNote(id, appel.argument<String>("note")) }
                InviteNote.retirer(applicationContext, id)
                SyncWorker.forcer(applicationContext)
                reponse.success(null)
            }

            "skipNote" -> {
                val id = (appel.argument<Number>("id") ?: 0).toLong()
                CallStore(applicationContext).use { it.ignorerNote(id) }
                InviteNote.retirer(applicationContext, id)
                SyncWorker.forcer(applicationContext)
                reponse.success(null)
            }

            // Identifiant transmis par la notification, consommé UNE fois :
            // sans cela, revenir sur l'application rouvrirait indéfiniment la
            // même invite de note.
            "consumePendingNoteCallId" -> {
                reponse.success(idAppelEnAttente)
                idAppelEnAttente = null
            }

            "syncNow" -> {
                SyncWorker.forcer(applicationContext)
                reponse.success(null)
            }

            // Recherche depuis l'application : passe par le CACHE avant le
            // réseau, exactement comme la surimpression. Un commercial qui
            // cherche un numéro qu'il vient de voir sonner ne doit pas
            // provoquer un second appel à l'Odoo du client.
            // Les appels programmes dans le CRM. Le cache est rendu tout de
            // suite ; le rafraichissement suit, sur son fil.
            "listActivities" -> {
                val forcer = appel.argument<Boolean>("refresh") ?: false
                Thread {
                    if (forcer) ActiviteClient.rafraichir(applicationContext)
                    val liste = ActiviteClient.lireCache(applicationContext)
                    val date = ActiviteClient.dateDuCache(applicationContext)
                    runOnUiThread {
                        reponse.success(
                            mapOf(
                                // Millisecondes de la derniere recuperation
                                // reussie. AFFICHEE a l'ecran : une liste
                                // d'hier vaut mieux qu'un ecran vide, a
                                // condition de dire qu'elle date d'hier.
                                "fetchedAtMillis" to date,
                                "results" to liste.map {
                                    mapOf(
                                        "id" to it.id,
                                        "client" to it.client,
                                        "phone" to it.phone,
                                        "deadline" to it.deadline,
                                        "state" to it.state,
                                        "summary" to it.summary,
                                        "note" to it.note,
                                    )
                                },
                            )
                        )
                    }
                }.start()
            }

            "completeActivity" -> {
                val id = (appel.argument<Number>("id") ?: 0).toLong()
                Thread {
                    val ok = ActiviteClient.cloturer(applicationContext, id)
                    runOnUiThread { reponse.success(ok) }
                }.start()
            }

            "searchContacts" -> {
                val fragment = appel.argument<String>("fragment").orEmpty().trim()
                Thread {
                    val resultats = ContactClient.rechercher(reglages, fragment)
                    runOnUiThread {
                        reponse.success(
                            resultats.map {
                                mapOf(
                                    "name" to it.name,
                                    "company" to it.company,
                                    "phone" to it.phone,
                                    "crm_stage" to it.crmStage,
                                )
                            }
                        )
                    }
                }.start()
            }

            // Ouvre le clavier du téléphone avec le numéro composé, SANS le
            // lancer.
            //
            // `ACTION_DIAL` et non `ACTION_CALL`, et ce n'est pas de la
            // timidité : `ACTION_CALL` exige la permission `CALL_PHONE`, une
            // permission dangereuse de plus sur une application qui en
            // demande déjà une restreinte (`READ_CALL_LOG`) et le rôle de
            // filtrage d'appels. Elle donnerait surtout à l'application le
            // pouvoir de passer un appel toute seule — sur la ligne
            // professionnelle de quelqu'un, un bogue coûterait de l'argent et
            // de la confiance. Le vert du clavier reste sous le pouce du
            // commercial. Un appui de plus, et la chaîne de capture prend le
            // relais comme pour n'importe quel appel.
            "dial" -> {
                val numero = appel.argument<String>("phoneNumber").orEmpty().trim()
                if (numero.isBlank()) {
                    reponse.success(false)
                } else {
                    startActivity(
                        android.content.Intent(
                            android.content.Intent.ACTION_DIAL,
                            android.net.Uri.fromParts("tel", numero, null),
                        )
                    )
                    reponse.success(true)
                }
            }

            "lookupContact" -> {
                val numero = appel.argument<String>("phoneNumber").orEmpty().trim()
                Thread {
                    val cache = ContactCache(applicationContext)
                    val fiche = cache.lire(numero)
                        ?: ContactClient.chercher(reglages, numero)
                            ?.also { cache.ecrire(numero, it) }
                    // La réponse doit repartir sur le fil principal : le canal
                    // de plateforme n'est pas utilisable depuis un autre.
                    runOnUiThread {
                        reponse.success(
                            fiche?.let {
                                mapOf(
                                    "name" to it.name,
                                    "company" to it.company,
                                    "last_notes" to it.lastNotes,
                                    "crm_stage" to it.crmStage,
                                )
                            }
                        )
                    }
                }.start()
            }

            "hasCallScreeningRole" -> reponse.success(roleFiltrageAccorde())

            "requestCallScreeningRole" -> {
                demanderRoleFiltrage()
                reponse.success(null)
            }

            "canDrawOverlay" -> reponse.success(CallerIdOverlay.autorise(applicationContext))

            "requestOverlayPermission" -> {
                // Pas de dialogue possible : cette permission s'accorde dans
                // un écran des réglages du système, que l'on ne peut
                // qu'ouvrir.
                startActivity(
                    Intent(
                        Settings.ACTION_MANAGE_OVERLAY_PERMISSION,
                        Uri.parse("package:$packageName"),
                    )
                )
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

    /**
     * Le rôle de filtrage d'appels est-il accordé ?
     *
     * C'est lui qui donne accès au numéro entrant — voir FiltrageAppelService.
     * `RoleManager` n'existe qu'à partir d'Android 10 ; en dessous, seule
     * l'application Téléphone par défaut y a droit, cas qu'on ne vise pas.
     */
    private fun roleFiltrageAccorde(): Boolean {
        if (android.os.Build.VERSION.SDK_INT < android.os.Build.VERSION_CODES.Q) return false
        val gestionnaire = getSystemService(android.app.role.RoleManager::class.java)
        return gestionnaire?.isRoleHeld(android.app.role.RoleManager.ROLE_CALL_SCREENING) == true
    }

    private fun demanderRoleFiltrage() {
        if (android.os.Build.VERSION.SDK_INT < android.os.Build.VERSION_CODES.Q) return
        val gestionnaire = getSystemService(android.app.role.RoleManager::class.java) ?: return
        if (!gestionnaire.isRoleAvailable(android.app.role.RoleManager.ROLE_CALL_SCREENING)) return
        startActivityForResult(
            gestionnaire.createRequestRoleIntent(
                android.app.role.RoleManager.ROLE_CALL_SCREENING
            ),
            DEMANDE_ROLE,
        )
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
        const val DEMANDE_ROLE = 7301
    }
}
