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
     *
     * ⚠️ Retenu **deux minutes**, pas trente comme une fiche trouvée. Voir
     * [DUREE_INCONNU_MILLIS] : c'est le correctif d'un défaut observé.
     */
    fun marquerInconnu(numero: String) {
        prefs.edit()
            .putString(cle(numero), INCONNU)
            .putLong(cle(numero) + AGE, System.currentTimeMillis())
            .apply()
    }

    fun estConnuInconnu(numero: String): Boolean {
        val cle = cle(numero)
        if (prefs.getString(cle, null) != INCONNU) return false
        return System.currentTimeMillis() - prefs.getLong(cle + AGE, 0L) <= DUREE_INCONNU_MILLIS
    }

    fun vider() = prefs.edit().clear().apply()

    private fun cle(numero: String) = "f_" + numero.filter(Char::isDigit).takeLast(9)

    private companion object {
        const val FICHIER = "call_tracker_contacts"
        const val AGE = "_t"
        const val INCONNU = "-"
        const val DUREE_MILLIS = 30 * 60 * 1000L

        /**
         * Durée de rétention d'un **inconnu**, bien plus courte que celle
         * d'une fiche trouvée.
         *
         * Constaté le 2026-08-10 sur émulateur : un numéro appelé avant d'être
         * saisi dans le CRM restait « inconnu » à l'écran pendant trente
         * minutes, alors que la fiche existait depuis cinq. Le Caller ID ne
         * s'affichait pas, et rien ne le signalait — l'application n'appelait
         * même plus le serveur.
         *
         * Ce n'est pas un cas de laboratoire : la qualification est manuelle
         * ici, donc « un inconnu appelle → je crée le client → il rappelle »
         * est la séquence NORMALE. Deux minutes suffisent à couvrir le rappel
         * immédiat d'un démarcheur, qui est le seul cas que ce cache devait
         * éviter.
         */
        const val DUREE_INCONNU_MILLIS = 2 * 60 * 1000L
    }
}
