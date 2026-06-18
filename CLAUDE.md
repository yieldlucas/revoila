# CLAUDE.md — Spec du projet pour Claude Code

> Ce fichier est lu automatiquement par Claude Code. Il décrit quoi construire, comment, et dans quel ordre. Garde-le à jour quand le projet évolue.

## Le produit en une phrase

Un service qui se branche sur la caisse (POS) d'un restaurant et fait **revenir automatiquement les clients perdus** : il détecte les clients endormis, génère un message personnalisé par IA, et l'envoie par SMS + email — sans que le restaurateur ait rien à piloter.

## Principe directeur

**MVP brutalement simple.** Un seul scénario : le *win-back* (relance des clients qui ne sont pas revenus). Pas de fidélité à points, pas d'agent vocal, pas de réponse aux avis. Ça viendra après les premiers clients payants.

**On code sans dépendre de l'API Lightspeed.** Toute la donnée passe par une couche d'abstraction `DataSource`. En dev, c'est `MockDataSource` (données fictives dans `data/mock_customers.json`). Plus tard, on ajoute `LightspeedDataSource` sans toucher au reste du code.

## Stack

- **Python 3.11+ / FastAPI** — API + petit dashboard.
- **SQLite** en dev (via SQLModel ou sqlite3), Postgres/Supabase plus tard.
- **APScheduler** — le cycle automatique (détection + envoi) tourne tout seul.
- **LLM** (Anthropic Claude) — génération des messages personnalisés. En dev sans clé API, un mode `--dry-run` génère un message template.
- **Envois** : stubs en dev (on logge le message). Brancher Brevo/Twilio (SMS) + Resend/Brevo (email) plus tard.

## Architecture des fichiers

```
winback-resto/
  app/
    main.py          # FastAPI : endpoints + rendu des templates (lifespan, /health)
    config.py        # variables d'environnement, seuils
    models.py        # modèles de données (Restaurant, Customer, MessageLog)
    restaurants.py   # registre multi-tenant (cache des restaurants)
    data_source.py   # interface DataSource + MockDataSource (+ LightspeedDataSource plus tard)
    winback.py       # logique : qui est "endormi", qui relancer
    scoring.py       # score de priorité RFM + segmentation (feature signature, Pro)
    attribution.py   # détection des retours après relance (moteur du paiement au résultat)
    plans.py         # gating Free/Standard/Pro (canaux, scoring, quota) + upsell + outcome
    messaging.py     # message (IA/template, adapté au segment) + envoi email/SMS
    billing.py       # abonnements Stripe (statut, checkout, webhooks)
    db.py            # persistance SQLite (logs, opt-out, abonnements)
    charts.py        # mini-graphes SVG inline
    logging_config.py# logging structuré
    scheduler.py     # APScheduler : lance le cycle win-back périodiquement
    templates/       # vues Jinja2 (base, index, dashboard, unsubscribe)
  data/
    mock_customers.json   # clients fictifs (2 restaurants)
    restaurants.json      # config par restaurant
  tests/             # pytest (logique, multi-tenant, API, billing, charts)
  Dockerfile / Procfile / render.yaml   # déploiement
  pyproject.toml     # config ruff + pytest
  requirements.txt / .env.example / README.md / DEPLOY.md / CLAUDE.md
```

## Règles métier du win-back (MVP)

1. **Client "endormi"** = dernière visite il y a plus de `WINBACK_DAYS` jours (défaut 45), ET au moins 2 visites au total (on ne relance pas un client de passage unique).
2. **Anti-spam** : ne jamais relancer un client déjà contacté il y a moins de `COOLDOWN_DAYS` jours (défaut 30). Vérifier dans `MessageLog`.
3. **Personnalisation** : le message mentionne le prénom et, si dispo, le plat le plus commandé.
4. **Canal** : SMS si numéro dispo, sinon email. (MVP : on logge, on n'envoie pas vraiment.)
5. **Consentement** : ne relancer que les clients avec `marketing_opt_in = true` (RGPD).
6. **Traçabilité** : chaque envoi crée une ligne dans `MessageLog` (client, date, canal, contenu, statut).

## Roadmap de build (ordre conseillé pour Claude Code)

- [x] **Étape 1** — Modèles + `MockDataSource` qui charge `data/mock_customers.json`.
- [x] **Étape 2** — `winback.py` : fonction `find_lapsed_customers()` appliquant les règles ci-dessus.
- [x] **Étape 3** — `messaging.py` : `generate_message(customer)` (mode template d'abord, IA ensuite) + `send_message()` qui logge.
- [x] **Étape 4** — `main.py` : endpoint `GET /` (dashboard) + `POST /run-cycle`.
- [x] **Étape 5** — `scheduler.py` : exécuter le cycle tous les jours.
- [x] **Étape 6** — Persistance SQLite des `MessageLog` (`app/db.py`). Tests dans `tests/`.
- [x] **Étape B** — Désinscription RGPD : endpoint `/unsubscribe`, table `opt_out`, priorité dans le moteur.
- [x] **Étape C** — Multi-restaurant : `restaurant_id` partout, config par resto (`data/restaurants.json`), données/logs/opt-out isolés.
- [x] **Étape D** — Auth par token + dashboard amélioré (index, par resto, historique des envois).
- [x] **Étape A (code)** — Intégration email (Brevo) + SMS (Brevo/Twilio) dans `messaging.py`, mode `DRY_RUN` par défaut, tests mockés.
- [x] **Étape E** — Facturation Stripe (`app/billing.py`) : statut d'abonnement par resto, essai, checkout, webhooks, blocage des cycles si inactif. Tests mockés.
- [x] **Étape F (scaffolding)** — `Dockerfile`, `Procfile`, `render.yaml`, `DEPLOY.md`, config `DATABASE_URL` prête.
- [~] **Étape 7 (en cours)** — `LightspeedDataSource` : squelette posé dans `data_source.py` ; reste à brancher OAuth 2.0 + appel API réel quand les accès partenaires arrivent.
- [ ] **RESTE À FAIRE (toi, sur ta machine — voir PROMPT_SUITE.md)** :
  - Brancher les vraies clés (Brevo / Twilio / Anthropic / Stripe) dans `.env` et tester un envoi + un paiement réels (`DRY_RUN=false`).
  - Migration SQLite → Postgres (réimplémenter `app/db.py` avec `psycopg`, mêmes signatures) puis déployer.
  - Compléter `LightspeedDataSource` une fois le statut partenaire validé.

## Conventions

- Code et commentaires : noms en anglais, c'est plus standard.
- Tout seuil/config passe par `config.py` (lui-même depuis `.env`), jamais en dur dans la logique.
- Chaque nouvelle source de données implémente l'interface `DataSource` — ne jamais appeler une API POS directement ailleurs.
- Écrire au moins un test par règle métier du win-back.

## Définition de "terminé" pour le MVP

`uvicorn app.main:app` démarre, `/` affiche les clients endormis issus des données fictives, `POST /run-cycle` détecte + génère + logge les messages en respectant anti-spam et consentement, et le scheduler tourne tout seul.
