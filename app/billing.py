"""Facturation par abonnement (Stripe), multi-tenant.

Logique :
- Chaque restaurant a un abonnement (table `subscription`) : trialing / active /
  past_due / canceled / suspended.
- `is_active()` décide si le restaurant peut déclencher des cycles.
- `create_checkout_session()` ouvre un paiement Stripe (essai gratuit inclus).
- `handle_webhook()` met à jour le statut selon les événements Stripe.

Aucune clé Stripe en dev => `is_active()` renvoie True (essai implicite) pour ne pas
bloquer le développement. Le code réel est protégé et n'appelle Stripe que si configuré.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta

from . import config, db
from .models import Restaurant

ACTIVE_STATUSES = ("active", "trialing")


# --------------------------------------------------------------------------
# État de l'abonnement
# --------------------------------------------------------------------------

def is_active(restaurant_id: str) -> bool:
    """Le restaurant peut-il déclencher des cycles ?"""
    sub = db.get_subscription(restaurant_id)
    if sub is None:
        return True  # essai implicite tant qu'aucune facturation n'est configurée
    status = sub.get("status")
    if status == "active":
        return True
    if status == "trialing":
        trial_end = sub.get("trial_end")
        if not trial_end:
            return True
        return datetime.utcnow() < datetime.fromisoformat(trial_end)
    return False


def status_label(restaurant_id: str) -> str:
    sub = db.get_subscription(restaurant_id)
    if sub is None:
        return "essai (non configuré)"
    return sub.get("status", "inconnu")


# Libellés et couleurs lisibles pour l'interface.
_BADGES = {
    "active": ("Actif", "#1a7f37"),
    "trialing": ("Essai", "#9a6700"),
    "past_due": ("Paiement en attente", "#b35900"),
    "canceled": ("Annulé", "#b42318"),
    "suspended": ("Suspendu", "#b42318"),
}


def subscription_view(restaurant_id: str) -> dict:
    """Vue prête pour l'UI : libellé, couleur, et si le service est actif."""
    sub = db.get_subscription(restaurant_id)
    active = is_active(restaurant_id)
    if sub is None:
        return {"label": "Essai (non configuré)", "color": "#9a6700", "active": active}
    status = sub.get("status", "inconnu")
    label, color = _BADGES.get(status, (status, "#666"))
    return {"label": label, "color": color, "active": active}


def start_trial(restaurant_id: str, days: int | None = None) -> None:
    days = days if days is not None else config.TRIAL_DAYS
    trial_end = (datetime.utcnow() + timedelta(days=days)).isoformat()
    db.upsert_subscription(restaurant_id, status="trialing", trial_end=trial_end)


# --------------------------------------------------------------------------
# Checkout Stripe
# --------------------------------------------------------------------------

def create_checkout_session(restaurant: Restaurant, tier: str = "standard") -> str:
    """Crée une session de paiement Stripe et renvoie son URL."""
    if not config.STRIPE_SECRET_KEY:
        raise RuntimeError("Stripe non configuré (STRIPE_SECRET_KEY manquante).")
    price_id = (
        config.STRIPE_PRICE_PRO if tier == "pro" else config.STRIPE_PRICE_STANDARD
    )
    if not price_id:
        raise RuntimeError(f"Price ID Stripe manquant pour le palier '{tier}'.")

    import stripe  # dépendance optionnelle

    stripe.api_key = config.STRIPE_SECRET_KEY
    base = config.PUBLIC_BASE_URL.rstrip("/")
    session = stripe.checkout.Session.create(
        mode="subscription",
        line_items=[{"price": price_id, "quantity": 1}],
        subscription_data={
            "trial_period_days": config.TRIAL_DAYS,
            "metadata": {"restaurant_id": restaurant.id},
        },
        metadata={"restaurant_id": restaurant.id},
        success_url=f"{base}/r/{restaurant.id}?token={restaurant.dashboard_token}",
        cancel_url=f"{base}/",
    )
    return session.url


# --------------------------------------------------------------------------
# Webhooks Stripe
# --------------------------------------------------------------------------

def handle_webhook(payload: bytes, sig_header: str = "") -> dict:
    """Vérifie (si secret configuré) puis traite un événement Stripe."""
    if config.STRIPE_WEBHOOK_SECRET:
        import stripe

        event = stripe.Webhook.construct_event(
            payload, sig_header, config.STRIPE_WEBHOOK_SECRET
        )
        event = dict(event)
    else:
        event = json.loads(payload)
    return process_event(event)


def process_event(event: dict) -> dict:
    """Met à jour l'abonnement selon le type d'événement. Testable directement."""
    etype = event.get("type")
    obj = event.get("data", {}).get("object", {})
    rid = (obj.get("metadata") or {}).get("restaurant_id")

    if etype in ("customer.subscription.created", "customer.subscription.updated"):
        if not rid:
            return {"ignored": etype}
        status = obj.get("status", "active")
        trial_end_epoch = obj.get("trial_end")
        trial_end = (
            datetime.utcfromtimestamp(trial_end_epoch).isoformat()
            if trial_end_epoch else None
        )
        db.upsert_subscription(
            rid, status=status, trial_end=trial_end,
            stripe_customer_id=obj.get("customer"),
            stripe_subscription_id=obj.get("id"),
        )
        return {"updated": rid, "status": status}

    if etype == "customer.subscription.deleted":
        if rid:
            db.upsert_subscription(rid, status="canceled")
        return {"canceled": rid}

    if etype == "checkout.session.completed":
        if rid:
            db.upsert_subscription(
                rid, status="active",
                stripe_customer_id=obj.get("customer"),
                stripe_subscription_id=obj.get("subscription"),
            )
        return {"activated": rid}

    if etype == "invoice.payment_failed":
        if rid:
            db.upsert_subscription(rid, status="past_due")
        return {"past_due": rid}

    return {"ignored": etype}
