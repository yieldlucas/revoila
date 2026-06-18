"""Tests du gating Free / Standard / Pro (canaux, fonctionnalités, prix)."""
from app import plans
from app.messaging import choose_channel
from app.models import Customer, Restaurant
from app.restaurants import get_restaurant

PRO = get_restaurant("resto1")    # plan pro
FREE = get_restaurant("resto2")   # plan free
STANDARD = Restaurant(id="s", name="S", tone="t", dashboard_token="x", plan="standard")


def cust(phone="+33600000000"):
    return Customer.from_dict({
        "id": "c", "restaurant_id": "r", "first_name": "X",
        "email": "x@example.com", "phone": phone,
        "marketing_opt_in": True, "visits": 4,
        "last_visit": "2026-01-01", "favorite_dish": "Plat", "total_spent": 100.0,
    })


def test_features_par_plan():
    assert plans.allows_sms("pro") is True
    assert plans.allows_sms("standard") is True
    assert plans.allows_sms("free") is False
    assert plans.features("pro")["scoring"] is True
    assert plans.features("standard")["scoring"] is False  # SMS mais pas l'intelligence
    assert plans.features("free")["scoring"] is False
    # plan inconnu => repli sur free
    assert plans.features("inconnu") == plans.features("free")


def test_echelle_de_montee_en_gamme():
    assert [p["id"] for p in plans.upgrades("free")] == ["standard", "pro"]
    assert [p["id"] for p in plans.upgrades("standard")] == ["pro"]
    assert plans.upgrades("pro") == []


def test_estimation_paiement_au_resultat():
    # 3 retours attendus * 5 € = 15 €
    assert plans.outcome_estimate(3.0) == 15.0


def test_standard_envoie_des_sms():
    assert choose_channel(cust(phone="+33600000000"), STANDARD) == "sms"


def test_free_force_email_meme_avec_telephone():
    assert choose_channel(cust(phone="+33600000000"), FREE) == "email"


def test_pro_utilise_sms_si_telephone():
    assert choose_channel(cust(phone="+33600000000"), PRO) == "sms"


def test_pro_sans_telephone_retombe_sur_email():
    assert choose_channel(cust(phone=None), PRO) == "email"
