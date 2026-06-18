# Revoilà

**Vos clients reviennent. Tout seuls.**

Revoilà repère les clients d'un restaurant qui ne sont pas revenus, calcule lesquels
rapportent le plus (score RFM), et les relance automatiquement par SMS et email — à
partir des données de la caisse. (Nom de code projet : `winback-resto`.)

## Tarification

Offre simple (voir `app/plans.py`) : **essai gratuit 14 jours**, puis deux façons de payer :

- **Abonnement Pro — 99 €/mois** : tout inclus, sans limite — SMS + email, score de
  priorité RFM, segmentation, messages sur-mesure, **validation avant envoi**, ciblage,
  et garde-fous anti-sur-sollicitation (plafonds + heures calmes).
- **Au résultat** : ~5 €/client réellement réactivé (ou % du CA récupéré), sans abonnement.
  Le client ne paie que si ça marche — l'argument le plus fort au démarrage.

Un seul plan applicatif (`pro`) ; l'accès réel est piloté par le **statut d'abonnement**
(essai / actif / expiré) dans `app/billing.py`. Le dashboard affiche l'estimation du
coût « au résultat » du mois.

## Démarrage rapide

```bash
# 1. Créer un environnement virtuel
python3 -m venv .venv
source .venv/bin/activate        # Windows : .venv\Scripts\activate

# 2. Installer les dépendances
pip install -r requirements.txt

# 3. Copier la config d'exemple
cp .env.example .env

# 4. Lancer l'app
uvicorn app.main:app --reload
```

Ouvre http://localhost:8000 → liste des restaurants de démo. Clique sur l'un d'eux
(le token de démo est dans l'URL) pour voir son dashboard : clients à relancer,
ROI estimé, historique des envois.

### Endpoints

- `GET /health` — vérification de santé (pour l'hébergeur).
- `GET /` — index des restaurants.
- `GET /r/{restaurant_id}?token=...` — dashboard d'un restaurant (auth par token).
- `POST /r/{restaurant_id}/run-cycle?token=...` — lance un cycle de relance.
- `POST /r/{restaurant_id}/billing/checkout?token=...&tier=standard|pro` — démarre un abonnement Stripe.
- `POST /stripe/webhook` — réception des événements Stripe.
- `GET /unsubscribe?restaurant_id=...&customer_id=...` — désinscription RGPD (lien public).

Tokens de démo : `demo-token-resto1`, `demo-token-resto2` (dans `data/restaurants.json`).

En mode `DRY_RUN=true` (défaut), les messages sont seulement loggés dans la console — rien n'est envoyé.

## Comment c'est fait

- **Multi-restaurant** : chaque resto a sa config dans `data/restaurants.json` ; clients, logs et désinscriptions sont isolés par `restaurant_id`.
- Les données clients viennent de `data/mock_customers.json` via `MockDataSource`. Aucune vraie caisse n'est nécessaire pour développer.
- La logique de détection (avec RGPD + anti-spam) est dans `app/winback.py`.
- La génération du message est dans `app/messaging.py` (template par défaut, IA si `ANTHROPIC_API_KEY` fournie). Envois email (Brevo) et SMS (Brevo/Twilio) prêts, protégés par `DRY_RUN`.
- La persistance (logs + opt-out + abonnements) est en SQLite dans `app/db.py` (mode WAL + index).
- La facturation Stripe (essai, checkout, webhooks, blocage si inactif) est dans `app/billing.py`.
- Le cycle tourne tout seul (tous les restos) via `app/scheduler.py`, démarré/arrêté proprement via le lifespan FastAPI.
- Interface : templates **Jinja2** (`app/templates/`, auto-échappés → anti-XSS), design responsive, badge d'abonnement, bouton « S'abonner », et mini-graphique SVG des envois sur 14 jours (`app/charts.py`, sans JS ni dépendance).
- UX : après un cycle, le navigateur est redirigé vers le dashboard (POST-redirect-GET) ; les appels API peuvent demander du JSON via l'en-tête `Accept`.
- Logging structuré via `app/logging_config.py`.

## Tests & qualité

```bash
python -m pytest        # 33 tests
python -m ruff check app tests   # lint (si ruff installé)
```

## Ce qui reste à faire

Voir `PROMPT_SUITE.md` : brancher les vraies clés API, Stripe (facturation), déploiement, et compléter `LightspeedDataSource`.

## Travailler avec Claude Code

Le fichier `CLAUDE.md` contient la spec complète et la roadmap. Ouvre le projet dans VS Code, lance Claude Code, et demande-lui par exemple :

> « Implémente l'étape 2 de la roadmap dans CLAUDE.md »

## Brancher une vraie caisse (plus tard)

Créer une classe `LightspeedDataSource` dans `app/data_source.py` qui implémente la même interface `DataSource`. Rien d'autre ne change dans le code. Voir CLAUDE.md, étape 7.
# revoila
