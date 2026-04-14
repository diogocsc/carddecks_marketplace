# -*- coding: utf-8 -*-

from odoo import api, fields, models


class CardDeckDeckMarketplace(models.Model):
    _inherit = "carddecks.deck"

    marketplace_for_sale = fields.Boolean(string="For Sale", default=False)
    marketplace_price = fields.Float(string="Marketplace Price", digits="Product Price")
    marketplace_currency_id = fields.Many2one(
        "res.currency",
        string="Marketplace Currency",
        default=lambda self: self.env.company.currency_id,
    )
    marketplace_commission_percent = fields.Float(
        string="Commission (%)",
        help="If set, overrides the global commission percent for this deck.",
    )
    marketplace_active = fields.Boolean(string="Marketplace Active", default=True)

    marketplace_is_available = fields.Boolean(
        string="Marketplace Available",
        compute="_compute_marketplace_is_available",
        store=True,
    )

    @api.depends("marketplace_for_sale", "marketplace_active", "is_public", "approval_status", "marketplace_price")
    def _compute_marketplace_is_available(self):
        for deck in self:
            deck.marketplace_is_available = bool(
                deck.marketplace_for_sale
                and deck.marketplace_active
                and deck.is_public
                and deck.approval_status == "approved"
                and (deck.marketplace_price or 0.0) > 0.0
            )

    def _marketplace_user_has_entitlement(self, user):
        self.ensure_one()
        if not user or user._is_public():
            return False
        return bool(
            self.env["carddecks_marketplace.entitlement"]
            .sudo()
            .search_count([("deck_id", "=", self.id), ("user_id", "=", user.id), ("active", "=", True)])
        )

    def can_user_access(self, user=None):
        """
        Extends subscription_plans' access control:
        - if deck is being sold on marketplace, access requires entitlement (or creator/admin)
        - otherwise, fall back to original subscription logic
        """
        self.ensure_one()
        user = user or self.env.user

        if self.marketplace_is_available:
            if user._is_public():
                return False
            if self.creator_user_id and self.creator_user_id.id == user.id:
                return True
            if user.has_group("base.group_system"):
                return True
            return self._marketplace_user_has_entitlement(user)

        return super().can_user_access(user=user)

    def can_user_play(self, user=None):
        self.ensure_one()
        user = user or self.env.user
        return self.can_user_access(user) and self.approval_status == "approved"

    @api.model
    def get_accessible_decks(self, user=None, deck_type=None, limit=None):
        """
        Extend subscription_plans filtering so that any authenticated user (free or premium)
        can browse marketplace decks that are available for sale.
        """
        user = user or self.env.user
        decks = super().get_accessible_decks(user=user, deck_type=deck_type, limit=limit)

        # Only show marketplace sale decks to authenticated users (not public visitors)
        if user and not user._is_public():
            marketplace_domain = [
                ("is_public", "=", True),
                ("marketplace_is_available", "=", True),
            ]
            marketplace_decks = self.search(marketplace_domain, order="play_count desc")
            decks = (decks | marketplace_decks)

        if limit:
            return decks[: int(limit)]
        return decks

