"""Tests de l'offre (plan unique Pro + paiement au résultat)."""
from app import plans
from app.messaging import choose_channel
from app.models import Customer
from app.restaurants import get_restaurant

PRO = get_restaurant("resto1")


def cust(phone="+33600000000"):
    return Customer.from_dict({
        "id": "c", "restaurant_id": "r", "first_name": "X",
        "email": "x@example.com", "phone": phone,
        "marketing_opt_in": True, "visits": 4,
        "last_visit": "2026-01-01", "favorite_dish": "Plat", "total_spent": 100.0,
    })


def test_plan_unique_pro():
    f = plans.features("pro")
    assert f["scoring"] is True
    assert "sms" in f["channels"]
    assert plans.allows_sms("pro") is True
    assert plans.monthly_cap("pro") is None       # plus de quota Free
    assert plans.PRO_PRICE == "99 €/mois"


def test_controles_actifs():
    for feat in ("manual_approval", "targeting", "frequency_cap", "quiet_hours"):
        assert plans.has("pro", feat) is True
    assert plans.annual_cap("pro") == plans.ANNUAL_CAP_PER_CUSTOMER


def test_estimation_paiement_au_resultat():
    assert plans.outcome_estimate(3.0) == 15.0


def test_choix_du_canal():
    assert choose_channel(cust(phone="+33600000000"), PRO) == "sms"
    assert choose_channel(cust(phone=None), PRO) == "email"
