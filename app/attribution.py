"""Attribution des retours — le moteur du paiement au résultat.

Principe : un client relancé qui repasse en caisse dans la fenêtre d'attribution
(par défaut 30 jours après l'envoi) est compté comme « retour récupéré ». C'est ce
retour qui est facturable en mode « payez au résultat ».

La détection du retour s'appuie sur la date de dernière visite fournie par la caisse
(POS). En dev, on peut la simuler. Règles :
- une seule conversion par client (pas de double facturation) ;
- la visite doit être postérieure à l'envoi et dans la fenêtre ;
- on attribue à l'envoi qualifiant le plus ancien.
"""
from __future__ import annotations

from datetime import date, datetime

from . import db, plans
from .logging_config import get_logger
from .models import Customer, Restaurant

logger = get_logger(__name__)

ATTRIBUTION_WINDOW_DAYS = 30


def run_attribution(
    restaurant: Restaurant,
    customers: list[Customer],
    window_days: int = ATTRIBUTION_WINDOW_DAYS,
    today: date | None = None,
) -> dict:
    """Détecte et enregistre les retours attribuables. Renvoie un résumé."""
    last_visit = {c.id: c.last_visit for c in customers}
    already = db.get_converted_customer_ids(restaurant.id)
    newly: set[str] = set()

    for send in db.get_unconverted_sends(restaurant.id):
        cid = send["customer_id"]
        if cid in already or cid in newly:
            continue
        visit = last_visit.get(cid)
        if visit is None:
            continue
        sent_day = datetime.fromisoformat(send["sent_at"]).date()
        delta = (visit - sent_day).days
        if 0 < delta <= window_days:
            db.mark_converted(send["id"], visit.isoformat(), restaurant.avg_ticket)
            newly.add(cid)

    if newly:
        logger.info("Attribution %s : %d retour(s) récupéré(s).", restaurant.id, len(newly))
    return {"new_conversions": len(newly)}


def billing_summary(restaurant: Restaurant) -> dict:
    """Montant facturable au résultat, selon les deux modèles (par client / %)."""
    stats = db.conversion_stats(restaurant.id)
    per_client = round(stats["recovered"] * plans.OUTCOME["per_client"], 2)
    pct = round(stats["recovered_revenue"] * plans.OUTCOME["pct_revenue"], 2)
    return {
        "recovered": stats["recovered"],
        "recovered_revenue": stats["recovered_revenue"],
        "due_per_client": per_client,
        "due_pct_revenue": pct,
    }
