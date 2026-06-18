"""Génération du message personnalisé + envoi (email / SMS).

Sécurité : si config.DRY_RUN est vrai (défaut), on logge sans rien envoyer.
Les vrais envois passent par Brevo (email + SMS) ou Twilio (SMS).
"""
from __future__ import annotations

from urllib.parse import urlencode

from . import config, plans
from .logging_config import get_logger
from .models import Customer, MessageLog, Restaurant
from .scoring import score_customer

logger = get_logger(__name__)


# --------------------------------------------------------------------------
# Choix du canal (gating par plan)
# --------------------------------------------------------------------------

def choose_channel(customer: Customer, restaurant: Restaurant) -> str:
    """SMS si le plan l'autorise et qu'un numéro existe, sinon email."""
    if customer.phone and plans.allows_sms(restaurant.plan):
        return "sms"
    return "email"


# --------------------------------------------------------------------------
# Génération du contenu
# --------------------------------------------------------------------------

def unsubscribe_link(customer: Customer) -> str:
    qs = urlencode({"restaurant_id": customer.restaurant_id, "customer_id": customer.id})
    return f"{config.PUBLIC_BASE_URL.rstrip('/')}/unsubscribe?{qs}"


def _template_message(customer: Customer, restaurant: Restaurant) -> str:
    """Message par défaut, sans appel IA. Toujours disponible.

    Pro : le ton s'adapte au segment du client (smart_message).
    """
    dish = (
        f" On garde votre {customer.favorite_dish.lower()} au chaud !"
        if customer.favorite_dish
        else ""
    )

    if plans.features(restaurant.plan)["smart_message"]:
        segment = score_customer(customer, restaurant).segment
        if segment == "VIP":
            return (
                f"Bonjour {customer.first_name}, vous faites partie de nos meilleurs "
                f"clients et vous nous manquez chez {restaurant.name} !{dish} "
                f"On vous réserve le meilleur accueil pour votre retour. 🍽️"
            )
        if segment == "Habitué":
            return (
                f"Bonjour {customer.first_name}, ça fait un moment chez "
                f"{restaurant.name} !{dish} On a hâte de vous revoir à votre table. 🍽️"
            )

    return (
        f"Bonjour {customer.first_name}, ça fait un moment qu'on ne vous a pas vu "
        f"chez {restaurant.name} !{dish} Au plaisir de vous revoir très vite. 🍽️"
    )


def _ai_message(customer: Customer, restaurant: Restaurant) -> str:
    """Message généré par Claude. Activé seulement si une clé API est fournie."""
    import anthropic  # dépendance optionnelle

    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    prompt = (
        f"Rédige un SMS court (max 320 caractères), ton {restaurant.tone}, "
        f"pour faire revenir un client d'un restaurant nommé {restaurant.name}. "
        f"Client : prénom {customer.first_name}, plat préféré "
        f"{customer.favorite_dish or 'inconnu'}, "
        f"{customer.days_since_last_visit()} jours sans venir. "
        f"Pas de lien, pas de code promo inventé. Renvoie uniquement le message."
    )
    resp = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=200,
        messages=[{"role": "user", "content": prompt}],
    )
    return resp.content[0].text.strip()


def generate_message(customer: Customer, restaurant: Restaurant) -> str:
    """IA si clé dispo, sinon template. Le template est toujours un filet de sécurité."""
    if config.ANTHROPIC_API_KEY:
        try:
            return _ai_message(customer, restaurant)
        except Exception as e:  # ne jamais bloquer le cycle pour un souci IA
            logger.warning("IA indisponible (%s); fallback template.", e)
    return _template_message(customer, restaurant)


# --------------------------------------------------------------------------
# Notification interne (capture durable de la waitlist)
# --------------------------------------------------------------------------

def notify_waitlist_signup(email: str, count: int) -> str:
    """Prévient le propriétaire d'un nouvel inscrit waitlist (via Brevo HTTP).

    Garantit qu'aucun email n'est perdu même si la base est éphémère.
    Renvoie un statut : 'skipped' / 'logged' (dry-run) / 'sent' / 'failed'.
    """
    to = config.WAITLIST_NOTIFY_EMAIL
    if not to:
        return "skipped"
    if config.DRY_RUN or not config.BREVO_API_KEY:
        logger.info("[waitlist] nouvel inscrit %s (total %s) → %s", email, count, to)
        return "logged"
    try:
        import requests
        resp = requests.post(
            "https://api.brevo.com/v3/smtp/email",
            headers={"api-key": config.BREVO_API_KEY, "Content-Type": "application/json"},
            json={
                "sender": {"name": "Revoilà", "email": config.EMAIL_FROM},
                "to": [{"email": to}],
                "subject": f"Nouvel inscrit waitlist Revoilà ({count})",
                "htmlContent": f"<p>Nouvel inscrit : <b>{email}</b></p><p>Total : {count}</p>",
            },
            timeout=15,
        )
        if resp.status_code >= 400:
            logger.warning("[waitlist] Brevo %s pour %s : %s",
                           resp.status_code, email, resp.text[:400])
            return "failed"
        return "sent"
    except Exception as e:
        logger.warning("[waitlist] notification échouée pour %s : %s", email, e)
        return "failed"


# --------------------------------------------------------------------------
# Envoi (providers réels)
# --------------------------------------------------------------------------

def _send_email(customer: Customer, restaurant: Restaurant, content: str) -> None:
    """Email transactionnel via Brevo. Lève une exception en cas d'échec."""
    import requests

    if not config.BREVO_API_KEY:
        raise RuntimeError("BREVO_API_KEY manquante.")

    html = (
        f"<p>{content}</p>"
        f'<p style="font-size:12px;color:#999">'
        f'Vous ne souhaitez plus recevoir ces messages ? '
        f'<a href="{unsubscribe_link(customer)}">Se désinscrire</a></p>'
    )
    resp = requests.post(
        "https://api.brevo.com/v3/smtp/email",
        headers={"api-key": config.BREVO_API_KEY, "Content-Type": "application/json"},
        json={
            "sender": {"name": restaurant.name, "email": config.EMAIL_FROM},
            "to": [{"email": customer.email, "name": customer.first_name}],
            "subject": f"Vous nous manquez chez {restaurant.name} !",
            "htmlContent": html,
        },
        timeout=15,
    )
    resp.raise_for_status()


def _send_sms(customer: Customer, restaurant: Restaurant, content: str) -> None:
    """SMS via Brevo ou Twilio selon config.SMS_PROVIDER. Lève une exception si échec."""
    import requests

    body = f"{content}\nSTOP : {unsubscribe_link(customer)}"

    if config.SMS_PROVIDER == "brevo":
        if not config.BREVO_API_KEY:
            raise RuntimeError("BREVO_API_KEY manquante.")
        resp = requests.post(
            "https://api.brevo.com/v3/transactionalSMS/sms",
            headers={"api-key": config.BREVO_API_KEY, "Content-Type": "application/json"},
            json={"sender": config.SMS_SENDER, "recipient": customer.phone, "content": body},
            timeout=15,
        )
        resp.raise_for_status()

    elif config.SMS_PROVIDER == "twilio":
        if not (config.TWILIO_ACCOUNT_SID and config.TWILIO_AUTH_TOKEN and config.TWILIO_FROM):
            raise RuntimeError("Identifiants Twilio manquants.")
        resp = requests.post(
            f"https://api.twilio.com/2010-04-01/Accounts/{config.TWILIO_ACCOUNT_SID}/Messages.json",
            data={"From": config.TWILIO_FROM, "To": customer.phone, "Body": body},
            auth=(config.TWILIO_ACCOUNT_SID, config.TWILIO_AUTH_TOKEN),
            timeout=15,
        )
        resp.raise_for_status()

    else:
        raise RuntimeError(f"SMS_PROVIDER '{config.SMS_PROVIDER}' non configuré.")


def send_message(customer: Customer, restaurant: Restaurant, content: str) -> MessageLog:
    """Envoie le message sur le canal préféré.

    DRY_RUN (défaut) : on logge sans envoyer (statut 'logged').
    Sinon : envoi réel, statut 'sent' ou 'failed'.
    """
    channel = choose_channel(customer, restaurant)

    if config.DRY_RUN:
        logger.info("[DRY-RUN %s] -> %s (%s) : %s",
                    channel.upper(), customer.first_name, customer.id, content)
        return MessageLog(restaurant.id, customer.id, channel, content, "logged")

    try:
        if channel == "email":
            _send_email(customer, restaurant, content)
        else:
            _send_sms(customer, restaurant, content)
        status = "sent"
    except Exception as e:
        logger.warning("Échec envoi %s à %s : %s", channel, customer.id, e)
        status = "failed"

    return MessageLog(restaurant.id, customer.id, channel, content, status)
