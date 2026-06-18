"""Pré-remplissage de données de démonstration réalistes.

But : que le dashboard de démo « grouille de vie » dès qu'un visiteur l'ouvre
(historique d'envois sur 14 jours, retours attribués, CA récupéré) — pour montrer
la puissance de l'outil en un coup d'œil.

Idempotent : ne seede un restaurant que si sa table d'envois est vide. Sur un
hébergeur à disque éphémère (plan gratuit), c'est rejoué à chaque démarrage —
donc la démo est toujours pleine. N'envoie jamais rien : insère directement des
lignes d'historique en base.
"""
from __future__ import annotations

import random
from datetime import datetime, timedelta

from . import db
from .logging_config import get_logger
from .models import MessageLog
from .restaurants import get_all_restaurants

logger = get_logger(__name__)

_NAMES = [
    "Camille", "Yanis", "Marc", "Nadia", "Karim", "Julie", "Paul", "Sarah",
    "Léa", "Hugo", "Émilie", "Antoine", "Sofia", "Tom", "Inès", "Lucas",
    "Chloé", "Marco", "Giulia", "Nora", "Adam", "Manon", "Théo", "Jade",
]


def seed_demo() -> None:
    """Remplit l'historique de démo des restaurants dont la table est vide."""
    db.init_db()
    for r in get_all_restaurants():
        if db.count_logs(r.id) > 0:
            continue
        rnd = random.Random(r.id)
        # 14 jours d'envois
        for d in range(13, -1, -1):
            base = datetime.utcnow() - timedelta(days=d)
            for _ in range(rnd.randint(1, 5)):
                ts = base - timedelta(hours=rnd.randint(0, 6), minutes=rnd.randint(0, 59))
                name = rnd.choice(_NAMES)
                channel = "sms" if rnd.random() < 0.6 else "email"
                db.add_log(MessageLog(r.id, name, channel, "Relance de démonstration", "sent", sent_at=ts))
        # Une partie revient (retours attribués) → CA récupéré.
        # On convertit des envois récents pour qu'ils soient visibles dans l'historique.
        unconverted = db.get_unconverted_sends(r.id)  # ordre chronologique
        for send in unconverted[-rnd.randint(10, 16):]:
            day = (datetime.utcnow() - timedelta(days=rnd.randint(0, 4))).date().isoformat()
            db.mark_converted(send["id"], day, r.avg_ticket)
        logger.info("Démo seedée pour %s (%d envois).", r.id, db.count_logs(r.id))
