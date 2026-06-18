"""Tests de l'attribution des retours (paiement au résultat)."""
from datetime import date, datetime, timedelta

from app import attribution, db
from app.models import Customer, MessageLog, Restaurant

RESTO = Restaurant(id="r", name="R", tone="t", dashboard_token="x", avg_ticket=35)


def cust(cid, last_visit_iso):
    return Customer.from_dict({
        "id": cid, "restaurant_id": "r", "first_name": "X",
        "email": "x@example.com", "phone": "+33600000000",
        "marketing_opt_in": True, "visits": 4,
        "last_visit": last_visit_iso, "favorite_dish": "Plat", "total_spent": 100.0,
    })


def test_retour_dans_la_fenetre_est_attribue():
    # Relance il y a 10 jours, le client est revenu il y a 2 jours.
    sent = datetime.utcnow() - timedelta(days=10)
    db.add_log(MessageLog("r", "c1", "sms", "msg", "sent", sent_at=sent))
    visit = (date.today() - timedelta(days=2)).isoformat()

    res = attribution.run_attribution(RESTO, [cust("c1", visit)])
    assert res["new_conversions"] == 1

    summary = attribution.billing_summary(RESTO)
    assert summary["recovered"] == 1
    assert summary["recovered_revenue"] == 35.0
    assert summary["due_per_client"] == 5.0  # 1 client * 5 €


def test_retour_hors_fenetre_non_attribue():
    # Relance il y a 90 jours, visite il y a 1 jour => au-delà des 30 j après l'envoi.
    sent = datetime.utcnow() - timedelta(days=90)
    db.add_log(MessageLog("r", "c2", "sms", "msg", "sent", sent_at=sent))
    visit = (date.today() - timedelta(days=1)).isoformat()

    res = attribution.run_attribution(RESTO, [cust("c2", visit)])
    assert res["new_conversions"] == 0


def test_visite_avant_la_relance_non_attribuee():
    sent = datetime.utcnow() - timedelta(days=5)
    db.add_log(MessageLog("r", "c3", "sms", "msg", "sent", sent_at=sent))
    visit = (date.today() - timedelta(days=20)).isoformat()  # avant l'envoi

    res = attribution.run_attribution(RESTO, [cust("c3", visit)])
    assert res["new_conversions"] == 0


def test_pas_de_double_attribution():
    sent = datetime.utcnow() - timedelta(days=8)
    db.add_log(MessageLog("r", "c4", "sms", "msg", "sent", sent_at=sent))
    visit = (date.today() - timedelta(days=1)).isoformat()

    first = attribution.run_attribution(RESTO, [cust("c4", visit)])
    second = attribution.run_attribution(RESTO, [cust("c4", visit)])
    assert first["new_conversions"] == 1
    assert second["new_conversions"] == 0  # déjà compté
    assert attribution.billing_summary(RESTO)["recovered"] == 1
