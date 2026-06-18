"""Tests du score de priorité RFM et de la segmentation."""
from datetime import date, timedelta

from app.models import Customer, Restaurant
from app.scoring import prioritize, score_customer

TODAY = date(2026, 6, 17)
RESTO = Restaurant(
    id="r", name="R", tone="t", dashboard_token="x",
    winback_days=45, avg_ticket=35, winback_conversion=0.15,
)


def cust(visits, spent, days_ago, cid="c"):
    return Customer.from_dict({
        "id": cid, "restaurant_id": "r", "first_name": "X",
        "email": "x@example.com", "phone": "+33600000000",
        "marketing_opt_in": True, "visits": visits,
        "last_visit": (TODAY - timedelta(days=days_ago)).isoformat(),
        "favorite_dish": "Plat", "total_spent": spent,
    })


def test_vip_a_un_score_eleve():
    vip = cust(visits=12, spent=900, days_ago=50)
    s = score_customer(vip, RESTO, today=TODAY)
    assert s.segment == "VIP"
    assert s.value >= 60


def test_occasionnel_a_un_score_bas():
    occ = cust(visits=2, spent=40, days_ago=120)
    s = score_customer(occ, RESTO, today=TODAY)
    assert s.segment == "Occasionnel"
    assert s.value < 40


def test_recoverable_flag():
    recent = cust(visits=5, spent=200, days_ago=50)
    lost = cust(visits=5, spent=200, days_ago=200)
    assert score_customer(recent, RESTO, today=TODAY).recoverable is True
    assert score_customer(lost, RESTO, today=TODAY).recoverable is False


def test_priorisation_decroissante():
    customers = [
        cust(2, 40, 120, "low"),
        cust(12, 900, 50, "high"),
        cust(5, 200, 60, "mid"),
    ]
    ordered = prioritize(customers, RESTO, today=TODAY)
    ids = [c.id for c, _ in ordered]
    assert ids[0] == "high" and ids[-1] == "low"
    scores = [s.value for _, s in ordered]
    assert scores == sorted(scores, reverse=True)
