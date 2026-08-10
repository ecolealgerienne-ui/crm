# -*- coding: utf-8 -*-
from odoo import _, fields, models
from odoo.exceptions import UserError


class CallTrackerNoteWizard(models.TransientModel):
    """Compléter, depuis un appel, ce qui se sait sur le client.

    **Pourquoi un assistant plutôt qu'un champ modifiable sur l'appel.**

    L'appel est le compte rendu d'un **événement** : il est figé par nature,
    et il doit le rester — les faits qu'il porte (durée, horodatage, sens)
    sont le socle du reporting. Une durée corrigeable rendrait chaque chiffre
    négociable en réunion, et la mesure du délai de remise ne vaudrait plus
    rien.

    Le fil de discussion, lui, est l'histoire de la **relation** : cumulatif
    par nature. Une note mal dictée dans la voiture ne se réécrit donc pas —
    on écrit la bonne en dessous. C'est le modèle d'Odoo, et il est juste.

    Cet assistant ne fait qu'une chose : éviter le détour. Sans lui, compléter
    demande d'ouvrir la fiche client, trouver le fil, cliquer « Log note ».
    Trois gestes depuis un écran qu'on quitte, pour une phrase.

    ⚠️ **Le message est publié tel quel, sans en-tête.** Contrairement à la
    trace d'un appel, aucun « Appel sortant — +213… » ne le précède : c'est
    ce même message que ``_derniere_note`` renvoie au Caller ID, tronqué à
    200 caractères. Un en-tête mangerait la moitié de ce que le commercial
    lira à la sonnerie suivante, pour redire ce que le fil affiche déjà.
    """

    _name = 'call.tracker.note.wizard'
    _description = "Compléter la note d'un appel"

    call_id = fields.Many2one('call.tracker.log', required=True, readonly=True)
    target_name = fields.Char(string="Publiée sur", readonly=True)
    # Pas `required=True` : cela poserait un NOT NULL en base, et l'assistant
    # est créé **vide** par l'appel avant d'être présenté à l'écran. L'exigence
    # appartient à la vue, et le vide est refusé par `action_publier`.
    note = fields.Text(string="Note")

    def action_publier(self):
        self.ensure_one()
        cible = self.call_id.lead_id or self.call_id.partner_id
        if not cible:
            # Ne devrait pas arriver : le bouton est masqué dans ce cas. Mais
            # un appel peut être qualifié par quelqu'un d'autre entre
            # l'ouverture de l'assistant et la validation.
            raise UserError(_(
                "Cet appel n'est rattaché à aucun client ni à aucune piste. "
                "Qualifiez-le d'abord : la note n'aurait nulle part où aller."
            ))

        texte = (self.note or '').strip()
        if not texte:
            raise UserError(_("La note est vide."))

        # **Pas de sudo(), volontairement.** Publier au nom de l'utilisateur
        # réel fait jouer les droits d'Odoo : quelqu'un qui n'a pas accès à
        # cette piste ne doit pas pouvoir écrire dans son fil par le détour
        # d'un appel. Le contrôleur, lui, passe en sudo parce qu'il n'a
        # justement aucun utilisateur derrière.
        cible.message_post(
            body=texte,
            message_type='comment',
            subtype_xmlid='mail.mt_note',
        )
        return {'type': 'ir.actions.act_window_close'}
