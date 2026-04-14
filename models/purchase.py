# -*- coding: utf-8 -*-

from odoo import api, fields, models


class DeckPurchase(models.Model):
    _name = "carddecks_marketplace.purchase"
    _description = "Deck Purchase"
    _order = "create_date desc"

    deck_id = fields.Many2one("carddecks.deck", required=True, ondelete="cascade", index=True)
    buyer_user_id = fields.Many2one("res.users", required=True, ondelete="cascade", index=True)
    seller_user_id = fields.Many2one("res.users", required=True, ondelete="restrict", index=True)

    currency_id = fields.Many2one("res.currency", required=True)
    amount_total = fields.Float(digits="Product Price", required=True)
    amount_commission = fields.Float(digits="Product Price", required=True)
    amount_seller = fields.Float(digits="Product Price", required=True)
    commission_percent = fields.Float(required=True)

    stripe_payment_intent_id = fields.Char(index=True)

    state = fields.Selection(
        [
            ("requires_payment", "Requires Payment"),
            ("processing", "Processing"),
            ("succeeded", "Succeeded"),
            ("failed", "Failed"),
            ("refunded", "Refunded"),
            ("cancelled", "Cancelled"),
        ],
        default="requires_payment",
        required=True,
        index=True,
    )

    @api.model
    def find_by_intent(self, payment_intent_id):
        return self.search([("stripe_payment_intent_id", "=", payment_intent_id)], limit=1)


class DeckEntitlement(models.Model):
    _name = "carddecks_marketplace.entitlement"
    _description = "Deck Entitlement"
    _order = "create_date desc"

    deck_id = fields.Many2one("carddecks.deck", required=True, ondelete="cascade", index=True)
    user_id = fields.Many2one("res.users", required=True, ondelete="cascade", index=True)
    purchase_id = fields.Many2one("carddecks_marketplace.purchase", ondelete="set null")

    active = fields.Boolean(default=True, index=True)

    _sql_constraints = [
        ("entitlement_unique", "unique(deck_id, user_id)", "User already owns this deck."),
    ]

