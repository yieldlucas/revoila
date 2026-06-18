"""Tests du graphe SVG et de l'agrégation quotidienne des envois."""
from datetime import date, datetime

from app import charts, db
from app.models import MessageLog


def test_daily_send_counts_serie_complete():
    series = db.daily_send_counts("resto1", days=7)
    assert len(series) == 7  # un point par jour, même sans envoi
    assert all(count == 0 for _, count in series)


def test_daily_send_counts_compte_aujourdhui():
    today = datetime.utcnow()
    db.add_log(MessageLog("resto1", "c1", "sms", "x", "sent", sent_at=today))
    db.add_log(MessageLog("resto1", "c2", "sms", "x", "sent", sent_at=today))
    series = db.daily_send_counts("resto1", days=7)
    label_today = date.today().isoformat()[5:]
    assert dict(series)[label_today] == 2


def test_bar_chart_vide():
    svg = charts.bar_chart_svg([])
    assert "<svg" in svg and "Aucun envoi" in svg


def test_bar_chart_avec_donnees():
    svg = charts.bar_chart_svg([("06-01", 0), ("06-02", 5), ("06-03", 2)])
    assert "<svg" in svg and "<rect" in svg
    assert "pic : 5/j" in svg
