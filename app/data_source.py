"""Couche d'abstraction des données client.

En dev : MockDataSource (fichier JSON).
Plus tard : LightspeedDataSource (API POS) implémentant la même interface,
sans rien changer au reste du code.
"""
from __future__ import annotations

import json
from abc import ABC, abstractmethod
from pathlib import Path

from .models import Customer

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

# Cache des clients chargés depuis le JSON, invalidé si le fichier change (mtime).
# Clé : chemin absolu ; valeur : (mtime, liste de Customer).
_mock_cache: dict[str, tuple[float, list[Customer]]] = {}


class DataSource(ABC):
    @abstractmethod
    def get_customers(self, restaurant_id: str) -> list[Customer]:
        """Retourne les clients d'un restaurant donné, avec leur historique."""
        ...


class MockDataSource(DataSource):
    def __init__(self, path: Path | None = None):
        self.path = path or (DATA_DIR / "mock_customers.json")

    def _load_all(self) -> list[Customer]:
        """Charge tous les clients du fichier, avec cache invalidé au changement."""
        key = str(self.path)
        mtime = self.path.stat().st_mtime
        cached = _mock_cache.get(key)
        if cached is None or cached[0] != mtime:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            customers = [Customer.from_dict(d) for d in raw]
            _mock_cache[key] = (mtime, customers)
        return _mock_cache[key][1]

    def get_customers(self, restaurant_id: str) -> list[Customer]:
        return [c for c in self._load_all() if c.restaurant_id == restaurant_id]


class LightspeedDataSource(DataSource):
    """Source de données réelle via l'API Lightspeed Restaurant (K-Series).

    Squelette prêt à compléter quand les accès partenaires seront validés.
    Doc API : https://api-docs.lsk.lightspeed.app/
    Auth : OAuth 2.0 (déposer la Partner Application, choisir « Build an App »).

    Étapes pour finaliser (voir CLAUDE.md étape 7) :
      1. Obtenir client_id / client_secret via le Developer Portal Lightspeed.
      2. Implémenter le flux OAuth 2.0 (autorisation + refresh token).
      3. Appeler l'endpoint clients/ventes, paginer, et mapper vers Customer.
    """

    BASE_URL = "https://api.lsk.lightspeed.app"  # à confirmer selon la région

    def __init__(self, access_token: str, business_id: str):
        self.access_token = access_token
        self.business_id = business_id

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Accept": "application/json",
        }

    def get_customers(self, restaurant_id: str) -> list[Customer]:
        # TODO : appeler l'API (requests/httpx), paginer, puis :
        #   return [self._map(raw, restaurant_id) for raw in api_rows]
        raise NotImplementedError(
            "LightspeedDataSource n'est pas encore branchée. "
            "Compléter le flux OAuth + l'appel API (voir docstring)."
        )

    @staticmethod
    def _map(raw: dict, restaurant_id: str) -> Customer:
        """Mappe une ligne d'API Lightspeed vers notre modèle Customer.

        À ajuster aux vrais noms de champs renvoyés par l'API.
        """
        return Customer.from_dict(
            {
                "id": raw.get("id"),
                "restaurant_id": restaurant_id,
                "first_name": raw.get("first_name") or raw.get("firstName") or "Client",
                "email": raw.get("email"),
                "phone": raw.get("phone") or raw.get("mobile"),
                "marketing_opt_in": bool(raw.get("marketing_opt_in", False)),
                "visits": int(raw.get("visit_count", 0)),
                "last_visit": raw.get("last_visit_date"),
                "favorite_dish": raw.get("favorite_dish"),
                "total_spent": float(raw.get("total_spent", 0.0)),
            }
        )


def get_default_source() -> DataSource:
    """Point d'entrée unique : on change ici quand on passe au vrai POS.

    Exemple futur :
        return LightspeedDataSource(access_token=..., business_id=...)
    """
    return MockDataSource()
