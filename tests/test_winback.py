"""Tests des règles métier du win-back (multi-tenant + RGPD)."""
from datetime import date, datetime, timedelta

from app.models import Customer, MessageLog, Restaurant
from app.winback import (
    estimate_recovered_revenue,
    find_lapsed_customers,
    is_lapsed,
    recently_contacted,
)

TODAY = date(2026, 6, 17)

RESTO = Restaurant(
    id="resto1", name="Chez Lucas", tone="chaleureux", dashboard_token="t",
    winback_days=45, min_visits=2, cooldown_days=30,
    avg_ticket=35, winback_conversion=0.15,
)


def make_customer(**kwargs) -> Customer:
    base = {
        "id": "c1",
        "restaurant_id": "resto1",
        "first_name": "Test",
        "email": "t@example.com",
        "phone": "+33600000000",
        "marketing_opt_in": True,
        "visits": 5,
        "last_visit": (TODAY - timedelta(days=60)).isoformat(),
        "favorite_dish": "Plat",
        "total_spent": 100.0,
    }
    base.update(kwargs)
    return Customer.from_dict(base)


def test_client_endormi_est_detecte():
    c = make_customer(last_visit=(TODAY - timedelta(days=60)).isoformat())
    assert is_lapsed(c, RESTO, today=TODAY) is True


def test_client_recent_non_detecte():
    c = make_customer(last_visit=(TODAY - timedelta(days=10)).isoformat())
    assert is_lapsed(c, RESTO, today=TODAY) is False


def test_opt_out_rgpd_jamais_relance():
    c = make_customer()
    assert is_lapsed(c, RESTO, today=TODAY, opt_outs={c.id}) is False


def test_consentement_marketing_requis():
    c = make_customer(marketing_opt_in=False)
    assert is_lapsed(c, RESTO, today=TODAY) is False


def test_visite_unique_non_relancee():
    c = make_customer(visits=1)
    assert is_lapsed(c, RESTO, today=TODAY) is False


def test_anti_spam_bloque_relance_recente():
    c = make_customer()
    recent_log = MessageLog(
        restaurant_id="resto1", customer_id=c.id, channel="sms",
        content="x", status="logged",
        sent_at=datetime.utcnow() - timedelta(days=5),
    )
    assert recently_contacted(c, RESTO, [recent_log]) is True
    assert find_lapsed_customers([c], RESTO, logs=[recent_log], today=TODAY) == []


def test_anti_spam_laisse_passer_apres_cooldown():
    c = make_customer()
    old_log = MessageLog(
        restaurant_id="resto1", customer_id=c.id, channel="sms",
        content="x", status="logged",
        sent_at=datetime.utcnow() - timedelta(days=RESTO.cooldown_days + 1),
    )
    assert recently_contacted(c, RESTO, [old_log]) is False
    assert find_lapsed_customers([c], RESTO, logs=[old_log], today=TODAY) == [c]


def test_canal_email_si_pas_de_telephone():
    c = make_customer(phone=None)
    assert c.preferred_channel == "email"


def test_estimation_roi():
    targets = [make_customer(id=f"c{i}") for i in range(10)]
    roi = estimate_recovered_revenue(targets, RESTO)
    assert roi["targeted"] == 10
    assert roi["estimated_revenue"] == round(
        10 * RESTO.winback_conversion * RESTO.avg_ticket, 2
    )
