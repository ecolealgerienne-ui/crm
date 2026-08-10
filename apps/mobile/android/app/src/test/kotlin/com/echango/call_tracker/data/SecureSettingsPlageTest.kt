package com.echango.call_tracker.data

import androidx.test.core.app.ApplicationProvider
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner

/**
 * La plage horaire de capture.
 *
 * Fonction arithmétique pure, dont dépendent deux décisions lourdes : ce qui
 * entre dans le CRM, et — depuis le 2026-08-10 — ce qui déclenche une requête
 * vers Odoo à la sonnerie. L'avis d'information promet « rien en dehors de la
 * plage horaire indiquée dans les réglages » ; ces bornes sont donc la
 * traduction en code d'une phrase montrée aux commerciaux.
 */
@RunWith(RobolectricTestRunner::class)
class SecureSettingsPlageTest {

    private lateinit var reglages: SecureSettings

    @Before
    fun avant() {
        reglages = SecureSettings(ApplicationProvider.getApplicationContext())
    }

    private fun plage(de: Int, a: Int) {
        reglages.fromHour = de
        reglages.toHour = a
    }

    @Test
    fun `une plage ordinaire retient ses heures et rejette les autres`() {
        plage(8, 19)
        assertTrue(reglages.dansLaPlage(8))
        assertTrue(reglages.dansLaPlage(12))
        assertTrue(reglages.dansLaPlage(18))
        assertFalse(reglages.dansLaPlage(19))
        assertFalse(reglages.dansLaPlage(7))
        assertFalse(reglages.dansLaPlage(23))
    }

    @Test
    fun `la borne de debut est incluse et celle de fin exclue`() {
        plage(9, 10)
        assertTrue(reglages.dansLaPlage(9))
        assertFalse(reglages.dansLaPlage(10))
    }

    @Test
    fun `une plage qui enjambe minuit reste continue`() {
        // Le commercial de garde n'a pas à voir sa plage refusée parce qu'elle
        // traverse minuit.
        plage(22, 6)
        assertTrue(reglages.dansLaPlage(22))
        assertTrue(reglages.dansLaPlage(23))
        assertTrue(reglages.dansLaPlage(0))
        assertTrue(reglages.dansLaPlage(5))
        assertFalse(reglages.dansLaPlage(6))
        assertFalse(reglages.dansLaPlage(12))
    }

    @Test
    fun `des bornes egales signifient toute la journee`() {
        // Et surtout PAS « aucune heure » : le repli silencieux d'un réglage
        // mal saisi ne doit pas éteindre la capture sans le dire.
        plage(0, 0)
        for (heure in 0..23) {
            assertTrue("heure $heure", reglages.dansLaPlage(heure))
        }
    }

    @Test
    fun `minuit est dans une plage de nuit et hors d une plage de jour`() {
        plage(8, 19)
        assertFalse(reglages.dansLaPlage(0))
        plage(19, 8)
        assertTrue(reglages.dansLaPlage(0))
    }
}
