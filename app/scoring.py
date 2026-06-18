"""Score de priorité RFM (Recency, Frequency, Monetary) — fonctionnalité signature.

Pour chaque client endormi, on calcule un score 0-100 qui combine :
- la valeur du client (combien il dépense, à quelle fréquence il vient),
- l'urgence (un client parti récemment se récupère mieux qu'un client parti depuis 6 mois).

Résultat : le restaurateur relance d'abord ceux qui rapportent le plus et sont
encore récupérables. C'est ce qui distingue Revoilà d'une simple relance de masse.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from .models import Customer, Restaurant


@dataclass
class Score:
    value: int        # priorité globale 0-100
    segment: str      # "VIP", "Habitué", "Occasionnel"
    recency_days: int
    recoverable: bool  # encore dans une fenêtre où la relance marche bien


def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def score_customer(
    customer: Customer, restaurant: Restaurant, today: date | None = None
) -> Score:
    days = customer.days_since_last_visit(today)

    # Urgence : 1.0 juste après le seuil, décroît jusqu'à ~0 après +90 jours.
    extra = days - restaurant.winback_days
    recency_factor = _clamp(1.0 - extra / 90.0)

    # Valeur : fréquence (plafonnée à 10 visites) + montant (plafonné à 10 tickets moyens).
    freq_factor = _clamp(customer.visits / 10.0)
    avg_ticket = max(restaurant.avg_ticket, 1.0)
    mon_factor = _clamp(customer.total_spent / (avg_ticket * 10.0))
    value_factor = 0.6 * mon_factor + 0.4 * freq_factor

    score = round(100 * (0.7 * value_factor + 0.3 * recency_factor))

    if value_factor >= 0.6:
        segment = "VIP"
    elif value_factor >= 0.3:
        segment = "Habitué"
    else:
        segment = "Occasionnel"

    return Score(
        value=score,
        segment=segment,
        recency_days=days,
        recoverable=days <= restaurant.winback_days * 3,
    )


def prioritize(
    customers: list[Customer], restaurant: Restaurant, today: date | None = None
) -> list[tuple[Customer, Score]]:
    """Trie les clients par score décroissant (les plus rentables d'abord)."""
    scored = [(c, score_customer(c, restaurant, today)) for c in customers]
    scored.sort(key=lambda pair: pair[1].value, reverse=True)
    return scored
