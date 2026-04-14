/** @odoo-module **/

// Minimal Stripe Elements checkout for deck purchases.

async function jsonRpc(route, params) {
  const resp = await fetch(route, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ jsonrpc: "2.0", method: "call", params, id: Date.now() }),
  });
  const data = await resp.json();
  if (data.error) throw new Error(data.error.data?.message || data.error.message || "RPC error");
  return data.result;
}

document.addEventListener("DOMContentLoaded", async () => {
  const form = document.getElementById("marketplace-checkout");
  if (!form) return;

  const deckId = form.getAttribute("data-deck-id");
  const statusEl = document.getElementById("payment-status");
  const payBtn = document.getElementById("pay-btn");

  const publishableKeyInput = document.getElementById("stripe-publishable-key");
  // Fallback: reuse same hidden input pattern as subscription_plans if present globally
  const publishableKey =
    publishableKeyInput?.value || window.ODOO_STRIPE_PUBLISHABLE_KEY || null;

  // If no publishable key is exposed, we can't proceed
  if (!publishableKey) {
    statusEl.style.display = "block";
    statusEl.className = "alert alert-danger";
    statusEl.textContent = "Stripe is not configured.";
    payBtn.disabled = true;
    return;
  }

  const stripe = Stripe(publishableKey);
  const elements = stripe.elements();
  const card = elements.create("card");
  card.mount("#card-element");

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    payBtn.disabled = true;

    try {
      const { success, client_secret, error } = await jsonRpc("/marketplace/payment_intent/create", {
        deck_id: deckId,
      });
      if (!success) throw new Error(error || "Failed to create payment intent");

      const cardholderName = document.getElementById("cardholder-name")?.value || "";
      const result = await stripe.confirmCardPayment(client_secret, {
        payment_method: {
          card,
          billing_details: { name: cardholderName },
        },
      });

      if (result.error) throw new Error(result.error.message);

      const intentId = result.paymentIntent?.id;
      const confirm = await jsonRpc("/marketplace/payment_intent/confirm", { payment_intent_id: intentId });
      if (confirm.success && confirm.redirect_url) {
        window.location.href = confirm.redirect_url;
        return;
      }
      throw new Error(confirm.error || "Payment confirmation failed");
    } catch (err) {
      statusEl.style.display = "block";
      statusEl.className = "alert alert-danger";
      statusEl.textContent = err.message || String(err);
      payBtn.disabled = false;
    }
  });
});

