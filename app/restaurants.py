"""Registre des restaurants (multi-tenant).

En dev : chargé depuis data/restaurants.json (mis en cache).
Plus tard : table en base, alimentée à l'inscription d'un nouveau client.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from .models import Restaurant

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
_REGISTRY_PATH = DATA_DIR / "restaurants.json"


@lru_cache(maxsize=1)
def _registry() -> dict[str, Restaurant]:
    """Charge et met en cache le registre. Utiliser reload() après modification."""
    raw = json.loads(_REGISTRY_PATH.read_text(encoding="utf-8"))
    return {d["id"]: Restaurant.from_dict(d) for d in raw}


def reload() -> None:
    """Vide le cache (à appeler si data/restaurants.json change à chaud)."""
    _registry.cache_clear()


def get_all_restaurants() -> list[Restaurant]:
    return list(_registry().values())


def get_restaurant(restaurant_id: str) -> Restaurant | None:
    return _registry().get(restaurant_id)
