package com.echango.call_tracker.data

import android.content.Context
import com.echango.call_tracker.sync.ContactClient
import com.echango.call_tracker.sync.FicheContact

/**
 * Cache local des fiches contact.
 *
 * La spec confiait ce rôle à un Redis à TTL court, côté plateforme. Cette
 * plateforme n'existe pas dans l'architecture directe retenue : sans cache,
 * chaque sonnerie déclencherait un appel réseau à l'Odoo du client. Le cache
 * a donc suivi jusqu'ici.
 *
 * Rangé dans des SharedPreferences ordinaires et non chiffrées, à la
 * différence du jeton : ce sont quatre champs déjà destinés à s'afficher en
 * grand sur l'écran verrouillé du téléphone. Les protéger au repos serait un
 * théâtre.
 */
class ContactCache(context: Context) {

    private val prefs = context.getSharedPreferences(FICHIER, Context.MODE_PRIVATE)

    /**
     * Fiche encore valable pour ce numéro, ou `null`.
     *
     * Trente minutes : assez pour qu'un client qui rappelle dans la foulée
     * n'entraîne pas de second appel réseau, assez court pour qu'une note
     * écrite après le premier appel apparaisse au suivant — c'est précisément
     * la boucle que la fonctionnalité doit refermer.
     */
    fun lire(numero: String): FicheContact? {
        val cle = cle(numero)
        val depose = prefs.getLong(cle + AGE, 0L)
        if (System.currentTimeMillis() - depose > DUREE_MILLIS) return null
        val brut = prefs.getString(cle, null) ?: return null
        return ContactClient.lire(brut)
    }

    fun ecrire(numero: String, fiche: FicheContact) {
        prefs.edit()
            .putString(cle(numero), ContactClient.serialiser(fiche))
            .putLong(cle(numero) + AGE, System.currentTimeMillis())
            .apply()
    }

    /**
     * Mémorise qu'un numéro est inconnu du CRM.
     *
     * Sans cela, les numéros inconnus — démarchage, taxi, famille — feraient
     * un appel réseau à chaque sonnerie, précisément ceux pour lesquels il n'y
     * a rien à afficher.
     */
    fun marquerInconnu(numero: String) {
        prefs.edit()
            .putString(cle(numero), INCONNU)
            .putLong(cle(numero) + AGE, System.currentTimeMillis())
            .apply()
    }

    fun estConnuInconnu(numero: String): Boolean {
        val cle = cle(numero)
        if (System.currentTimeMillis() - prefs.getLong(cle + AGE, 0L) > DUREE_MILLIS) return false
        return prefs.getString(cle, null) == INCONNU
    }

    fun vider() = prefs.edit().clear().apply()

    private fun cle(numero: String) = "f_" + numero.filter(Char::isDigit).takeLast(9)

    private companion object {
        const val FICHIER = "call_tracker_contacts"
        const val AGE = "_t"
        const val INCONNU = "-"
        const val DUREE_MILLIS = 30 * 60 * 1000L
    }
}
