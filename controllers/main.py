# -*- coding: utf-8 -*-

import json
import logging

import stripe

from odoo import http, fields
from odoo.http import request
from odoo.exceptions import AccessError

_logger = logging.getLogger(__name__)


class CardDecksMarketplaceController(http.Controller):
    def _stripe_config(self):
        # Reuse subscription_plans Stripe configuration
        return request.env["stripe.payment"].sudo().get_stripe_config()

    def _commission_percent(self, deck):
        deck.ensure_one()
        if (deck.marketplace_commission_percent or 0.0) > 0.0:
            return float(deck.marketplace_commission_percent)
        icp = request.env["ir.config_parameter"].sudo()
        return float(icp.get_param("carddecks_marketplace.commission_percent", "10.0"))

    def _creator_seller(self, user):
        Seller = request.env["carddecks_marketplace.seller"].sudo()
        seller = Seller.get_or_create_for_user(user)
        return seller

    @http.route("/seller/onboard", type="http", auth="user", website=True)
    def seller_onboard(self, **kwargs):
        user = request.env.user
        if user._is_public():
            return request.redirect("/web/login?redirect=/seller/onboard")

        config = self._stripe_config()
        stripe.api_key = config["secret_key"]

        seller = self._creator_seller(user)

        if not seller.stripe_account_id:
            acct = stripe.Account.create(
                type="express",
                email=user.email or None,
                metadata={"odoo_user_id": user.id, "odoo_db": request.env.cr.dbname},
            )
            seller.write(
                {
                    "stripe_account_id": acct["id"],
                    "onboarding_state": "pending",
                    "last_stripe_sync": fields.Datetime.now(),
                }
            )

        refresh_url = request.httprequest.host_url.rstrip("/") + "/seller/onboard"
        return_url = request.httprequest.host_url.rstrip("/") + "/seller/onboard/return"
        link = stripe.AccountLink.create(
            account=seller.stripe_account_id,
            refresh_url=refresh_url,
            return_url=return_url,
            type="account_onboarding",
        )
        return request.redirect(link["url"])

    @http.route("/seller/onboard/return", type="http", auth="user", website=True)
    def seller_onboard_return(self, **kwargs):
        user = request.env.user
        if user._is_public():
            return request.redirect("/web/login?redirect=/seller/onboard/return")

        config = self._stripe_config()
        stripe.api_key = config["secret_key"]
        seller = self._creator_seller(user)

        if seller.stripe_account_id:
            acct = stripe.Account.retrieve(seller.stripe_account_id)
            seller.write(
                {
                    "charges_enabled": bool(acct.get("charges_enabled")),
                    "payouts_enabled": bool(acct.get("payouts_enabled")),
                    "details_submitted": bool(acct.get("details_submitted")),
                    "onboarding_state": "complete"
                    if acct.get("charges_enabled") and acct.get("payouts_enabled")
                    else "pending",
                    "last_stripe_sync": fields.Datetime.now(),
                }
            )

        return request.redirect("/my/decks")

    @http.route("/deck/<int:deck_id>/buy", type="http", auth="user", website=True)
    def buy_deck_page(self, deck_id, **kwargs):
        deck = request.env["carddecks.deck"].sudo().browse(deck_id)
        if not deck.exists():
            return request.not_found()
        if not deck.marketplace_is_available:
            return request.redirect(f"/deck/{deck_id}")

        seller_user = deck.creator_user_id
        if seller_user and seller_user.id == request.env.user.id:
            return request.redirect(f"/deck/{deck_id}")

        seller = request.env["carddecks_marketplace.seller"].sudo().search([("user_id", "=", seller_user.id)], limit=1)
        return request.render(
            "carddecks_marketplace.buy_page",
            {
                "deck": deck,
                "seller": seller,
            },
        )

    @http.route("/marketplace/payment_intent/create", type="json", auth="user", methods=["POST"])
    def create_deck_payment_intent(self, deck_id, **kwargs):
        user = request.env.user
        deck = request.env["carddecks.deck"].sudo().browse(int(deck_id))
        if not deck.exists() or not deck.marketplace_is_available:
            return {"success": False, "error": "Deck not available for sale"}
        if deck.creator_user_id and deck.creator_user_id.id == user.id:
            return {"success": False, "error": "You already own this deck"}

        # Ensure seller is onboarded
        seller_user = deck.creator_user_id
        seller = request.env["carddecks_marketplace.seller"].sudo().search([("user_id", "=", seller_user.id)], limit=1)
        if not seller or not seller.stripe_account_id:
            return {"success": False, "error": "Seller is not onboarded"}

        config = self._stripe_config()
        stripe.api_key = config["secret_key"]

        commission_percent = self._commission_percent(deck)
        amount_total = float(deck.marketplace_price)
        currency = (deck.marketplace_currency_id or request.env.company.currency_id).name.lower()

        amount_cents = int(round(amount_total * 100))
        fee_cents = int(round(amount_cents * (commission_percent / 100.0)))
        seller_cents = max(amount_cents - fee_cents, 0)

        if amount_cents <= 0 or seller_cents <= 0:
            return {"success": False, "error": "Invalid pricing configuration"}

        Purchase = request.env["carddecks_marketplace.purchase"].sudo()
        purchase = Purchase.create(
            {
                "deck_id": deck.id,
                "buyer_user_id": user.id,
                "seller_user_id": seller_user.id,
                "currency_id": deck.marketplace_currency_id.id,
                "amount_total": amount_total,
                "amount_commission": float(fee_cents / 100.0),
                "amount_seller": float(seller_cents / 100.0),
                "commission_percent": commission_percent,
                "state": "processing",
            }
        )

        intent = stripe.PaymentIntent.create(
            amount=amount_cents,
            currency=currency,
            automatic_payment_methods={"enabled": True},
            metadata={
                "odoo_db": request.env.cr.dbname,
                "purchase_id": purchase.id,
                "deck_id": deck.id,
                "buyer_user_id": user.id,
                "seller_user_id": seller_user.id,
            },
            application_fee_amount=fee_cents,
            transfer_data={"destination": seller.stripe_account_id},
        )

        purchase.write({"stripe_payment_intent_id": intent["id"]})

        return {"success": True, "client_secret": intent["client_secret"], "payment_intent_id": intent["id"]}

    @http.route("/marketplace/payment_intent/confirm", type="json", auth="user", methods=["POST"])
    def confirm_deck_payment(self, payment_intent_id, **kwargs):
        config = self._stripe_config()
        stripe.api_key = config["secret_key"]

        intent = stripe.PaymentIntent.retrieve(payment_intent_id)
        purchase = request.env["carddecks_marketplace.purchase"].sudo().find_by_intent(payment_intent_id)
        if not purchase:
            return {"success": False, "error": "Purchase not found"}
        if purchase.buyer_user_id.id != request.env.user.id:
            raise AccessError("Not your purchase")

        if intent["status"] == "succeeded":
            purchase.write({"state": "succeeded"})
            request.env["carddecks_marketplace.entitlement"].sudo().create(
                {
                    "deck_id": purchase.deck_id.id,
                    "user_id": purchase.buyer_user_id.id,
                    "purchase_id": purchase.id,
                    "active": True,
                }
            )
            return {"success": True, "redirect_url": f"/deck/{purchase.deck_id.id}/play"}

        return {"success": False, "error": f"Payment not completed: {intent['status']}"}

    @http.route("/marketplace/stripe/webhook", type="http", auth="public", methods=["POST"], csrf=False)
    def stripe_webhook(self, **kwargs):
        config = self._stripe_config()
        stripe.api_key = config["secret_key"]

        webhook_secret = config.get("webhook_secret")
        if not webhook_secret:
            return request.make_response("Webhook secret not configured", status=400)

        payload = request.httprequest.data
        sig_header = request.httprequest.headers.get("Stripe-Signature")

        try:
            event = stripe.Webhook.construct_event(payload, sig_header, webhook_secret)
        except Exception as e:
            _logger.error("Webhook error: %s", str(e))
            return request.make_response("Invalid webhook", status=400)

        event_type = event.get("type")
        obj = event.get("data", {}).get("object", {}) or {}
        pi_id = obj.get("id")

        if event_type in ("payment_intent.succeeded", "payment_intent.payment_failed") and pi_id:
            purchase = request.env["carddecks_marketplace.purchase"].sudo().find_by_intent(pi_id)
            if purchase:
                if event_type == "payment_intent.succeeded":
                    purchase.write({"state": "succeeded"})
                    # idempotent: unique constraint prevents duplicates
                    try:
                        request.env["carddecks_marketplace.entitlement"].sudo().create(
                            {"deck_id": purchase.deck_id.id, "user_id": purchase.buyer_user_id.id, "purchase_id": purchase.id}
                        )
                    except Exception:
                        pass
                else:
                    purchase.write({"state": "failed"})

        return request.make_response("OK", status=200)

