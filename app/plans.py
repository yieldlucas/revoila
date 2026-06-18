"""Plans tarifaires et fonctionnalités associées (gating Free / Standard / Pro).

Échelle de prix (décidée pour amorcer puis monter en gamme) :
- Free (0 €)      : relance email, anti-spam, RGPD. Pour entrer sans friction.
- Standard (49 €) : + SMS multi-canal. Le palier d'entrée payant.
- Pro (149 €)     : + l'intelligence (score RFM, segments, messages sur-mesure,
                    relance priorisée). C'est le cœur de la valeur.

Alternative : paiement au résultat (outcome) — le client ne paie qu'en fonction
des clients réellement réactivés. Argument de vente le plus fort au démarrage.
"""
from __future__ import annotations

PLAN_FEATURES: dict[str, dict] = {
    "free": {
        "label": "Free",
        "channels": ("email",),
        "scoring": False,
        "segments": False,
        "smart_message": False,
        "prioritized": False,
        "monthly_cap": 10,   # entonnoir : 10 relances/mois max
        "price": "0 €",
    },
    "standard": {
        "label": "Standard",
        "channels": ("sms", "email"),
        "scoring": False,
        "segments": False,
        "smart_message": False,
        "prioritized": False,
        "monthly_cap": None,  # illimité
        "price": "49 €/mois",
    },
    "pro": {
        "label": "Pro",
        "channels": ("sms", "email"),
        "scoring": True,
        "segments": True,
        "smart_message": True,
        "prioritized": True,
        "monthly_cap": None,
        "price": "149 €/mois",
    },
}

# Ordre des plans (pour proposer uniquement les montées en gamme).
RANK = {"free": 0, "standard": 1, "pro": 2}

# Cartes de prix affichées comme options de montée en gamme.
PRICING = [
    {
        "id": "standard",
        "name": "Standard",
        "price": "49 €/mois",
        "line": "Relance automatique par email + SMS, multi-canal.",
    },
    {
        "id": "pro",
        "name": "Pro",
        "price": "149 €/mois",
        "line": "Score de priorité, segments, messages sur-mesure, relance priorisée.",
    },
]

# Paiement au résultat (alternative à l'abonnement).
OUTCOME = {
    "per_client": 5.0,         # € par client réactivé
    "pct_revenue": 0.08,       # ou 8 % du CA récupéré
    "label": "Payez au résultat",
}

# Arguments de vente affichés dans la bannière d'upsell (valeur du Pro).
PRO_HIGHLIGHTS = [
    ("Score de priorité", "On relance tous vos clients — en commençant par les plus précieux. Personne n'est oublié."),
    ("Segments clients", "VIP, Habitués, Occasionnels — détectés automatiquement."),
    ("Messages sur-mesure", "Le ton s'adapte au segment (un VIP n'est pas un client de passage)."),
    ("SMS + Email", "Multi-canal : on choisit le canal qui convertit le mieux."),
    ("Bon moment, bon ordre", "Vos meilleurs clients passent en tête de file, le reste suit."),
]


def features(plan: str) -> dict:
    return PLAN_FEATURES.get(plan, PLAN_FEATURES["free"])


def allows_sms(plan: str) -> bool:
    return "sms" in features(plan)["channels"]


def upgrades(plan: str) -> list[dict]:
    """Plans proposables au-dessus du plan courant (pour l'upsell)."""
    current = RANK.get(plan, 0)
    return [p for p in PRICING if RANK[p["id"]] > current]


def outcome_estimate(expected_returns: float) -> float:
    """Estimation du coût mensuel en mode 'paiement au résultat'."""
    return round(expected_returns * OUTCOME["per_client"], 2)


def monthly_cap(plan: str) -> int | None:
    """Quota mensuel de relances (None = illimité)."""
    return features(plan).get("monthly_cap")
