"""Tests d'API (FastAPI TestClient) : santé, auth, validation, sécurité XSS."""
from fastapi.testclient import TestClient

from app.main import app
from app.models import Customer


def _client() -> TestClient:
    return TestClient(app)


def test_health():
    with _client() as c:
        r = c.get("/health")
    assert r.status_code == 200 and r.json() == {"status": "ok", "db": "ok"}


def test_dashboard_affiche_le_graphique():
    with _client() as c:
        r = c.get("/r/resto1?token=demo-token-resto1")
    assert r.status_code == 200
    assert "14 derniers jours" in r.text and "<svg" in r.text


def test_run_cycle_json():
    with _client() as c:
        r = c.post(
            "/r/resto1/run-cycle?token=demo-token-resto1",
            headers={"accept": "application/json"},
        )
    assert r.status_code == 200
    assert r.json()["detected"] == 10


def test_run_cycle_redirige_le_navigateur():
    with _client() as c:
        r = c.post(
            "/r/resto1/run-cycle?token=demo-token-resto1",
            headers={"accept": "text/html"},
            follow_redirects=False,
        )
    assert r.status_code == 303
    assert "/r/resto1" in r.headers["location"]


def test_landing_publique():
    with _client() as c:
        r = c.get("/")
    assert r.status_code == 200
    assert "Revoilà" in r.text and "waitlist" in r.text.lower()


def test_demo_liste_les_restaurants():
    with _client() as c:
        r = c.get("/demo")
    assert r.status_code == 200
    assert "Chez Lucas" in r.text and "La Trattoria" in r.text


def test_waitlist_enregistre_un_email():
    from app import db
    with _client() as c:
        r = c.post("/waitlist", data={"email": "Resto@Test.fr"},
                   follow_redirects=False)
    assert r.status_code == 303 and "joined=1" in r.headers["location"]
    assert db.count_waitlist() == 1
    assert "resto@test.fr" in [w["email"] for w in db.list_waitlist()]


def test_waitlist_refuse_email_invalide():
    from app import db
    with _client() as c:
        r = c.post("/waitlist", data={"email": "pasunemail"},
                   follow_redirects=False)
    assert r.status_code == 303 and "error=1" in r.headers["location"]
    assert db.count_waitlist() == 0


def test_waitlist_doublon():
    with _client() as c:
        c.post("/waitlist", data={"email": "a@b.fr"}, follow_redirects=False)
        r = c.post("/waitlist", data={"email": "a@b.fr"}, follow_redirects=False)
    assert "exists=1" in r.headers["location"]


def test_waitlist_notifie_le_proprietaire(monkeypatch):
    calls = []
    monkeypatch.setattr("app.messaging.notify_waitlist_signup",
                        lambda email, count: calls.append((email, count)))
    with _client() as c:
        c.post("/waitlist", data={"email": "nouveau@resto.fr"}, follow_redirects=False)
    assert calls and calls[0][0] == "nouveau@resto.fr"


def test_dashboard_auth():
    with _client() as c:
        assert c.get("/r/resto1?token=WRONG").status_code == 401
        assert c.get("/r/resto1?token=demo-token-resto1").status_code == 200
        assert c.get("/r/inconnu?token=x").status_code == 404


def test_checkout_tier_invalide():
    with _client() as c:
        r = c.post("/r/resto1/billing/checkout?token=demo-token-resto1&tier=platine")
    assert r.status_code == 422


def test_unsubscribe_persiste(monkeypatch):
    from app import db
    with _client() as c:
        r = c.get("/unsubscribe?restaurant_id=resto1&customer_id=c001")
    assert r.status_code == 200
    assert "c001" in db.get_opt_outs("resto1")


def test_dashboard_echappe_le_html(monkeypatch):
    """Un nom client malveillant ne doit pas être injecté tel quel (anti-XSS)."""
    evil = Customer.from_dict({
        "id": "evil", "restaurant_id": "resto1",
        "first_name": "<script>alert(1)</script>",
        "email": "e@example.com", "phone": "+33600000000",
        "marketing_opt_in": True, "visits": 5,
        "last_visit": "2026-01-01", "favorite_dish": "Plat", "total_spent": 10.0,
    })

    class FakeSource:
        def get_customers(self, restaurant_id):
            return [evil]

    monkeypatch.setattr("app.main.get_default_source", lambda: FakeSource())
    with _client() as c:
        r = c.get("/r/resto1?token=demo-token-resto1")
    assert r.status_code == 200
    assert "<script>alert(1)</script>" not in r.text
    assert "&lt;script&gt;" in r.text
