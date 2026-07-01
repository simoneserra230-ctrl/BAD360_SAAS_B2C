# ═══════════════════════════════════════════════════════════════════
#  BAD360.ai — RBAC: ruoli, categorie, permessi moduli
#  File: backend/roles.py
#
#  Divide i gestionali per TIPO DI UTENTE (richiesta founder):
#    dipendente · manager · direttore · consulente_interno · consulente_esterno
#    (+ owner = direttore con impostazioni, platform_admin = bypass)
#
#  - canonical_role(): normalizza i ruoli legacy del token
#  - allowed_modules(): cosa vede un ruolo nella suite (per il cockpit)
#  - require_module(key): dependency FastAPI che blocca (403) chi non ha accesso
#
#  Registrato in main.py:
#    from backend.roles import router as roles_router
#    app.include_router(roles_router)
# ═══════════════════════════════════════════════════════════════════

from __future__ import annotations
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

from backend.auth import require_user, get_current_user, UserProfile

router = APIRouter(prefix="/api/auth", tags=["Ruoli & Permessi"])

# ──────────────────────────────────────────────────────────────────
#  RUOLI CANONICI  (i 5 tipi utente + owner/admin)
# ──────────────────────────────────────────────────────────────────

ROLE_LABELS = {
    "dipendente":          "Dipendente (operativo)",
    "manager":             "Manager / Responsabile",
    "direttore":           "Direttore",
    "consulente_interno":  "Consulente interno",
    "consulente_esterno":  "Consulente esterno",
    "owner":               "Titolare",
    "platform_admin":      "Amministratore piattaforma",
}

# Ruoli legacy presenti nei token demo → ruolo canonico
LEGACY_ROLE_MAP = {
    "bar_manager":     "manager",
    "general_manager": "direttore",
    "owner":           "owner",
    "platform_admin":  "platform_admin",
    "user":            "dipendente",
    "staff":           "dipendente",
}


def canonical_role(role: Optional[str]) -> str:
    r = (role or "").strip().lower()
    if r in ROLE_LABELS:
        return r
    return LEGACY_ROLE_MAP.get(r, "dipendente")


def role_label(role: Optional[str]) -> str:
    return ROLE_LABELS.get(canonical_role(role), "Utente")


# ──────────────────────────────────────────────────────────────────
#  CATEGORIE  (tier di accesso) e MODULI
# ──────────────────────────────────────────────────────────────────
#  public     → vetrine, sempre visibili (anche senza login)
#  ops        → operatività quotidiana / inserimento dati
#  finance    → costi e margini operativi (food/drink cost, ordini, eventi)
#  direzione  → finanza strategica / P&L / revenue (solo direzione)
#  compliance → qualità, certificazioni, normative, quality manager
#  reputation → recensioni
#  training   → academy / formazione
#  admin      → impostazioni & billing

ROLE_CATEGORIES = {
    "dipendente":         {"public", "ops", "training"},
    "manager":            {"public", "ops", "finance", "compliance", "reputation", "training"},
    "direttore":          {"public", "ops", "finance", "direzione", "compliance", "reputation", "training"},
    "owner":              {"public", "ops", "finance", "direzione", "compliance", "reputation", "training", "admin"},
    "consulente_interno": {"public", "ops", "compliance", "training"},
    "consulente_esterno": {"public", "compliance"},
    "platform_admin":     {"*"},
}

# Catalogo moduli (key = identificatore stabile; page = file html della suite)
MODULE_CATALOG = [
    # ── operatività ──
    {"key": "haccp",          "label": "HACCP",                "icon": "🌡️", "page": "haccp.html",          "category": "ops"},
    {"key": "shelflife",      "label": "Shelf Life / FEFO",    "icon": "📦", "page": "shelflife.html",      "category": "ops"},
    {"key": "tracciabilita",  "label": "Tracciabilità lotti",  "icon": "🔗", "page": "tracciabilita.html",  "category": "ops"},
    {"key": "housekeeping",   "label": "Housekeeping",         "icon": "🛏️", "page": "housekeeping.html",   "category": "ops"},
    {"key": "shifts",         "label": "Turni & Staff",        "icon": "🗓️", "page": "shiftmanager.html",   "category": "ops"},
    {"key": "staffmatch",     "label": "Staff Match",          "icon": "🤝", "page": "barmanmatch.html",    "category": "ops"},
    {"key": "nc",             "label": "Non Conformità",       "icon": "⚠️", "page": "nc.html",             "category": "ops"},
    # ── finance operativa ──
    {"key": "menueng",        "label": "Menu Engineering",     "icon": "📊", "page": "menuengineering.html","category": "finance"},
    {"key": "drinkcost",      "label": "Beverage / Drink Cost","icon": "🍸", "page": "bevmanager.html",     "category": "finance"},
    {"key": "hotellerie",     "label": "Hotellerie F&B",       "icon": "🍽️", "page": "hotellerie.html",     "category": "finance"},
    {"key": "scm",            "label": "Supply Chain / Ordini","icon": "🚚", "page": "scmpro.html",         "category": "finance"},
    {"key": "events",         "label": "Eventi / CRM",         "icon": "🥂", "page": "events.html",         "category": "finance"},
    # ── direzione (P&L / strategico) ──
    {"key": "bi",             "label": "BI Dashboard",         "icon": "📈", "page": "BAD360.html#bidashboard", "category": "direzione"},
    {"key": "revenue",        "label": "Revenue Management",   "icon": "💰", "page": "BAD360.html#revenue",     "category": "direzione"},
    {"key": "bandi360",       "label": "Bandi & Finanza",      "icon": "🏛️", "page": "BAD360.html#bandi360",    "category": "direzione"},
    # ── compliance / qualità ──
    {"key": "cert",           "label": "Certificazioni",       "icon": "📜", "page": "cert.html",           "category": "compliance"},
    {"key": "qm",             "label": "Quality Manager",      "icon": "🧭", "page": "qm.html",             "category": "compliance"},
    {"key": "norme",          "label": "Normative",            "icon": "⚖️", "page": "norme.html",          "category": "compliance"},
    # ── reputation ──
    {"key": "reviews",        "label": "Recensioni",           "icon": "⭐", "page": "recensioni.html",     "category": "reputation"},
    # ── training ──
    {"key": "academy",        "label": "Academy",              "icon": "🎓", "page": "academy.html",        "category": "training"},
    # ── Layer Ospite & Ricavi (front/ricavi) ──
    {"key": "guest",          "label": "AI Guest Assistant",   "icon": "💬", "page": "guestassistant.html", "category": "ops"},
    {"key": "esperienze",     "label": "Upsell Esperienze",    "icon": "✨", "page": "esperienze.html",     "category": "finance"},
    {"key": "eventipro",      "label": "Wedding Coordinator",  "icon": "💍", "page": "eventipro.html",      "category": "finance"},
    {"key": "beverage",       "label": "Beverage Program",     "icon": "🍹", "page": "beverage.html",       "category": "finance"},
    {"key": "restaurant",     "label": "Restaurant Intelligence","icon": "🍽️","page": "restaurant.html",    "category": "finance"},
    {"key": "str",            "label": "STR / Case Vacanza",   "icon": "🏝️", "page": "str.html",            "category": "ops"},
    {"key": "turnicompliance","label": "Scheduling CCNL",      "icon": "⏱️", "page": "turnicompliance.html","category": "ops"},
    # ── Compliance cluster (nicchia normativa) ──
    {"key": "esg",            "label": "ESG / Sostenibilità",  "icon": "🌱", "page": "esg.html",            "category": "compliance"},
    {"key": "compliance",     "label": "Compliance Radar",     "icon": "🛡️", "page": "compliance.html",     "category": "compliance"},
    {"key": "adempimenti",    "label": "Adempimenti ricettivi","icon": "🧾", "page": "adempimenti.html",    "category": "compliance"},
    {"key": "eaa",            "label": "Accessibilità EAA",    "icon": "♿", "page": "eaa.html",            "category": "compliance"},
    {"key": "privacy",        "label": "Privacy & Whistleblowing","icon": "🔐","page": "privacy.html",      "category": "compliance"},
    {"key": "sgi",            "label": "Sistema di Gestione ISO","icon": "🧭", "page": "sistemagestione.html","category": "compliance"},
    # ── admin ──
    {"key": "settings",       "label": "Impostazioni & Billing","icon": "⚙️", "page": "hub.html",           "category": "admin"},
]

CATEGORY_BY_MODULE = {m["key"]: m["category"] for m in MODULE_CATALOG}

CATEGORY_LABELS = {
    "public": "Vetrina", "ops": "Operatività", "finance": "Costi & Margini",
    "direzione": "Direzione", "compliance": "Qualità & Compliance",
    "reputation": "Reputazione", "training": "Formazione", "admin": "Amministrazione",
}


# ──────────────────────────────────────────────────────────────────
#  LOGICA PERMESSI
# ──────────────────────────────────────────────────────────────────

def allowed_categories(role: Optional[str]) -> set:
    cats = ROLE_CATEGORIES.get(canonical_role(role), {"public"})
    if "*" in cats:
        return set(CATEGORY_LABELS.keys())
    return set(cats)


def can_access(role: Optional[str], module_key: str) -> bool:
    cat = CATEGORY_BY_MODULE.get(module_key)
    if cat is None:
        return False
    return cat in allowed_categories(role)


def allowed_modules(role: Optional[str]) -> list:
    cats = allowed_categories(role)
    return [m for m in MODULE_CATALOG if m["category"] in cats]


def require_module(module_key: str):
    """Dependency factory: 403 se il ruolo dell'utente non può accedere al modulo.
    Uso:  @router.get(..., dependencies=[Depends(require_module('finance_key'))])
       o:  async def ep(..., user: UserProfile = Depends(require_module('foodcost'))): ..."""
    async def _dep(user: UserProfile = Depends(require_user)) -> UserProfile:
        if not can_access(user.role, module_key):
            raise HTTPException(
                status_code=403,
                detail=f"Il ruolo '{role_label(user.role)}' non ha accesso a questo modulo.",
            )
        return user
    return _dep


# ──────────────────────────────────────────────────────────────────
#  ENDPOINT
# ──────────────────────────────────────────────────────────────────

@router.get("/permissions", summary="Permessi & moduli visibili per l'utente corrente")
async def my_permissions(user: Optional[UserProfile] = Depends(get_current_user)):
    """Usato dalla suite per mostrare a ogni tipo utente SOLO i suoi gestionali.
    Senza login → ruolo pubblico (solo vetrine)."""
    role = user.role if user else "public"
    cr = canonical_role(role) if user else "public"
    cats = allowed_categories(role) if user else {"public"}
    mods = [m for m in MODULE_CATALOG if m["category"] in cats] if user else \
           [m for m in MODULE_CATALOG if m["category"] == "public"]
    return {
        "authenticated": bool(user),
        "role": cr,
        "role_label": role_label(role) if user else "Visitatore",
        "categories": sorted(cats),
        "category_labels": CATEGORY_LABELS,
        "modules": mods,
        "module_keys": [m["key"] for m in mods],
    }


@router.get("/roles", summary="Catalogo ruoli e matrice categorie (riferimento)")
async def roles_catalog():
    return {
        "roles": [
            {"role": r, "label": ROLE_LABELS[r], "categories": sorted(allowed_categories(r))}
            for r in ROLE_LABELS
        ],
        "categories": CATEGORY_LABELS,
        "modules": MODULE_CATALOG,
    }
