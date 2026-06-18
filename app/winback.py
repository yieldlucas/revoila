"""Logique métier : déterminer quels clients relancer."""
from __future__ import annotations

from datetime import date, datetime, timedelta

from .models import Customer, MessageLog, Restaurant


def is_lapsed(
    customer: Customer,
    restaurant: Restaurant,
    today: date | None = None,
    opt_outs: set[str] | None = None,
) -> bool:
    """Un client est 'endormi' s'il a assez d'historique mais n'est pas revenu.

    L'opt-out (désinscription RGPD) et le consentement marketing priment sur tout.
    """
    opt_outs = opt_outs or set()
    if customer.id in opt_outs:
        return False
    if not customer.marketing_opt_in:
        return False
    if customer.visits < restaurant.min_visits:
        return False
    return customer.days_since_last_visit(today) >= restaurant.winback_days


def recently_contacted(
    customer: Customer,
    restaurant: Restaurant,
    logs: list[MessageLog],
) -> bool:
    """Anti-spam : a-t-on déjà relancé ce client récemment ?"""
    cutoff = datetime.utcnow() - timedelta(days=restaurant.cooldown_days)
    return any(
        log.customer_id == customer.id and log.sent_at >= cutoff
        for log in logs
    )


def find_lapsed_customers(
    customers: list[Customer],
    restaurant: Restaurant,
    logs: list[MessageLog] | None = None,
    opt_outs: set[str] | None = None,
    today: date | None = None,
    exclude_ids: set[str] | None = None,
    annual_cap: int | None = None,
) -> list[Customer]:
    """Liste des clients à relancer : endormis, non désinscrits, anti-spam appliqué.

    L'anti-spam est précalculé en un seul passage sur les logs (O(n+m)) plutôt que
    de rescanner les logs pour chaque client.

    - `exclude_ids` : clients à ne jamais relancer (liste d'exclusion, Pro).
    - `annual_cap` : si fourni, exclut les clients déjà relancés `annual_cap` fois
      ou plus sur les 365 derniers jours (plafond de fréquence, Pro).
    """
    logs = logs or []
    opt_outs = opt_outs or set()
    exclude_ids = exclude_ids or set()

    now = datetime.utcnow()
    cutoff = now - timedelta(days=restaurant.cooldown_days)
    recent_ids = {log.customer_id for log in logs if log.sent_at >= cutoff}

    capped_ids: set[str] = set()
    if annual_cap is not None:
        year_ago = now - timedelta(days=365)
        counts: dict[str, int] = {}
        for log in logs:
            if log.sent_at >= year_ago:
                counts[log.customer_id] = counts.get(log.customer_id, 0) + 1
        capped_ids = {cid for cid, n in counts.items() if n >= annual_cap}

    blocked = recent_ids | capped_ids | exclude_ids
    return [
        c for c in customers
        if c.id not in blocked and is_lapsed(c, restaurant, today, opt_outs)
    ]


def estimate_recovered_revenue(
    targeted: list[Customer],
    restaurant: Restaurant,
) -> dict[str, float]:
    """Estimation simple du revenu récupérable, pour le dashboard."""
    expected_returns = len(targeted) * restaurant.winback_conversion
    revenue = expected_returns * restaurant.avg_ticket
    return {
        "targeted": len(targeted),
        "expected_returns": round(expected_returns, 1),
        "estimated_revenue": round(revenue, 2),
    }
