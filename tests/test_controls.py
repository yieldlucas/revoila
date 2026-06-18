"""Tests des contrôles Pro : flags, plafonds de fréquence, heures calmes, validation manuelle."""
import datetime as dt
from datetime import timedelta

from fastapi.testclient import TestClient

from app import plans, winback
from app.main import app
from app.models import Customer, MessageLog, Restaurant

RESTO = Restaurant(
    id="r", name="R", tone="t", dashboard_token="x",
    winback_days=45, min_visits=2, cooldown_days=30, avg_ticket=35,
)


def lapsed_customer():
    return Customer.from_dict({
        "id": "c1", "restaurant_id": "r", "first_name": "X",
        "email": "x@example.com", "phone": "+33600000000",
        "marketing_opt_in": True, "visits": 5,
        "last_visit": (dt.date.today() - timedelta(days=120)).isoformat(),
        "favorite_dish": "Plat", "total_spent": 200.0,
    })


# --- Fonctionnalités de contrôle (plan unique) ---

def test_controles_actifs():
    for feat in ("manual_approval", "targeting", "frequency_cap", "quiet_hours"):
        assert plans.has("pro", feat) is True
    assert plans.annual_cap("pro") == plans.ANNUAL_CAP_PER_CUSTOMER


# --- Heures calmes ---

def test_heures_calmes():
    wed = dt.datetime(2026, 6, 17, 12, 0)         # mercredi midi
    assert wed.weekday() != 6
    assert plans.in_quiet_hours(wed) is False
    assert plans.in_quiet_hours(wed.replace(hour=22)) is True
    assert plans.in_quiet_hours(wed.replace(hour=7)) is True
    sunday = wed
    while sunday.weekday() != 6:
        sunday += timedelta(days=1)
    assert plans.in_quiet_hours(sunday.replace(hour=12)) is True


# --- Plafond de fréquence + exclusion ---

def test_plafond_annuel_exclut_client_trop_sollicite():
    c = lapsed_customer()
    now = dt.datetime.utcnow()
    # 6 relances entre 60 et 200 j (au-delà du cooldown, dans l'année)
    logs = [MessageLog("r", "c1", "sms", "m", "sent", sent_at=now - timedelta(days=60 + 20 * i))
            for i in range(6)]
    assert winback.find_lapsed_customers([c], RESTO, logs=logs, annual_cap=6) == []
    assert winback.find_lapsed_customers([c], RESTO, logs=logs, annual_cap=None) == [c]


def test_liste_exclusion():
    c = lapsed_customer()
    assert winback.find_lapsed_customers([c], RESTO, exclude_ids={"c1"}) == []
    assert winback.find_lapsed_customers([c], RESTO, exclude_ids=set()) == [c]


# --- Mode validation manuelle (API) ---

def test_preview_accessible():
    with TestClient(app) as client:
        r = client.get("/r/resto1/preview?token=demo-token-resto1")
        assert r.status_code == 200 and "Préparer une relance" in r.text


def test_preview_envoie_seulement_la_selection():
    from app import db
    with TestClient(app) as client:
        before = db.count_logs("resto1")
        r = client.post(
            "/r/resto1/preview/send?token=demo-token-resto1",
            data={"ids": ["c001", "c002"]}, follow_redirects=False,
        )
        assert r.status_code == 303 and "sent=2" in r.headers["location"]
        assert db.count_logs("resto1") == before + 2


def test_preview_send_bloque_si_essai_termine():
    from app import db
    with TestClient(app) as client:
        db.upsert_subscription("resto1", status="canceled")
        r = client.post(
            "/r/resto1/preview/send?token=demo-token-resto1",
            data={"ids": ["c001"]}, follow_redirects=False,
        )
        assert r.status_code == 402
