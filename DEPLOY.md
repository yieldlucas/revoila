# Mettre Revoilà en ligne sur Render

Objectif : une URL publique (ex. `https://revoila.onrender.com`) avec la landing
et la collecte d'emails waitlist. Gratuit pour démarrer.

> Le déploiement se fait depuis **ton** compte Render + un dépôt Git. Suis les étapes
> ci-dessous — c'est rapide (~15 min la première fois).

---

## Étape 1 — Mettre le code sur GitHub

Depuis le dossier `winback-resto` :

```bash
git init
git add .
git commit -m "Revoilà — version initiale"
```

Crée un dépôt vide sur github.com (bouton « New repository », ne coche rien), puis :

```bash
git remote add origin https://github.com/TON-COMPTE/revoila.git
git branch -M main
git push -u origin main
```

(`.env`, la base et les caches sont déjà ignorés via `.gitignore` — aucun secret n'est poussé.)

## Étape 2 — Créer le service sur Render

1. Va sur render.com, crée un compte (connexion via GitHub conseillée).
2. **New > Blueprint**, sélectionne ton dépôt `revoila`. Render lit `render.yaml`
   et crée automatiquement le service web (plan Free).
3. Au moment du déploiement, renseigne les variables marquées « sync: false » (voir Étape 3).
4. Lance le déploiement. Au bout de 1-2 min, tu as une URL `https://revoila.onrender.com`.

*(Alternative sans Blueprint : New > Web Service → ton dépôt → Build `pip install -r requirements.txt`,
Start `uvicorn app.main:app --host 0.0.0.0 --port $PORT`, plan Free.)*

## Étape 3 — Variables d'environnement

Pour un **premier lancement waitlist**, le minimum suffit :

| Variable | Valeur | Rôle |
|---|---|---|
| `PUBLIC_BASE_URL` | `https://revoila.onrender.com` | URL publique (liens) |
| `WAITLIST_NOTIFY_EMAIL` | ton email | reçois chaque inscrit (capture durable) |
| `BREVO_API_KEY` | ta clé Brevo | nécessaire pour l'envoi des notifications |
| `EMAIL_FROM` | adresse expéditeur vérifiée chez Brevo | expéditeur |
| `DRY_RUN` | `true` au début | tant que tu testes, rien n'est envoyé |

Quand tu veux activer les vraies notifications waitlist : passe `DRY_RUN=false`
(avec `BREVO_API_KEY` + `EMAIL_FROM` renseignés). Les variables Stripe / SMS / IA
ne sont utiles que plus tard (abonnements, relances réelles).

## Étape 4 — Vérifier

- Ouvre l'URL → la landing s'affiche.
- `https://.../health` doit renvoyer `{"status":"ok","db":"ok"}`.
- Inscris un email test → tu le reçois sur `WAITLIST_NOTIFY_EMAIL`.

---

## À savoir sur le plan gratuit (important)

- **Mise en veille** : un service Free s'endort après 15 min sans trafic ; le premier
  visiteur après une veille attend ~30 s. Sans gravité pour une landing. (Le cycle de
  relance quotidien ne tourne pas de façon fiable sur Free — sans importance tant que
  l'intégration caisse n'est pas branchée.)
- **Base éphémère** : le SQLite est réinitialisé à chaque redéploiement. C'est pour ça
  qu'on t'envoie chaque inscrit par email (`WAITLIST_NOTIFY_EMAIL`) — **aucun email
  perdu**. Les données de démo (restaurants, logs) sont fictives, leur reset est sans effet.
- **SMTP bloqué** : Render Free bloque les ports SMTP (25/465/587). On n'est pas
  concerné : Brevo est appelé en **API HTTPS**, pas en SMTP.

## Quand passer en « vraiment durable »

Le jour où tu veux une base persistante (historique, comptes restaurants réels) :
- Ajoute une base **Render Postgres** (gratuite 30 jours, puis payante) ou Supabase,
- et implémente le backend Postgres derrière `app/db.py` (mêmes fonctions, voir
  `PROMPT_SUITE.md` → migration Postgres). Le reste du code ne bouge pas.
