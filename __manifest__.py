# -*- coding: utf-8 -*-
{
    "name": "Card Decks Marketplace",
    "version": "16.0.0.0.1",
    "author": "Diogo Cordeiro",
    "summary": "Sell decks via Stripe Connect with platform commission",
    "category": "Website",
    "depends": [
        "website",
        "portal",
        "carddecks",
        "carddecks_game",
        "subscription_plans",
    ],
    "data": [
        "security/ir.model.access.csv",
        "security/rules.xml",
        "views/website_templates.xml",
    ],
    "assets": {
        "web.assets_frontend": [
            "carddecks_marketplace/static/src/css/marketplace.css",
            "carddecks_marketplace/static/src/js/marketplace_checkout.js",
        ],
    },
    "installable": True,
    "application": False,
    "license": "LGPL-3",
}

