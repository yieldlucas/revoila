# Ce qui reste à finir — toi + Claude Code

> Le code est complet et testé pour tout ce qui ne demande pas de secrets : moteur win-back,
> multi-restaurant, désinscription RGPD, auth, dashboard, et l'intégration email/SMS (écrite,
> en mode DRY_RUN). Il reste les parties qui ont besoin de TES comptes et clés, à faire sur ta machine.

---

## 1. Partie technique à remplir TOI-MÊME (comptes + clés)

Rien à coder ici, juste créer des comptes et coller les clés dans un fichier `.env`
(copie `.env.example`). **Ne committe jamais `.env`** (déjà dans `.gitignore`).

| Quoi | Où l'obtenir | Variable `.env` |
|---|---|---|
| Clé IA (messages générés) | console.anthropic.com | `ANTHROPIC_API_KEY` |
| Envoi d'emails | brevo.com (compte gratuit) | `BREVO_API_KEY`, `EMAIL_FROM` |
| Envoi de SMS | Brevo SMS ou twilio.com | `SMS_PROVIDER=brevo` ou `twilio` (+ identifiants) |
| Compte Stripe | stripe.com | (clés pour l'étape E) |
| Numéro/expéditeur SMS | Brevo / Twilio | `SMS_SENDER` ou `TWILIO_FROM` |

Pour tester un envoi réel : mets `DRY_RUN=false` dans `.env`, lance l'app, et fais un cycle
sur un client de test à TON adresse / TON numéro. Tant que `DRY_RUN=true`, rien ne part.

> Note légale : en France, pour envoyer des SMS/emails marketing il faut le consentement
> du client (déjà géré via `marketing_opt_in` + désinscription). Garde ça propre.

---

## 2. À finir dans Claude Code (étapes qui restent)

Les étapes E (Stripe) et F (scaffolding déploiement) sont **déjà codées et testées**.
Il reste surtout la migration Postgres et le branchement de la vraie caisse.

Ouvre le dossier dans VS Code, lance Claude Code, et colle ce bloc :

```
Lis CLAUDE.md en entier (spec + roadmap + conventions). Le projet est fonctionnel et testé
(python -m pytest -q doit passer : 27 tests). Implémente les étapes restantes, une par une,
en lançant les tests après chacune et en cochant la roadmap dans CLAUDE.md.

ÉTAPE F (migration) — Postgres
- Réimplémente app/db.py pour utiliser Postgres quand config.DATABASE_URL est défini
  (sinon SQLite en local), avec psycopg. GARDE EXACTEMENT les mêmes signatures de fonctions ;
  le reste du code ne doit pas changer. Décommente psycopg dans requirements.txt.
- Ajoute des tests (ou une CI) qui tournent contre une base Postgres jetable.

ÉTAPE 7 — Brancher la vraie caisse (quand tes accès Lightspeed sont validés)
- Complète LightspeedDataSource dans app/data_source.py : flux OAuth 2.0 + appel API réel
  + pagination, en mappant vers le modèle Customer (méthode _map déjà esquissée).
- Bascule get_default_source() pour utiliser Lightspeed quand un restaurant est connecté.
- Tests avec l'API mockée.

FINITIONS
- Ajoute un bouton "S'abonner" sur le dashboard qui appelle /r/{id}/billing/checkout.
- Améliore le dashboard (graphique simple de l'historique des envois).
```

---

## 3. En parallèle (business, pas du code)

1. **Déposer la Partner Application Lightspeed** (« Build an App ») — le plus long à valider.
2. **Interviewer 5-10 restaurateurs/chefs** de ton réseau : problème ressenti ? prix acceptable (~49-149€/mois) ? quel logiciel de caisse utilisent-ils vraiment ?
3. **Choisir le POS de départ** selon leurs réponses (Lightspeed = API propre, Zelty = marketplace FR).
