"""Test du quota mensuel de relances sur le plan Free."""
from datetime import date, timedelta

from app import scheduler
from app.models import Customer
from app.restaurants import get_restaurant

FREE = get_restaurant("resto2")  # plan free, cap 10/mois


def _lapsed(n):
    old = (date.today() - timedelta(days=120)).isoformat()
    return [
        Customer.from_dict({
            "id": f"f{i}", "restaurant_id": "resto2", "first_name": "X",
            "email": f"f{i}@example.com", "phone": None,
            "marketing_opt_in": True, "visits": 4,
            "last_visit": old, "favorite_dish": "Plat", "total_spent": 100.0,
        })
        for i in range(n)
    ]


def test_free_plafonne_les_relances(monkeypatch):
    class FakeSource:
        def get_customers(self, restaurant_id):
            return _lapsed(15)

    monkeypatch.setattr(scheduler, "get_default_source", lambda: FakeSource())
    summary = scheduler.run_cycle_for(FREE)
    assert summary["sent"] == 10          # plafonné à 10
    assert "capped" in summary
