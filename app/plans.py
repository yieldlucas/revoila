"""Offre Revoilà — un seul abonnement + paiement au résultat.

Structure (simple, décidée après les premiers retours) :
- **Essai gratuit 14 jours** (géré côté facturation via le statut d'abonnement).
- **Abonnement Pro — 99 €/mois** : tout inclus, sans limite.
- **Au résultat** : alternative sans abonnement, ~5 €/client réellement réactivé.

Il n'y a donc qu'un seul plan applicatif (`pro`). L'accès est contrôlé par le
statut d'abonnement (essai / actif / expiré) dans `app/billing.py`, pas par des
paliers de fonctionnalités.
"""
from __future__ import annotations

PRO_PRICE = "99 €/mois"

PLAN_FEATURES: dict[str, dict] = {
    "pro": {
        "label": "Pro",
        "channels": ("sms", "email"),
        "scoring": True,
        "segments": True,
        "smart_message": True,
        "prioritized": True,
        "monthly_cap": None,       # pas de quota
        "manual_approval": True,    # valider/cocher avant envoi
        "targeting": True,          # cibler par segment / filtres / exclusion
        "frequency_cap": True,      # plafonds de fréquence renforcés
        "quiet_hours": True,        # pas d'envoi tard le soir / dimanche
        "price": PRO_PRICE,
    },
}

# Plafond annuel de relances par client (anti-sur-sollicitation).
ANNUAL_CAP_PER_CUSTOMER = 6
# Segments ciblables (mode validation manuelle).
SEGMENTS = ("VIP", "Habitué", "Occasionnel")
# Heures calmes : pas d'envoi avant/après ces heures, ni le dimanche (weekday 6).
QUIET_BEFORE_HOUR = 9
QUIET_AFTER_HOUR = 21

# Paiement au résultat (alternative à l'abonnement).
OUTCOME = {
    "per_client": 5.0,         # € par client réactivé
    "pct_revenue": 0.08,       # ou 8 % du CA récupéré
    "label": "Payez au résultat",
}

# Atouts mis en avant (essai → abonnement).
PRO_HIGHLIGHTS = [
    ("Validation avant envoi", "Vous cochez qui relancer — rien ne part sans votre accord. Ou laissez tourner en auto."),
    ("Ciblage fin", "Relancez seulement les VIP, les habitués, ou par filtres — et excluez qui vous voulez."),
    ("Score de priorité", "Vos meilleurs clients passent en premier. Personne n'est oublié."),
    ("Messages sur-mesure", "Le ton s'adapte au segment (un VIP n'est pas un client de passage)."),
    ("Anti-harcèlement renforcé", "Plafonds de fréquence + heures calmes : impossible de sur-solliciter."),
    ("SMS + Email", "Multi-canal : on choisit le canal qui convertit le mieux."),
]


def features(plan: str | None = None) -> dict:
    """Renvoie les fonctionnalités du plan (un seul plan : pro)."""
    return PLAN_FEATURES.get(plan or "pro", PLAN_FEATURES["pro"])


def allows_sms(plan: str | None = None) -> bool:
    return "sms" in features(plan)["channels"]


def has(plan: str | None, feature: str) -> bool:
    """Le plan débloque-t-il cette fonctionnalité ? (toujours vrai en plan unique)."""
    return bool(features(plan).get(feature, False))


def annual_cap(plan: str | None = None) -> int | None:
    return ANNUAL_CAP_PER_CUSTOMER if has(plan, "frequency_cap") else None


def monthly_cap(plan: str | None = None) -> int | None:
    return features(plan).get("monthly_cap")


def outcome_estimate(expected_returns: float) -> float:
    """Estimation du coût mensuel en mode 'paiement au résultat'."""
    return round(expected_returns * OUTCOME["per_client"], 2)


def in_quiet_hours(now) -> bool:
    """Vrai si on est en 'heures calmes' (tôt, tard, ou dimanche)."""
    return now.weekday() == 6 or now.hour < QUIET_BEFORE_HOUR or now.hour >= QUIET_AFTER_HOUR
