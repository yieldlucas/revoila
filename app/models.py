"""Modèles de données."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime

from . import config


@dataclass
class Restaurant:
    id: str
    name: str
    tone: str
    dashboard_token: str
    plan: str = "pro"  # plan unique (l'accès réel dépend du statut d'abonnement)
    winback_days: int = config.WINBACK_DAYS
    min_visits: int = config.MIN_VISITS
    cooldown_days: int = config.COOLDOWN_DAYS
    avg_ticket: float = config.AVG_TICKET
    winback_conversion: float = config.WINBACK_CONVERSION

    @staticmethod
    def from_dict(d: dict) -> Restaurant:
        return Restaurant(
            id=d["id"],
            name=d["name"],
            tone=d.get("tone", "chaleureux et convivial"),
            dashboard_token=d.get("dashboard_token", ""),
            plan=d.get("plan", "pro"),
            winback_days=int(d.get("winback_days", config.WINBACK_DAYS)),
            min_visits=int(d.get("min_visits", config.MIN_VISITS)),
            cooldown_days=int(d.get("cooldown_days", config.COOLDOWN_DAYS)),
            avg_ticket=float(d.get("avg_ticket", config.AVG_TICKET)),
            winback_conversion=float(d.get("winback_conversion", config.WINBACK_CONVERSION)),
        )

    @property
    def is_pro(self) -> bool:
        return self.plan == "pro"


@dataclass
class Customer:
    id: str
    restaurant_id: str
    first_name: str
    email: str | None
    phone: str | None
    marketing_opt_in: bool
    visits: int
    last_visit: date
    favorite_dish: str | None
    total_spent: float

    @staticmethod
    def from_dict(d: dict) -> Customer:
        return Customer(
            id=d["id"],
            restaurant_id=d.get("restaurant_id", ""),
            first_name=d["first_name"],
            email=d.get("email"),
            phone=d.get("phone"),
            marketing_opt_in=bool(d.get("marketing_opt_in", False)),
            visits=int(d.get("visits", 0)),
            last_visit=date.fromisoformat(d["last_visit"]),
            favorite_dish=d.get("favorite_dish"),
            total_spent=float(d.get("total_spent", 0.0)),
        )

    def days_since_last_visit(self, today: date | None = None) -> int:
        today = today or date.today()
        return (today - self.last_visit).days

    @property
    def preferred_channel(self) -> str:
        return "sms" if self.phone else "email"


@dataclass
class MessageLog:
    restaurant_id: str
    customer_id: str
    channel: str
    content: str
    status: str  # "logged" (dry-run), "sent", "failed"
    sent_at: datetime = field(default_factory=datetime.utcnow)
    id: int | None = None
    converted_at: str | None = None  # date du retour attribué (paiement au résultat)
