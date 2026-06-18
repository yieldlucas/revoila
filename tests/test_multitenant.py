"""Tests multi-tenant : isolation des données, persistance, opt-out, envois."""

from app import config, db, messaging
from app.data_source import MockDataSource
from app.models import Customer, MessageLog
from app.restaurants import get_all_restaurants, get_restaurant

RESTO1 = get_restaurant("resto1")
RESTO2 = get_restaurant("resto2")


def make_customer(rid="resto1") -> Customer:
    return Customer.from_dict({
        "id": "x1", "restaurant_id": rid, "first_name": "Test",
        "email": "t@example.com", "phone": "+33600000000",
        "marketing_opt_in": True, "visits": 5,
        "last_visit": "2026-01-01", "favorite_dish": "Plat", "total_spent": 100.0,
    })


def test_registre_charge_les_restaurants():
    assert {r.id for r in get_all_restaurants()} == {"resto1", "resto2"}
    assert RESTO2.winback_days == 60  # surcharge par restaurant


def test_datasource_isole_par_restaurant():
    src = MockDataSource()
    c1 = src.get_customers("resto1")
    c2 = src.get_customers("resto2")
    assert all(c.restaurant_id == "resto1" for c in c1)
    assert all(c.restaurant_id == "resto2" for c in c2)
    assert len(c1) == 18 and len(c2) == 6


def test_db_logs_scopes_par_restaurant(tmp_path):
    p = tmp_path / "t.db"
    db.init_db(p)
    db.add_log(MessageLog("resto1", "c1", "sms", "hi", "sent"), p)
    db.add_log(MessageLog("resto2", "d1", "email", "ciao", "sent"), p)
    assert db.count_logs("resto1", p) == 1
    assert db.count_logs("resto2", p) == 1
    assert db.get_logs("resto1", p)[0].customer_id == "c1"


def test_db_opt_out_persiste_et_scope(tmp_path):
    p = tmp_path / "t.db"
    db.init_db(p)
    db.add_opt_out("resto1", "c1", p)
    db.add_opt_out("resto1", "c1", p)  # idempotent
    assert db.get_opt_outs("resto1", p) == {"c1"}
    assert db.get_opt_outs("resto2", p) == set()


def test_dry_run_logge_sans_envoyer(monkeypatch):
    monkeypatch.setattr(config, "DRY_RUN", True)
    c = make_customer()
    log = messaging.send_message(c, RESTO1, "coucou")
    assert log.status == "logged"
    assert log.restaurant_id == "resto1"


def test_envoi_reel_succes(monkeypatch):
    monkeypatch.setattr(config, "DRY_RUN", False)
    monkeypatch.setattr(messaging, "_send_sms", lambda c, r, content: None)
    c = make_customer()  # a un téléphone => SMS
    log = messaging.send_message(c, RESTO1, "coucou")
    assert log.status == "sent"


def test_envoi_reel_echec_ne_bloque_pas(monkeypatch):
    monkeypatch.setattr(config, "DRY_RUN", False)

    def boom(c, r, content):
        raise RuntimeError("provider down")

    monkeypatch.setattr(messaging, "_send_email", boom)
    c = make_customer()
    c.phone = None  # force le canal email
    log = messaging.send_message(c, RESTO1, "coucou")
    assert log.status == "failed"


def test_lien_desinscription_contient_les_ids():
    c = make_customer()
    link = messaging.unsubscribe_link(c)
    assert "restaurant_id=resto1" in link and "customer_id=x1" in link
