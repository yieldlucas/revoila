"""Fixtures partagées : isole chaque test (DB jetable + caches vidés)."""
import pytest

from app import data_source, db, main, restaurants


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    """Chaque test utilise une base SQLite jetable et des caches propres."""
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "test.db")
    db.init_db()
    data_source._mock_cache.clear()
    restaurants.reload()
    main._WL_HITS.clear()  # remet à zéro le rate-limit waitlist entre les tests
    yield
    data_source._mock_cache.clear()
    restaurants.reload()
