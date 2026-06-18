"""Cycle automatique : détecte les clients endormis et envoie les relances.

Multi-tenant : un cycle par restaurant. Envois persistés en SQLite (app/db.py).
"""
from __future__ import annotations

from datetime import date

from apscheduler.schedulers.background import BackgroundScheduler

from . import attribution, billing, db, plans, scoring
from .data_source import get_default_source
from .logging_config import get_logger
from .messaging import generate_message, send_message
from .models import Restaurant
from .restaurants import get_all_restaurants, get_restaurant
from .winback import find_lapsed_customers

logger = get_logger(__name__)


def run_cycle_for(restaurant: Restaurant) -> dict:
    """Un cycle complet de win-back pour un restaurant. Renvoie un résumé."""
    db.init_db()

    # Pas d'abonnement actif => on ne déclenche rien.
    if not billing.is_active(restaurant.id):
        logger.info("Cycle %s ignoré : abonnement inactif.", restaurant.id)
        return {
            "restaurant_id": restaurant.id,
            "detected": 0,
            "sent": 0,
            "skipped": "inactive_subscription",
        }

    source = get_default_source()
    customers = source.get_customers(restaurant.id)

    # Attribution : a-t-on des clients revenus après une relance ? (paiement au résultat)
    attribution.run_attribution(restaurant, customers)

    logs = db.get_logs(restaurant.id)          # pour l'anti-spam
    opt_outs = db.get_opt_outs(restaurant.id)  # désinscriptions RGPD

    targets = find_lapsed_customers(customers, restaurant, logs=logs, opt_outs=opt_outs)

    # Pro : on relance d'abord les clients les plus rentables (priorisation RFM).
    if plans.features(restaurant.plan)["prioritized"]:
        targets = [c for c, _ in scoring.prioritize(targets, restaurant)]

    # Free : quota mensuel de relances (entonnoir d'upgrade).
    capped = False
    cap = plans.monthly_cap(restaurant.plan)
    if cap is not None:
        first_of_month = date.today().replace(day=1).isoformat()
        used = db.count_logs_since(restaurant.id, first_of_month)
        remaining = max(0, cap - used)
        if len(targets) > remaining:
            targets = targets[:remaining]
            capped = True

    sent = 0
    for customer in targets:
        content = generate_message(customer, restaurant)
        log = send_message(customer, restaurant, content)
        db.add_log(log)
        sent += 1

    summary = {
        "restaurant_id": restaurant.id,
        "detected": len(targets),
        "sent": sent,
        "total_logged": db.count_logs(restaurant.id),
    }
    if capped:
        summary["capped"] = f"quota Free ({cap}/mois) atteint"
    logger.info("Cycle %s : %s", restaurant.id, summary)
    return summary


def run_cycle(restaurant_id: str) -> dict:
    restaurant = get_restaurant(restaurant_id)
    if restaurant is None:
        raise ValueError(f"Restaurant inconnu : {restaurant_id}")
    return run_cycle_for(restaurant)


def run_all() -> list[dict]:
    """Lance le cycle pour tous les restaurants (utilisé par le scheduler)."""
    return [run_cycle_for(r) for r in get_all_restaurants()]


def start_scheduler() -> BackgroundScheduler:
    """Lance le cycle automatiquement une fois par jour, pour tous les restaurants."""
    db.init_db()
    scheduler = BackgroundScheduler()
    scheduler.add_job(run_all, "interval", days=1, id="winback_daily")
    scheduler.start()
    logger.info("Scheduler démarré : cycle win-back quotidien (tous restaurants).")
    return scheduler
