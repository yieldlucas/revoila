"""Tests de la facturation Stripe (abonnement, webhooks, gating des cycles)."""
from datetime import datetime, timedelta

import pytest

from app import billing, config, db, scheduler
from app.restaurants import get_restaurant


@pytest.fixture(autouse=True)
def tmp_db(tmp_path, monkeypatch):
    """Chaque test utilise une base SQLite jetable."""
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "billing.db")
    db.init_db()
    yield


def test_actif_sans_abonnement_configure():
    # Aucun enregistrement => essai implicite, ne bloque pas le dev.
    assert billing.is_active("resto1") is True


def test_trial_en_cours_est_actif():
    billing.start_trial("resto1", days=14)
    assert billing.is_active("resto1") is True
    assert billing.status_label("resto1") == "trialing"


def test_trial_expire_est_inactif():
    past = (datetime.utcnow() - timedelta(days=1)).isoformat()
    db.upsert_subscription("resto1", status="trialing", trial_end=past)
    assert billing.is_active("resto1") is False


def test_abonnement_actif():
    db.upsert_subscription("resto1", status="active")
    assert billing.is_active("resto1") is True


def test_abonnement_annule_est_inactif():
    db.upsert_subscription("resto1", status="canceled")
    assert billing.is_active("resto1") is False


def test_webhook_checkout_complete_active():
    event = {
        "type": "checkout.session.completed",
        "data": {"object": {
            "metadata": {"restaurant_id": "resto1"},
            "customer": "cus_123", "subscription": "sub_123",
        }},
    }
    out = billing.process_event(event)
    assert out == {"activated": "resto1"}
    assert billing.is_active("resto1") is True
    assert db.get_subscription("resto1")["stripe_customer_id"] == "cus_123"


def test_webhook_paiement_echoue_passe_past_due():
    event = {
        "type": "invoice.payment_failed",
        "data": {"object": {"metadata": {"restaurant_id": "resto1"}}},
    }
    billing.process_event(event)
    assert db.get_subscription("resto1")["status"] == "past_due"
    assert billing.is_active("resto1") is False


def test_webhook_evenement_inconnu_ignore():
    out = billing.process_event({"type": "ping", "data": {"object": {}}})
    assert "ignored" in out


def test_scheduler_ignore_resto_inactif():
    db.upsert_subscription("resto1", status="canceled")
    summary = scheduler.run_cycle_for(get_restaurant("resto1"))
    assert summary["sent"] == 0
    assert summary.get("skipped") == "inactive_subscription"


def test_checkout_sans_cle_stripe_leve_erreur(monkeypatch):
    monkeypatch.setattr(config, "STRIPE_SECRET_KEY", "")
    with pytest.raises(RuntimeError):
        billing.create_checkout_session(get_restaurant("resto1"))
