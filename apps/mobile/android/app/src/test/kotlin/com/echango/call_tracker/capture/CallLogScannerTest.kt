package com.echango.call_tracker.capture

import android.app.Application
import android.content.Context
import androidx.test.core.app.ApplicationProvider
import androidx.work.Configuration
import androidx.work.testing.SynchronousExecutor
import androidx.work.testing.WorkManagerTestInitHelper
import com.echango.call_tracker.data.CallStore
import com.echango.call_tracker.data.SecureSettings
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.Shadows.shadowOf

/**
 * Le curseur de balayage — la pièce la plus silencieuse du dispositif.
 *
 * Tous les défauts couverts ici ont la même signature : la capture s'arrête ou
 * saute un appel, et **tout indique que rien ne va mal**. L'écran affiche
 * « Tout est synchronisé », la file est vide, aucune erreur n'est journalisée.
 * Ils ne se voient qu'en réunion, des semaines plus tard, quand un commercial
 * dont on croyait qu'il ne téléphonait plus s'en défend.
 */
@RunWith(RobolectricTestRunner::class)
class CallLogScannerTest {

    private lateinit var contexte: Context
    private lateinit var reglages: SecureSettings

    private val uneHeure = 3_600_000L
    private val maintenant get() = System.currentTimeMillis()

    @Before
    fun avant() {
        contexte = ApplicationProvider.getApplicationContext()
        WorkManagerTestInitHelper.initializeTestWorkManager(
            contexte,
            Configuration.Builder().setExecutor(SynchronousExecutor()).build(),
        )
        shadowOf(contexte as Application).grantPermissions(
            android.Manifest.permission.READ_CALL_LOG,
        )
        JournalFactice.vider()
        // Le faux journal n'est pas declare au manifeste : on le branche a la
        // main sur l'autorite que `CallLog.Calls.CONTENT_URI` vise.
        org.robolectric.shadows.ShadowContentResolver.registerProviderInternal(
            android.provider.CallLog.AUTHORITY,
            JournalFactice().apply { onCreate() },
        )

        reglages = SecureSettings(contexte)
        reglages.captureEnabled = true
        // Toute la journée : ces tests portent sur le curseur, pas sur la
        // plage horaire, qui a ses propres cas.
        reglages.fromHour = 0
        reglages.toHour = 0
        CallStore(contexte).use { it.writableDatabase.execSQL("DELETE FROM call_event") }
    }

    @After
    fun apres() {
        JournalFactice.vider()
    }

    private fun enFile(): List<Long> =
        CallStore(contexte).use { store -> store.derniers().map { it.startedAtMillis } }

    // ── L'invariant « jamais l'historique » ──────────────────────────────────

    @Test
    fun `un curseur a zero pose le repere sans rien remonter`() {
        // Un zéro ne fait pas rien : il verserait dans le CRM tout l'historique
        // du téléphone, vie privée comprise, sans qu'aucune erreur ne le dise.
        reglages.lastScanMillis = 0L
        JournalFactice.ajouter(maintenant - 10 * uneHeure)

        assertEquals(0, CallLogScanner.balayer(contexte))

        assertTrue(enFile().isEmpty())
        assertTrue(reglages.lastScanMillis > 0L)
    }

    @Test
    fun `un curseur dans le futur est ramene a maintenant sans rien remonter`() {
        // Le défaut symétrique, et le plus vicieux. Une horloge fausse au
        // moment de l'activation pose le repère dans plusieurs jours ; le NTP
        // corrige ensuite, et `DATE > curseur` n'est plus jamais vrai. La
        // capture est morte pour toujours, en silence.
        val dansQuatreJours = maintenant + 4 * 24 * uneHeure
        reglages.lastScanMillis = dansQuatreJours
        JournalFactice.ajouter(maintenant - 10 * uneHeure)

        assertEquals(0, CallLogScanner.balayer(contexte))

        assertTrue(
            "le curseur doit redescendre à maintenant",
            reglages.lastScanMillis < dansQuatreJours,
        )
        assertTrue("mais pas remonter le passé", enFile().isEmpty())
    }

    @Test
    fun `apres un curseur ramene la capture repart`() {
        reglages.lastScanMillis = maintenant + 4 * 24 * uneHeure
        CallLogScanner.balayer(contexte)

        JournalFactice.ajouter(maintenant + 1000)
        CallLogScanner.balayer(contexte)

        assertEquals(1, enFile().size)
    }

    // ── La marge de recouvrement ─────────────────────────────────────────────

    @Test
    fun `un appel long apparu derriere un appel court est quand meme capture`() {
        // LE défaut que la marge ferme. `DATE` est l'instant de DÉBUT, alors
        // que la ligne n'est écrite qu'à la fin : un appel commencé à 10 h 00
        // et raccroché à 10 h 45 apparaît APRÈS un appel manqué de 10 h 10.
        // Sans marge, le curseur passait à 10 h 10 et la ligne de 10 h 00 ne
        // repassait plus jamais le filtre. C'était le plus long appel de la
        // matinée.
        reglages.lastScanMillis = maintenant - 30 * 60 * 1000

        val court = maintenant - 20 * 60 * 1000
        JournalFactice.ajouter(court, numero = "+213555111111")
        CallLogScanner.balayer(contexte)

        val long = maintenant - 25 * 60 * 1000
        JournalFactice.ajouter(long, numero = "+213555222222")
        CallLogScanner.balayer(contexte)

        assertTrue(
            "l'appel long doit avoir été rattrapé",
            enFile().contains(long),
        )
    }

    @Test
    fun `le curseur n avance jamais jusqu au present`() {
        val depart = maintenant - 30 * 60 * 1000
        reglages.lastScanMillis = depart
        JournalFactice.ajouter(maintenant - 60_000)

        CallLogScanner.balayer(contexte)

        assertTrue(
            "le curseur ne doit pas franchir la marge de recouvrement",
            reglages.lastScanMillis <= maintenant - 2 * uneHeure ||
                reglages.lastScanMillis == depart,
        )
    }

    @Test
    fun `le curseur avance bien sur des appels anciens`() {
        // La marge borne l'avance, elle ne la bloque pas : sinon chaque
        // balayage relirait un journal de plus en plus gros.
        val depart = maintenant - 10 * uneHeure
        reglages.lastScanMillis = depart
        JournalFactice.ajouter(maintenant - 5 * uneHeure)

        CallLogScanner.balayer(contexte)

        assertTrue(reglages.lastScanMillis > depart)
    }

    @Test
    fun `le curseur ne recule jamais sur un journal vide`() {
        // `maxOf(depuis, …)` : sans lui, la marge ferait RECULER le curseur
        // avant l'instant d'activation, et déverserait l'historique
        // pré-activation — le défaut d'origine, dans l'autre sens.
        val depart = maintenant - 60_000
        reglages.lastScanMillis = depart

        CallLogScanner.balayer(contexte)

        assertEquals(depart, reglages.lastScanMillis)
    }

    // ── Ce qui filtre ────────────────────────────────────────────────────────

    @Test
    fun `un appel hors plage horaire n entre pas dans la file`() {
        reglages.lastScanMillis = maintenant - 10 * uneHeure
        // Plage impossible à satisfaire pour l'heure courante : 1 h le matin.
        val heure = java.util.Calendar.getInstance()
            .get(java.util.Calendar.HOUR_OF_DAY)
        reglages.fromHour = (heure + 2) % 24
        reglages.toHour = (heure + 3) % 24

        JournalFactice.ajouter(maintenant - 60_000)
        CallLogScanner.balayer(contexte)

        assertTrue(enFile().isEmpty())
    }

    @Test
    fun `la capture desactivee ne lit rien et ne touche pas au curseur`() {
        reglages.captureEnabled = false
        val depart = maintenant - 60_000
        reglages.lastScanMillis = depart
        JournalFactice.ajouter(maintenant - 30_000)

        assertEquals(0, CallLogScanner.balayer(contexte))

        assertEquals(depart, reglages.lastScanMillis)
        assertTrue(enFile().isEmpty())
    }

    @Test
    fun `le meme appel relu par la marge ne cree pas de doublon`() {
        reglages.lastScanMillis = maintenant - 30 * 60 * 1000
        JournalFactice.ajouter(maintenant - 10 * 60 * 1000)

        CallLogScanner.balayer(contexte)
        CallLogScanner.balayer(contexte)

        assertEquals(1, enFile().size)
    }
}
