package com.echango.call_tracker.data

import androidx.test.core.app.ApplicationProvider
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner

/**
 * La file locale : dédoublonnage, retenue de note, transitions d'état.
 *
 * C'est la pièce dont dépend la promesse centrale du dispositif — « un appel
 * capturé est inscrit avant toute tentative d'envoi, il ne se perd pas ». Elle
 * n'était couverte par aucun test, et deux de ses défauts ne se voyaient que
 * sur un vrai téléphone, plusieurs jours après.
 */
@RunWith(RobolectricTestRunner::class)
class CallStoreTest {

    private lateinit var store: CallStore

    @Before
    fun avant() {
        store = CallStore(ApplicationProvider.getApplicationContext())
    }

    @After
    fun apres() {
        store.close()
    }

    private fun inserer(
        numero: String = "+213555000000",
        debut: Long = 1_000_000L,
        attente: Long = 0,
    ) = store.inserer(numero, CallStore.SORTANT, 42, debut, attente)

    // ── Dédoublonnage ────────────────────────────────────────────────────────

    @Test
    fun `le meme appel insere deux fois ne compte qu une fois`() {
        // `PHONE_STATE` est diffusé plusieurs fois pour un même appel, et le
        // balayage garde désormais une marge de recouvrement qui relit
        // volontairement des lignes déjà lues. Le dédoublonnage n'est donc pas
        // une précaution : c'est ce qui rend la relecture sûre.
        assertTrue(inserer() > 0)
        assertEquals(-1L, inserer())
        assertEquals(1, store.derniers().size)
    }

    @Test
    fun `deux appels au meme numero a des instants differents coexistent`() {
        inserer(debut = 1_000_000L)
        inserer(debut = 2_000_000L)
        assertEquals(2, store.derniers().size)
    }

    // ── Retenue de note ──────────────────────────────────────────────────────

    @Test
    fun `un appel retenu pour une note n est pas encore a envoyer`() {
        inserer(attente = 60_000L)
        assertTrue(store.aEnvoyer().isEmpty())
        assertEquals(1, store.enAttenteDeNote().size)
    }

    @Test
    fun `la retenue expiree libere l appel meme sans note`() {
        // Une fonctionnalité de confort ne doit pas pouvoir retenir la donnée
        // principale : passé le délai, l'appel part sans note.
        inserer(attente = -1L)
        assertEquals(1, store.aEnvoyer().size)
    }

    @Test
    fun `renoncer a la note libere l appel tout de suite`() {
        val id = inserer(attente = 600_000L)
        store.ignorerNote(id)
        assertEquals(1, store.aEnvoyer().size)
    }

    // ── La note écrite trop tard ─────────────────────────────────────────────

    @Test
    fun `une note ecrite apres l envoi remet l appel en file`() {
        // LE défaut que ce test verrouille. La retenue vaut deux minutes et
        // écrire une note en prend une : le commercial qui valide quelques
        // secondes trop tard voyait « Note enregistrée », et la note ne
        // partait jamais — seuls les `pending` sont envoyés.
        val id = inserer()
        store.marquerEnvoye(id)
        assertTrue(store.aEnvoyer().isEmpty())

        store.enregistrerNote(id, "Rappeler lundi")

        assertEquals(1, store.aEnvoyer().size)
        assertEquals("Rappeler lundi", store.parId(id)?.note)
    }

    @Test
    fun `un appel en echec definitif n est pas ressuscite par une note`() {
        // Il repartirait pour être refusé à l'identique, en boucle.
        val id = inserer()
        store.marquerEchecDefinitif(id, "horodatage aberrant")
        store.enregistrerNote(id, "Une note")
        assertTrue(store.aEnvoyer().isEmpty())
    }

    @Test
    fun `une note vide ne remet pas un appel deja envoye en file`() {
        val id = inserer()
        store.marquerEnvoye(id)
        store.enregistrerNote(id, null)
        assertTrue(store.aEnvoyer().isEmpty())
    }

    // ── Motif d'échec ────────────────────────────────────────────────────────

    @Test
    fun `un echec temporaire conserve le motif et laisse l appel en file`() {
        // Le motif est ce qui manquait le plus à ce dispositif : un jeton
        // refusé laissait un compteur monter sans que rien ne dise pourquoi.
        val id = inserer()
        store.noterEchecTemporaire(id, "Jeton refuse (401)")

        val appel = store.parId(id)
        assertEquals("Jeton refuse (401)", appel?.lastError)
        assertEquals(CallStore.EN_ATTENTE, appel?.syncStatus)
        assertEquals(1, store.nombreEnAttente())
    }

    @Test
    fun `une remise reussie efface le motif d echec precedent`() {
        val id = inserer()
        store.noterEchecTemporaire(id, "Serveur injoignable")
        store.marquerEnvoye(id)
        assertNull(store.parId(id)?.lastError)
    }

    // ── Purge locale ─────────────────────────────────────────────────────────

    @Test
    fun `la purge efface les appels remis et hors retention`() {
        // L'avis d'information annonce « les appels sont effacés
        // automatiquement au bout de N jours ». C'était vrai côté Odoo et faux
        // sur le téléphone : rien n'y était jamais supprimé.
        val vieux = inserer(debut = System.currentTimeMillis() - 40L * 24 * 3600 * 1000)
        store.marquerEnvoye(vieux)

        store.purger(jours = 30)

        assertNull(store.parId(vieux))
    }

    @Test
    fun `la purge epargne un appel qui n a jamais ete remis`() {
        // Le purger le ferait disparaître pour de bon : la copie locale est
        // tout ce qu'il en reste.
        val vieux = inserer(debut = System.currentTimeMillis() - 40L * 24 * 3600 * 1000)

        store.purger(jours = 30)

        assertNotNull(store.parId(vieux))
    }

    @Test
    fun `la purge epargne un appel remis mais recent`() {
        val recent = inserer(debut = System.currentTimeMillis())
        store.marquerEnvoye(recent)

        store.purger(jours = 30)

        assertNotNull(store.parId(recent))
    }

    @Test
    fun `le plafond borne la base meme sans retention connue`() {
        // Le serveur n'a jamais répondu : la base ne doit pas croître sans fin
        // pour autant.
        repeat(6) { i ->
            val id = inserer(debut = 1_000_000L + i)
            store.marquerEnvoye(id)
        }

        store.purger(jours = 0, plafond = 3)

        assertEquals(3, store.derniers().size)
    }
}
