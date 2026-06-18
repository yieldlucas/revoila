"""Configuration centrale, lue depuis les variables d'environnement (.env).

Les valeurs ici servent de DÉFAUTS globaux. Chaque restaurant peut surcharger
ses propres seuils dans data/restaurants.json (voir app/restaurants.py).
"""
import os

from dotenv import load_dotenv

load_dotenv()


def _int(name: str, default: int) -> int:
    return int(os.getenv(name, default))


def _float(name: str, default: float) -> float:
    return float(os.getenv(name, default))


def _bool(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).strip().lower() in ("1", "true", "yes", "oui")


# Règles métier (défauts ; surchargées par restaurant)
WINBACK_DAYS = _int("WINBACK_DAYS", 45)
MIN_VISITS = _int("MIN_VISITS", 2)
COOLDOWN_DAYS = _int("COOLDOWN_DAYS", 30)

# Estimation ROI (défauts)
AVG_TICKET = _float("AVG_TICKET", 35.0)
WINBACK_CONVERSION = _float("WINBACK_CONVERSION", 0.15)

# IA (vide => mode template, aucun appel API)
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "").strip()

# --- Envois ---
# DRY_RUN=True => on logge sans rien envoyer (sécurité par défaut).
DRY_RUN = _bool("DRY_RUN", True)

# Email (Brevo / ex-Sendinblue)
BREVO_API_KEY = os.getenv("BREVO_API_KEY", "").strip()
EMAIL_FROM = os.getenv("EMAIL_FROM", "contact@example.com")
EMAIL_FROM_NAME = os.getenv("EMAIL_FROM_NAME", "Restaurant")

# SMS ("brevo", "twilio" ou "none")
SMS_PROVIDER = os.getenv("SMS_PROVIDER", "none").strip().lower()
SMS_SENDER = os.getenv("SMS_SENDER", "Resto")
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID", "").strip()
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "").strip()
TWILIO_FROM = os.getenv("TWILIO_FROM", "").strip()

# URL publique de base (pour les liens de désinscription)
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "http://localhost:8000")

# Adresse qui reçoit une notification à chaque inscription waitlist (capture durable).
WAITLIST_NOTIFY_EMAIL = os.getenv("WAITLIST_NOTIFY_EMAIL", "").strip()

# --- Facturation (Stripe) ---
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "").strip()
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "").strip()
# IDs de prix Stripe (créés dans le dashboard Stripe). Ex. price_xxx.
STRIPE_PRICE_STANDARD = os.getenv("STRIPE_PRICE_STANDARD", "").strip()
STRIPE_PRICE_PRO = os.getenv("STRIPE_PRICE_PRO", "").strip()
TRIAL_DAYS = _int("TRIAL_DAYS", 14)

# --- Base de données ---
# Vide => SQLite local (dev). Sinon URL Postgres (prod), ex. postgresql://...
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
