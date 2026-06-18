"""Persistance en SQLite (stdlib, aucune dépendance externe).

Tout est scopé par restaurant_id (multi-tenant). Pour passer à Postgres/Supabase
plus tard, réimplémenter ces mêmes fonctions ; le reste du code ne change pas.
"""
from __future__ import annotations

import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path

from .models import MessageLog

DB_PATH = Path(__file__).resolve().parent.parent / "winback.db"


def _connect(db_path: Path | None = None) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path or DB_PATH, timeout=5.0)
    conn.row_factory = sqlite3.Row
    # WAL : lectures et écritures concurrentes (scheduler + requêtes web).
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


def _migrate_message_log(conn: sqlite3.Connection) -> None:
    """Ajoute les colonnes d'attribution aux bases existantes (migration douce)."""
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(message_log)")}
    if "converted_at" not in cols:
        conn.execute("ALTER TABLE message_log ADD COLUMN converted_at TEXT")
    if "recovered_amount" not in cols:
        conn.execute("ALTER TABLE message_log ADD COLUMN recovered_amount REAL")


def init_db(db_path: Path | None = None) -> None:
    with _connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS message_log (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                restaurant_id   TEXT NOT NULL,
                customer_id     TEXT NOT NULL,
                channel         TEXT NOT NULL,
                content         TEXT NOT NULL,
                status          TEXT NOT NULL,
                sent_at         TEXT NOT NULL,
                converted_at    TEXT,
                recovered_amount REAL
            )
            """
        )
        _migrate_message_log(conn)
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS opt_out (
                restaurant_id TEXT NOT NULL,
                customer_id   TEXT NOT NULL,
                opted_out_at  TEXT NOT NULL,
                PRIMARY KEY (restaurant_id, customer_id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS subscription (
                restaurant_id          TEXT PRIMARY KEY,
                status                 TEXT NOT NULL,
                trial_end              TEXT,
                stripe_customer_id     TEXT,
                stripe_subscription_id TEXT,
                updated_at             TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS waitlist (
                email      TEXT PRIMARY KEY,
                source     TEXT,
                created_at TEXT NOT NULL
            )
            """
        )
        # Index : accélère les lectures de logs par restaurant (anti-spam + dashboard).
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_message_log_resto "
            "ON message_log(restaurant_id, sent_at)"
        )
        conn.commit()


# --- Logs d'envoi ---

def add_log(log: MessageLog, db_path: Path | None = None) -> None:
    with _connect(db_path) as conn:
        conn.execute(
            "INSERT INTO message_log "
            "(restaurant_id, customer_id, channel, content, status, sent_at)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (log.restaurant_id, log.customer_id, log.channel, log.content,
             log.status, log.sent_at.isoformat()),
        )
        conn.commit()


def get_logs(restaurant_id: str, db_path: Path | None = None) -> list[MessageLog]:
    with _connect(db_path) as conn:
        rows = conn.execute(
            "SELECT id, restaurant_id, customer_id, channel, content, status, "
            "sent_at, converted_at FROM message_log "
            "WHERE restaurant_id = ? ORDER BY sent_at DESC",
            (restaurant_id,),
        ).fetchall()
    return [
        MessageLog(
            id=r["id"],
            restaurant_id=r["restaurant_id"],
            customer_id=r["customer_id"],
            channel=r["channel"],
            content=r["content"],
            status=r["status"],
            sent_at=datetime.fromisoformat(r["sent_at"]),
            converted_at=r["converted_at"],
        )
        for r in rows
    ]


def count_logs(restaurant_id: str, db_path: Path | None = None) -> int:
    with _connect(db_path) as conn:
        return conn.execute(
            "SELECT COUNT(*) FROM message_log WHERE restaurant_id = ?",
            (restaurant_id,),
        ).fetchone()[0]


def count_logs_since(
    restaurant_id: str, since_iso: str, db_path: Path | None = None
) -> int:
    """Nombre d'envois depuis une date ISO (pour le quota mensuel du Free)."""
    with _connect(db_path) as conn:
        return conn.execute(
            "SELECT COUNT(*) FROM message_log "
            "WHERE restaurant_id = ? AND sent_at >= ?",
            (restaurant_id, since_iso),
        ).fetchone()[0]


# --- Attribution des retours (paiement au résultat) ---

def get_unconverted_sends(
    restaurant_id: str,
    statuses: tuple[str, ...] = ("sent", "logged"),
    db_path: Path | None = None,
) -> list[dict]:
    """Envois délivrés et pas encore attribués (id, customer_id, sent_at), du plus ancien."""
    placeholders = ",".join("?" for _ in statuses)
    with _connect(db_path) as conn:
        rows = conn.execute(
            f"SELECT id, customer_id, sent_at FROM message_log "
            f"WHERE restaurant_id = ? AND converted_at IS NULL "
            f"AND status IN ({placeholders}) ORDER BY sent_at ASC",
            (restaurant_id, *statuses),
        ).fetchall()
    return [dict(r) for r in rows]


def get_converted_customer_ids(
    restaurant_id: str, db_path: Path | None = None
) -> set[str]:
    with _connect(db_path) as conn:
        rows = conn.execute(
            "SELECT DISTINCT customer_id FROM message_log "
            "WHERE restaurant_id = ? AND converted_at IS NOT NULL",
            (restaurant_id,),
        ).fetchall()
    return {r["customer_id"] for r in rows}


def mark_converted(
    log_id: int, converted_at: str, recovered_amount: float,
    db_path: Path | None = None,
) -> None:
    with _connect(db_path) as conn:
        conn.execute(
            "UPDATE message_log SET converted_at = ?, recovered_amount = ? WHERE id = ?",
            (converted_at, recovered_amount, log_id),
        )
        conn.commit()


def conversion_stats(restaurant_id: str, db_path: Path | None = None) -> dict:
    """Bilan des retours attribués : nombre et CA récupéré cumulé."""
    with _connect(db_path) as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS n, COALESCE(SUM(recovered_amount), 0) AS rev "
            "FROM message_log WHERE restaurant_id = ? AND converted_at IS NOT NULL",
            (restaurant_id,),
        ).fetchone()
    return {"recovered": row["n"], "recovered_revenue": round(row["rev"], 2)}


# --- Waitlist (validation de la demande) ---

def add_waitlist(email: str, source: str = "landing",
                 db_path: Path | None = None) -> bool:
    """Ajoute un email à la waitlist. Renvoie False si déjà présent."""
    with _connect(db_path) as conn:
        cur = conn.execute(
            "INSERT OR IGNORE INTO waitlist (email, source, created_at) "
            "VALUES (?, ?, ?)",
            (email.strip().lower(), source, datetime.utcnow().isoformat()),
        )
        conn.commit()
        return cur.rowcount > 0


def count_waitlist(db_path: Path | None = None) -> int:
    with _connect(db_path) as conn:
        return conn.execute("SELECT COUNT(*) FROM waitlist").fetchone()[0]


def list_waitlist(db_path: Path | None = None) -> list[dict]:
    with _connect(db_path) as conn:
        rows = conn.execute(
            "SELECT email, source, created_at FROM waitlist ORDER BY created_at DESC"
        ).fetchall()
    return [dict(r) for r in rows]


def daily_send_counts(
    restaurant_id: str, days: int = 14, db_path: Path | None = None
) -> list[tuple[str, int]]:
    """Nombre d'envois par jour sur les `days` derniers jours (ordre chronologique).

    Renvoie une série complète (jours sans envoi inclus avec 0), idéale pour un graphe.
    """
    with _connect(db_path) as conn:
        rows = conn.execute(
            "SELECT substr(sent_at, 1, 10) AS d, COUNT(*) AS n "
            "FROM message_log WHERE restaurant_id = ? GROUP BY d",
            (restaurant_id,),
        ).fetchall()
    counts = {r["d"]: r["n"] for r in rows}
    today = date.today()
    series = []
    for i in range(days - 1, -1, -1):
        day = (today - timedelta(days=i)).isoformat()
        series.append((day[5:], counts.get(day, 0)))  # label MM-DD
    return series


# --- Désinscription (RGPD) ---

def add_opt_out(restaurant_id: str, customer_id: str,
                db_path: Path | None = None) -> None:
    with _connect(db_path) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO opt_out "
            "(restaurant_id, customer_id, opted_out_at) VALUES (?, ?, ?)",
            (restaurant_id, customer_id, datetime.utcnow().isoformat()),
        )
        conn.commit()


def get_opt_outs(restaurant_id: str, db_path: Path | None = None) -> set[str]:
    with _connect(db_path) as conn:
        rows = conn.execute(
            "SELECT customer_id FROM opt_out WHERE restaurant_id = ?",
            (restaurant_id,),
        ).fetchall()
    return {r["customer_id"] for r in rows}


# --- Abonnements (Stripe) ---

def get_subscription(restaurant_id: str,
                     db_path: Path | None = None) -> dict | None:
    with _connect(db_path) as conn:
        row = conn.execute(
            "SELECT restaurant_id, status, trial_end, stripe_customer_id, "
            "stripe_subscription_id, updated_at FROM subscription "
            "WHERE restaurant_id = ?",
            (restaurant_id,),
        ).fetchone()
    return dict(row) if row else None


def upsert_subscription(
    restaurant_id: str,
    status: str,
    trial_end: str | None = None,
    stripe_customer_id: str | None = None,
    stripe_subscription_id: str | None = None,
    db_path: Path | None = None,
) -> None:
    """Crée ou met à jour l'abonnement. Les champs None conservent l'existant."""
    existing = get_subscription(restaurant_id, db_path) or {}
    merged = {
        "status": status,
        "trial_end": trial_end if trial_end is not None else existing.get("trial_end"),
        "stripe_customer_id": stripe_customer_id if stripe_customer_id is not None
        else existing.get("stripe_customer_id"),
        "stripe_subscription_id": stripe_subscription_id if stripe_subscription_id is not None
        else existing.get("stripe_subscription_id"),
    }
    with _connect(db_path) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO subscription "
            "(restaurant_id, status, trial_end, stripe_customer_id, "
            "stripe_subscription_id, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
            (restaurant_id, merged["status"], merged["trial_end"],
             merged["stripe_customer_id"], merged["stripe_subscription_id"],
             datetime.utcnow().isoformat()),
        )
        conn.commit()
