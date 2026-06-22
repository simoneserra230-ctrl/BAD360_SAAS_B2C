"""
BAD360.ai — SaaS layer (parità con BA.IA)
─────────────────────────────────────────
Aggiunge il livello di monetizzazione/gestione mancante:
  • Paywall server-side (402) + quota AI per piano (429) sugli endpoint premium
  • Impostazioni Sito (solo admin): API key Anthropic, SMTP, Stripe — dal browser
  • Stripe billing (sandbox/live): checkout + webhook → attiva/scade il piano
  • Account utente (role-limited): piano + utilizzo + preferenze

Persistenza su Supabase (tabelle: site_settings, subscriptions, usage_counters,
user_prefs) con fallback in-memory se Supabase non è configurato.
Migration una-tantum: supabase/saas_schema.sql

Integrazione: in main.py →  from backend.saas import register_saas; register_saas(app)
"""

from __future__ import annotations
import os
import json
import datetime
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

try:
    from backend.database import get_supabase
except Exception:  # pragma: no cover
    def get_supabase():
        return None

try:
    from backend.auth import _decode_token
except Exception:  # pragma: no cover
    def _decode_token(_t):
        return None

router = APIRouter(prefix="/api", tags=["SaaS"])

# ── Config ────────────────────────────────────────────────────────────
ADMIN_EMAILS = {e.strip().lower() for e in os.getenv("ADMIN_EMAILS", "").split(",") if e.strip()}
ADMIN_ROLES = {"platform_admin", "owner", "developer", "admin"}
TRIAL_DAYS = 14
PAID_PLANS = ("free", "active", "paid", "pro", "base", "business")
PLAN_LIMITS_DEFAULT = {"trial": 40, "free": 10**9, "active": 1500, "base": 400,
                       "pro": 1500, "business": 6000, "expired": 0}

PAYWALL_PATHS = ("/api/ai/", "/api/agents", "/api/staff-match",
                 "/api/menu-engineering", "/api/menu-3d")

SETTING_KEYS = {
    "ANTHROPIC_API_KEY", "SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_PASS", "SMTP_FROM",
    "APP_URL", "PAYMENTS_ENABLED", "STRIPE_MODE", "STRIPE_SECRET_SANDBOX", "STRIPE_SECRET_LIVE",
    "STRIPE_PUB_SANDBOX", "STRIPE_PUB_LIVE", "STRIPE_PRICE_BASE", "STRIPE_PRICE_PRO", "STRIPE_WEBHOOK_SECRET",
}
SECRET_KEYS = {"ANTHROPIC_API_KEY", "SMTP_PASS", "STRIPE_SECRET_SANDBOX", "STRIPE_SECRET_LIVE", "STRIPE_WEBHOOK_SECRET"}

# Fallback in-memory (quando Supabase non è configurato: demo/locale)
_MEM = {"settings": {}, "subs": {}, "usage": {}, "prefs": {}}
_settings_cache = None


# ── util ──────────────────────────────────────────────────────────────
def _now():
    return datetime.datetime.utcnow()

def _period():
    return _now().strftime("%Y-%m")

def _is_admin(email, role=None):
    return (email or "").lower() in ADMIN_EMAILS or (role or "") in ADMIN_ROLES

def _sb():
    try:
        return get_supabase()
    except Exception:
        return None

def _mask(v):
    s = str(v or "")
    if not s:
        return ""
    return ("•" * max(2, min(12, len(s) - 4))) + s[-4:] if len(s) > 4 else "••••"


# ── settings (cache + Supabase/in-memory) ─────────────────────────────
def _apply_env(k, v):
    v = "" if v is None else str(v)
    os.environ[k] = v
    if k == "ANTHROPIC_API_KEY":
        try:
            import main as _m
            _m.ANTHROPIC_API_KEY = v
        except Exception:
            pass

def _settings_load():
    global _settings_cache
    sb = _sb()
    data = {}
    if sb:
        try:
            rows = sb.table("site_settings").select("key,value").execute().data or []
            data = {r["key"]: r["value"] for r in rows}
        except Exception as e:
            print(f"[SAAS] settings load err: {e}")
            data = dict(_MEM["settings"])
    else:
        data = dict(_MEM["settings"])
    _settings_cache = data
    for k, v in data.items():
        try:
            _apply_env(k, v)
        except Exception:
            pass
    return data

def _settings_all():
    if _settings_cache is None:
        _settings_load()
    return _settings_cache or {}

def _setting_set(k, v):
    v = "" if v is None else str(v)
    sb = _sb()
    if sb:
        try:
            sb.table("site_settings").upsert({"key": k, "value": v}, on_conflict="key").execute()
        except Exception as e:
            print(f"[SAAS] setting set err: {e}")
    else:
        _MEM["settings"][k] = v
    if _settings_cache is not None:
        _settings_cache[k] = v
    _apply_env(k, v)


# ── subscriptions ─────────────────────────────────────────────────────
def _sub_get(email):
    email = (email or "").lower()
    if not email:
        return {"email": "", "plan": "trial", "trial_ends_at": None}
    sb = _sb()
    row = None
    if sb:
        try:
            r = sb.table("subscriptions").select("*").eq("email", email).limit(1).execute()
            row = (r.data or [None])[0]
        except Exception as e:
            print(f"[SAAS] sub get err: {e}")
    else:
        row = _MEM["subs"].get(email)
    if not row:
        row = {"email": email, "plan": "trial",
               "trial_ends_at": (_now() + datetime.timedelta(days=TRIAL_DAYS)).isoformat()}
        if sb:
            try:
                sb.table("subscriptions").upsert(row, on_conflict="email").execute()
            except Exception as e:
                print(f"[SAAS] sub create err: {e}")
        else:
            _MEM["subs"][email] = row
    return row

def _sub_set_plan(email, plan):
    email = (email or "").lower()
    sb = _sb()
    if sb:
        try:
            sb.table("subscriptions").upsert({"email": email, "plan": plan}, on_conflict="email").execute()
        except Exception as e:
            print(f"[SAAS] sub set err: {e}")
    else:
        _MEM["subs"].setdefault(email, {"email": email})["plan"] = plan

def _has_access(email, role):
    if _is_admin(email, role):
        return True
    sub = _sub_get(email)
    plan = (sub.get("plan") or "trial")
    if plan in PAID_PLANS:
        return True
    if plan == "expired":
        return False
    te = sub.get("trial_ends_at")
    if te:
        try:
            return _now().isoformat() < str(te)
        except Exception:
            return True
    return True

def _plan_limit(email, role):
    if _is_admin(email, role):
        return 10**9
    plan = (_sub_get(email).get("plan") or "trial").lower()
    env = os.getenv("LIMIT_" + plan.upper(), "")
    if env.isdigit():
        return int(env)
    return PLAN_LIMITS_DEFAULT.get(plan, 40)


# ── usage / quota ─────────────────────────────────────────────────────
def _usage_get(email):
    email = (email or "").lower()
    period = _period()
    sb = _sb()
    if sb:
        try:
            r = sb.table("usage_counters").select("count").eq("email", email).eq("period", period).limit(1).execute()
            d = r.data or []
            return (d[0]["count"] if d else 0) or 0
        except Exception:
            return 0
    return _MEM["usage"].get((email, period), 0)

def _usage_inc(email):
    email = (email or "").lower()
    period = _period()
    sb = _sb()
    if sb:
        try:
            cur = _usage_get(email)
            sb.table("usage_counters").upsert({"email": email, "period": period, "count": cur + 1},
                                              on_conflict="email,period").execute()
        except Exception as e:
            print(f"[SAAS] usage inc err: {e}")
    else:
        _MEM["usage"][(email, period)] = _MEM["usage"].get((email, period), 0) + 1


# ── preferenze utente ─────────────────────────────────────────────────
def _prefs_get(email):
    email = (email or "").lower()
    sb = _sb()
    if sb:
        try:
            r = sb.table("user_prefs").select("key,value").eq("email", email).execute()
            return {x["key"]: x["value"] for x in (r.data or [])}
        except Exception:
            return {}
    return _MEM["prefs"].get(email, {})

def _prefs_set(email, key, value):
    email = (email or "").lower()
    sb = _sb()
    if sb:
        try:
            sb.table("user_prefs").upsert({"email": email, "key": key, "value": str(value)},
                                          on_conflict="email,key").execute()
        except Exception as e:
            print(f"[SAAS] prefs set err: {e}")
    else:
        _MEM["prefs"].setdefault(email, {})[key] = str(value)


# ── email ─────────────────────────────────────────────────────────────
def _send_email(to, subject, html):
    host = os.environ.get("SMTP_HOST", "")
    port = int(os.environ.get("SMTP_PORT", "587") or 587)
    user = os.environ.get("SMTP_USER", "")
    pwd = os.environ.get("SMTP_PASS", "")
    frm = os.environ.get("SMTP_FROM", user)
    if not host:
        raise ValueError("SMTP non configurato")
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = frm
    msg["To"] = to
    msg.attach(MIMEText(html, "html", "utf-8"))
    with smtplib.SMTP(host, port, timeout=15) as s:
        s.ehlo(); s.starttls()
        if user:
            s.login(user, pwd)
        s.sendmail(frm, to, msg.as_string())


# ── stripe helpers ────────────────────────────────────────────────────
def _stripe_available():
    try:
        import stripe  # noqa: F401
        return True
    except Exception:
        return False

def _stripe_keys():
    if os.environ.get("STRIPE_MODE", "sandbox") == "live":
        return os.environ.get("STRIPE_SECRET_LIVE", ""), os.environ.get("STRIPE_PUB_LIVE", "")
    return os.environ.get("STRIPE_SECRET_SANDBOX", ""), os.environ.get("STRIPE_PUB_SANDBOX", "")

def _payments_on():
    sec, _ = _stripe_keys()
    return os.environ.get("PAYMENTS_ENABLED", "0") == "1" and bool(sec) and _stripe_available()


# ── auth da request ───────────────────────────────────────────────────
def _user_from_request(request: Request):
    auth = request.headers.get("authorization") or ""
    tok = None
    if auth.lower().startswith("bearer "):
        tok = auth.split(None, 1)[1]
    tok = tok or request.headers.get("x-auth-token")
    if not tok:
        return None
    p = _decode_token(tok)
    if not p:
        return None
    email = p.get("email", "")
    role = p.get("role", "user")
    return {"id": p.get("sub", ""), "email": email, "name": p.get("name", ""),
            "role": role, "is_admin": _is_admin(email, role)}


# ══════════════════════════ MIDDLEWARE ════════════════════════════════
async def _paywall_mw(request: Request, call_next):
    is_ai = request.method == "POST" and any(seg in request.url.path for seg in PAYWALL_PATHS)
    user = None
    if is_ai:
        try:
            user = _user_from_request(request)
            if user and user.get("email"):
                if not _has_access(user["email"], user["role"]):
                    return JSONResponse({"ok": False, "code": "no_access",
                                         "error": "Prova terminata o abbonamento non attivo. Abbonati per continuare."}, 402)
                if _usage_get(user["email"]) >= _plan_limit(user["email"], user["role"]):
                    return JSONResponse({"ok": False, "code": "quota",
                                         "error": "Hai raggiunto il limite di operazioni AI del tuo piano per questo mese."}, 429)
        except Exception as e:
            print(f"[SAAS] paywall mw err: {e}")
    response = await call_next(request)
    if is_ai and user and user.get("email"):
        try:
            if getattr(response, "status_code", 500) == 200:
                _usage_inc(user["email"])
        except Exception:
            pass
    return response


# ══════════════════════════ ENDPOINTS ═════════════════════════════════
@router.get("/account/profile")
async def account_profile(request: Request):
    u = _user_from_request(request)
    if not u:
        return JSONResponse({"ok": False, "error": "Non autenticato"}, 401)
    sub = _sub_get(u["email"])
    used = _usage_get(u["email"])
    limit = _plan_limit(u["email"], u["role"])
    prefs = _prefs_get(u["email"])
    return {"ok": True, "user": u,
            "plan": sub.get("plan"), "trial_ends_at": sub.get("trial_ends_at"),
            "access": _has_access(u["email"], u["role"]),
            "usage": {"used": used, "limit": limit, "period": _period(), "unlimited": limit >= 10**9},
            "preferences": {"email_notifications": prefs.get("email_notifications", "1") == "1"},
            "payments_enabled": _payments_on()}

@router.post("/account/preferences")
async def account_preferences(request: Request):
    u = _user_from_request(request)
    if not u:
        return JSONResponse({"ok": False, "error": "Non autenticato"}, 401)
    body = await request.json()
    _prefs_set(u["email"], "email_notifications", "1" if body.get("email_notifications") else "0")
    return {"ok": True}

@router.get("/admin/settings")
async def admin_settings_get(request: Request):
    u = _user_from_request(request)
    if not u or not u.get("is_admin"):
        return JSONResponse({"ok": False, "error": "Non autorizzato"}, 403)
    s = _settings_all()
    def g(k, d=""): return s.get(k) or os.environ.get(k, d)
    def has(k): return bool(s.get(k) or os.environ.get(k))
    return {"ok": True, "settings": {
        "anthropic_api_key_configured": has("ANTHROPIC_API_KEY"),
        "anthropic_api_key_mask": _mask(g("ANTHROPIC_API_KEY")),
        "smtp_host": g("SMTP_HOST"), "smtp_port": g("SMTP_PORT", "587"),
        "smtp_user": g("SMTP_USER"), "smtp_from": g("SMTP_FROM"),
        "smtp_pass_configured": has("SMTP_PASS"), "smtp_configured": has("SMTP_HOST"),
        "app_url": g("APP_URL"),
        "payments_enabled": g("PAYMENTS_ENABLED", "0") == "1", "payments_live": _payments_on(),
        "stripe_lib": _stripe_available(), "stripe_mode": g("STRIPE_MODE", "sandbox"),
        "stripe_pub_sandbox": g("STRIPE_PUB_SANDBOX"), "stripe_pub_live": g("STRIPE_PUB_LIVE"),
        "stripe_secret_sandbox_configured": has("STRIPE_SECRET_SANDBOX"),
        "stripe_secret_live_configured": has("STRIPE_SECRET_LIVE"),
        "stripe_price_base": g("STRIPE_PRICE_BASE"), "stripe_price_pro": g("STRIPE_PRICE_PRO"),
        "stripe_webhook_secret_configured": has("STRIPE_WEBHOOK_SECRET"),
        "supabase": bool(_sb()),
    }}

@router.post("/admin/settings")
async def admin_settings_set(request: Request):
    u = _user_from_request(request)
    if not u or not u.get("is_admin"):
        return JSONResponse({"ok": False, "error": "Non autorizzato"}, 403)
    body = await request.json()
    incoming = body.get("settings") if isinstance(body.get("settings"), dict) else body
    saved = []
    for k, v in (incoming or {}).items():
        K = str(k).upper()
        if K not in SETTING_KEYS:
            continue
        if K in SECRET_KEYS and (v is None or str(v).strip() == "" or "•" in str(v)):
            continue
        _setting_set(K, v)
        saved.append(K)
    return {"ok": True, "saved": saved}

@router.post("/admin/smtp/test")
async def admin_smtp_test(request: Request):
    u = _user_from_request(request)
    if not u or not u.get("is_admin"):
        return JSONResponse({"ok": False, "error": "Non autorizzato"}, 403)
    body = await request.json()
    to = (body.get("to") or u["email"]).strip()
    if not os.environ.get("SMTP_HOST"):
        return {"ok": False, "error": "SMTP non configurato"}
    try:
        _send_email(to, "Test BAD360", "<p>Configurazione SMTP funzionante ✓</p>")
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}

@router.post("/admin/grant-license")
async def admin_grant_license(request: Request):
    u = _user_from_request(request)
    if not u or not u.get("is_admin"):
        return JSONResponse({"ok": False, "error": "Non autorizzato"}, 403)
    body = await request.json()
    target = (body.get("email") or "").strip().lower()
    plan = (body.get("plan") or "").strip().lower()
    if not target or plan not in ("free", "active", "trial", "expired"):
        return JSONResponse({"ok": False, "error": "Email o piano non valido"}, 400)
    _sub_set_plan(target, plan)
    return {"ok": True, "email": target, "plan": plan}

@router.get("/billing/config")
async def billing_config():
    sec, pub = _stripe_keys()
    return {"ok": True, "enabled": _payments_on(), "mode": os.environ.get("STRIPE_MODE", "sandbox"),
            "publishable_key": pub,
            "prices": {"base": os.environ.get("STRIPE_PRICE_BASE", ""), "pro": os.environ.get("STRIPE_PRICE_PRO", "")}}

@router.post("/billing/checkout")
async def billing_checkout(request: Request):
    u = _user_from_request(request)
    if not u:
        return JSONResponse({"ok": False, "error": "Autenticazione richiesta"}, 401)
    if not _payments_on():
        return JSONResponse({"ok": False, "error": "Pagamenti non attivi (configurali dal pannello admin)"}, 400)
    body = await request.json()
    plan = (body.get("plan") or "pro").lower()
    price = os.environ.get("STRIPE_PRICE_PRO", "") if plan == "pro" else os.environ.get("STRIPE_PRICE_BASE", "")
    if not price:
        return JSONResponse({"ok": False, "error": "Price ID non configurato"}, 400)
    sec, _ = _stripe_keys()
    import stripe
    stripe.api_key = sec
    app_url = (os.environ.get("APP_URL") or "http://localhost:8000").split("?")[0]
    try:
        sess = stripe.checkout.Session.create(
            mode="subscription",
            line_items=[{"price": price, "quantity": 1}],
            customer_email=u["email"],
            client_reference_id=u["id"],
            success_url=app_url + "?paid=1",
            cancel_url=app_url + "?canceled=1",
        )
        return {"ok": True, "url": sess.url}
    except Exception as e:
        print(f"[SAAS] checkout err: {e}")
        return JSONResponse({"ok": False, "error": str(e)}, 400)

@router.post("/billing/webhook")
async def billing_webhook(request: Request):
    if not _stripe_available():
        return JSONResponse({"ok": False}, 400)
    import stripe
    sec, _ = _stripe_keys()
    stripe.api_key = sec
    payload = await request.body()
    sig = request.headers.get("stripe-signature", "")
    wh = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
    try:
        if wh:
            event = stripe.Webhook.construct_event(payload, sig, wh)
        else:
            event = json.loads(payload.decode("utf-8"))
    except Exception as e:
        print(f"[SAAS] webhook verify err: {e}")
        return JSONResponse({"ok": False, "error": "firma non valida"}, 400)
    etype = event["type"] if isinstance(event, dict) else event.type
    obj = (event.get("data", {}) or {}).get("object", {}) if isinstance(event, dict) else event.data.object
    email = (obj.get("customer_email") or (obj.get("customer_details", {}) or {}).get("email") or "").lower()
    try:
        if etype in ("checkout.session.completed", "customer.subscription.created",
                     "customer.subscription.updated", "invoice.paid") and email:
            _sub_set_plan(email, "active")
            print(f"[SAAS] plan ACTIVE per {email}")
        elif etype == "customer.subscription.deleted" and email:
            _sub_set_plan(email, "expired")
            print(f"[SAAS] plan EXPIRED per {email}")
    except Exception as e:
        print(f"[SAAS] webhook apply err: {e}")
    return {"ok": True}


# ══════════════════════════ REGISTER ══════════════════════════════════
def register_saas(app):
    """Da chiamare in main.py dopo gli altri include_router."""
    app.include_router(router)
    app.middleware("http")(_paywall_mw)

    @app.on_event("startup")
    async def _saas_startup():
        try:
            _settings_load()
            print("[SAAS] layer SaaS attivo (settings caricate)")
        except Exception as e:
            print(f"[SAAS] startup err: {e}")
