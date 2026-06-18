"""API FastAPI : index, dashboard par restaurant (auth), cycle, facturation, RGPD.

Le rendu HTML utilise des templates Jinja2 (auto-échappés) dans app/templates/.
"""
from __future__ import annotations

import re
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path
from urllib.parse import quote

from fastapi import FastAPI, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from . import attribution, billing, charts, db, plans, scoring
from .data_source import get_default_source
from .logging_config import configure_logging, get_logger
from .messaging import choose_channel, generate_message, send_message
from .models import Restaurant
from .restaurants import get_all_restaurants, get_restaurant
from .scheduler import run_cycle
from .winback import estimate_recovered_revenue, find_lapsed_customers

logger = get_logger(__name__)

VALID_TIERS = ("pro",)
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))


def _score_color(score: int) -> str:
    """Couleur du badge de priorité selon le score (bleu soutenu = prioritaire)."""
    if score >= 66:
        return "#0071e3"
    if score >= 33:
        return "#5ea0f2"
    return "#aeb0b6"


templates.env.globals["score_color"] = _score_color


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Démarre le scheduler au lancement, l'arrête proprement à l'extinction."""
    configure_logging()
    db.init_db()
    from .scheduler import start_scheduler
    scheduler = start_scheduler()
    try:
        yield
    finally:
        scheduler.shutdown(wait=False)
        logger.info("Scheduler arrêté.")


app = FastAPI(title="Winback Resto — MVP", lifespan=lifespan)


def _check_token(restaurant_id: str, token: str) -> Restaurant:
    restaurant = get_restaurant(restaurant_id)
    if restaurant is None:
        raise HTTPException(status_code=404, detail="Restaurant inconnu")
    if not token or token != restaurant.dashboard_token:
        raise HTTPException(status_code=401, detail="Token invalide")
    return restaurant


def _wants_json(request: Request) -> bool:
    """Vrai si l'appelant préfère du JSON (API) plutôt qu'une page (navigateur)."""
    accept = request.headers.get("accept", "")
    return "application/json" in accept and "text/html" not in accept


@app.get("/health")
def health() -> dict:
    """Santé de l'app + connectivité base (utile pour l'hébergeur)."""
    try:
        db.init_db()
        db.count_logs("__healthcheck__")
    except Exception as e:  # pragma: no cover
        raise HTTPException(status_code=503, detail=f"DB indisponible : {e}") from e
    return {"status": "ok", "db": "ok"}


@app.get("/", response_class=HTMLResponse)
def landing(request: Request, joined: int = 0, exists: int = 0, error: int = 0):
    """Page vitrine publique + waitlist (validation de la demande)."""
    db.init_db()
    return templates.TemplateResponse(
        request=request,
        name="landing.html",
        context={
            "outcome": plans.OUTCOME,
            "pro_highlights": plans.PRO_HIGHLIGHTS,
            "pro_price": plans.PRO_PRICE,
            "waitlist_count": db.count_waitlist(),
            "joined": bool(joined),
            "exists": bool(exists),
            "error": bool(error),
        },
    )


@app.post("/waitlist")
def join_waitlist(email: str = Form(...), source: str = Form("landing")):
    """Enregistre un email de waitlist puis renvoie vers la landing avec un statut."""
    db.init_db()
    email = email.strip().lower()
    if not _EMAIL_RE.match(email):
        return RedirectResponse(url="/?error=1#waitlist", status_code=303)
    created = db.add_waitlist(email, source=source)
    if created:
        # Capture durable : on se notifie l'inscrit (ne bloque jamais la réponse).
        try:
            from .messaging import notify_waitlist_signup
            notify_waitlist_signup(email, db.count_waitlist())
        except Exception as e:
            logger.warning("Notification waitlist échouée : %s", e)
    flag = "joined=1" if created else "exists=1"
    return RedirectResponse(url=f"/?{flag}#waitlist", status_code=303)


@app.get("/demo", response_class=HTMLResponse)
def demo_index(request: Request):
    """Index de démonstration : liste des restaurants (dashboards)."""
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={"restaurants": get_all_restaurants()},
    )


@app.get("/r/{restaurant_id}", response_class=HTMLResponse)
def dashboard(request: Request, restaurant_id: str, token: str = Query("")):
    restaurant = _check_token(restaurant_id, token)
    db.init_db()

    customers = get_default_source().get_customers(restaurant_id)
    logs = db.get_logs(restaurant_id)
    opt_outs = db.get_opt_outs(restaurant_id)
    targets = find_lapsed_customers(customers, restaurant, logs=logs, opt_outs=opt_outs)
    roi = estimate_recovered_revenue(targets, restaurant)
    chart_svg = charts.bar_chart_svg(db.daily_send_counts(restaurant_id, days=14))

    feats = plans.features(restaurant.plan)

    # Paiement au résultat : retours déjà attribués + montant dû.
    outcome_billing = attribution.billing_summary(restaurant)

    # Quota Free du mois en cours.
    cap = plans.monthly_cap(restaurant.plan)
    quota = None
    if cap is not None:
        used = db.count_logs_since(restaurant_id, date.today().replace(day=1).isoformat())
        quota = {"cap": cap, "used": used, "remaining": max(0, cap - used)}

    if feats["scoring"]:
        ordered = scoring.prioritize(targets, restaurant)
        rows = [
            {"c": c, "score": s.value, "segment": s.segment,
             "channel": choose_channel(c, restaurant)}
            for c, s in ordered
        ]
    else:
        rows = [
            {"c": c, "score": None, "segment": None,
             "channel": choose_channel(c, restaurant)}
            for c in targets
        ]

    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={
            "restaurant": restaurant,
            "token": token,
            "sub": billing.subscription_view(restaurant_id),
            "features": feats,
            "pro_highlights": plans.PRO_HIGHLIGHTS,
            "pro_price": plans.PRO_PRICE,
            "outcome": plans.OUTCOME,
            "outcome_estimate": plans.outcome_estimate(roi["expected_returns"]),
            "outcome_billing": outcome_billing,
            "quota": quota,
            "roi": roi,
            "rows": rows,
            "logs": logs[:20],
            "total_logged": db.count_logs(restaurant_id),
            "chart_svg": chart_svg,
        },
    )


@app.post("/r/{restaurant_id}/run-cycle")
def trigger_cycle(request: Request, restaurant_id: str, token: str = Query("")):
    _check_token(restaurant_id, token)
    result = run_cycle(restaurant_id)
    if _wants_json(request):
        return JSONResponse(result)
    # Navigateur : on revient au dashboard mis à jour (pattern POST-redirect-GET).
    return RedirectResponse(
        url=f"/r/{restaurant_id}?token={token}", status_code=303
    )


@app.get("/r/{restaurant_id}/preview", response_class=HTMLResponse)
def preview(request: Request, restaurant_id: str, token: str = Query(""),
            segment: str = Query("all")):
    """Mode validation manuelle (Pro) : liste des clients à relancer, à cocher avant envoi."""
    restaurant = _check_token(restaurant_id, token)
    if not plans.has(restaurant.plan, "manual_approval"):
        # Réservé au Pro → on renvoie vers le dashboard (qui affiche l'upsell).
        return RedirectResponse(
            url=f"/r/{quote(restaurant_id)}?token={quote(token)}", status_code=303
        )
    db.init_db()
    customers = get_default_source().get_customers(restaurant_id)
    logs = db.get_logs(restaurant_id)
    opt_outs = db.get_opt_outs(restaurant_id)
    targets = find_lapsed_customers(
        customers, restaurant, logs=logs, opt_outs=opt_outs,
        annual_cap=plans.annual_cap(restaurant.plan),
    )
    rows = []
    for c, s in scoring.prioritize(targets, restaurant):
        if segment != "all" and s.segment != segment:
            continue
        rows.append({
            "c": c, "score": s.value, "segment": s.segment,
            "channel": choose_channel(c, restaurant),
            "message": generate_message(c, restaurant),
        })
    return templates.TemplateResponse(
        request=request, name="preview.html",
        context={"restaurant": restaurant, "token": token, "rows": rows,
                 "segment": segment, "segments": plans.SEGMENTS},
    )


@app.post("/r/{restaurant_id}/preview/send")
def preview_send(restaurant_id: str, token: str = Query(""),
                 ids: list[str] = Form(default=[])):
    """Envoie uniquement les clients cochés (validation manuelle, Pro)."""
    restaurant = _check_token(restaurant_id, token)
    if not billing.is_active(restaurant_id):
        raise HTTPException(status_code=402, detail="Essai terminé — abonnez-vous pour envoyer.")
    db.init_db()
    by_id = {c.id: c for c in get_default_source().get_customers(restaurant_id)}
    sent = 0
    for cid in ids:
        customer = by_id.get(cid)
        if customer is None:
            continue
        db.add_log(send_message(customer, restaurant, generate_message(customer, restaurant)))
        sent += 1
    return RedirectResponse(
        url=f"/r/{quote(restaurant_id)}?token={quote(token)}&sent={sent}", status_code=303
    )


@app.post("/r/{restaurant_id}/billing/checkout")
def billing_checkout(
    request: Request,
    restaurant_id: str,
    token: str = Query(""),
    tier: str = Query("standard"),
):
    """Démarre un abonnement Stripe : redirige vers le paiement (ou renvoie l'URL en JSON)."""
    restaurant = _check_token(restaurant_id, token)
    if tier not in VALID_TIERS:
        raise HTTPException(status_code=422, detail=f"Palier invalide : {tier}")
    try:
        url = billing.create_checkout_session(restaurant, tier=tier)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    if _wants_json(request):
        return {"checkout_url": url}
    return RedirectResponse(url=url, status_code=303)


@app.post("/stripe/webhook")
async def stripe_webhook(request: Request) -> dict:
    """Reçoit les événements Stripe et met à jour les abonnements."""
    payload = await request.body()
    sig = request.headers.get("Stripe-Signature", "")
    db.init_db()
    try:
        result = billing.handle_webhook(payload, sig)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Webhook invalide : {e}") from e
    return {"received": True, "result": result}


@app.get("/unsubscribe", response_class=HTMLResponse)
def unsubscribe(
    request: Request,
    restaurant_id: str = Query(...),
    customer_id: str = Query(...),
):
    """Désinscription RGPD : enregistre l'opt-out (aucune auth requise, lien public)."""
    restaurant = get_restaurant(restaurant_id)
    if restaurant is None:
        raise HTTPException(status_code=404, detail="Restaurant inconnu")
    db.init_db()
    db.add_opt_out(restaurant_id, customer_id)
    return templates.TemplateResponse(
        request=request, name="unsubscribe.html", context={"restaurant": restaurant}
    )
