# -*- coding: utf-8 -*-

import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class DeckSellerAccount(models.Model):
    _name = "carddecks_marketplace.seller"
    _description = "Deck Marketplace Seller"
    _order = "create_date desc"

    user_id = fields.Many2one("res.users", required=True, ondelete="cascade", index=True)

    stripe_account_id = fields.Char(string="Stripe Connect Account ID", index=True)
    onboarding_state = fields.Selection(
        [("not_started", "Not Started"), ("pending", "Pending"), ("complete", "Complete"), ("disabled", "Disabled")],
        default="not_started",
        required=True,
    )
    charges_enabled = fields.Boolean()
    payouts_enabled = fields.Boolean()
    details_submitted = fields.Boolean()

    last_stripe_sync = fields.Datetime()

    _sql_constraints = [
        ("seller_user_unique", "unique(user_id)", "A seller record already exists for this user."),
    ]

    @api.model
    def get_or_create_for_user(self, user):
        seller = self.search([("user_id", "=", user.id)], limit=1)
        if seller:
            return seller
        return self.create({"user_id": user.id})

