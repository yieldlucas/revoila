"""Le plan unique Pro n'a pas de quota mensuel : tous les clients éligibles sont relancés."""
from datetime import date, timedelta

from app import scheduler
from app.models import Customer
from app.restaurants import get_restaurant

RESTO = get_restaurant("resto2")  # plan pro


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


def test_pro_relance_sans_quota(monkeypatch):
    class FakeSource:
        def get_customers(self, restaurant_id):
            return _lapsed(15)

    monkeypatch.setattr(scheduler, "get_default_source", lambda: FakeSource())
    summary = scheduler.run_cycle_for(RESTO)
    assert summary["sent"] == 15           # aucun plafond mensuel
    assert "capped" not in summary
