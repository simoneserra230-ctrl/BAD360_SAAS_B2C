"""
BAD360.ai — Menu Engineering (food)
Ricette costate, matrice popolarità×margine (Star/Plowhorse/Puzzle/Dog),
matrice allergeni Reg. UE 1169/2011, agente AI C7.7 "AI Menu Optimizer".

Gap #1 dell'analisi personas (chef, F&B manager, titolare, maître).
"""

import os
import json
from typing import Optional, List, Dict, Any

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.database import get_supabase
from backend.auth import require_user, UserProfile
from fastapi import Depends

router = APIRouter(prefix="/api/menu-engineering", tags=["Menu Engineering"])

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

# I 14 allergeni obbligatori — Allegato II Reg. UE 1169/2011
ALLERGENI_UE = [
    "glutine", "crostacei", "uova", "pesce", "arachidi", "soia",
    "latte", "frutta a guscio", "sedano", "senape", "sesamo",
    "anidride solforosa e solfiti", "lupini", "molluschi",
]


# ─── Demo data (piatti sardi — Hotel Baia Sardinia, coerente con la suite) ────

DEMO_RECIPES: List[Dict[str, Any]] = [
    {"id": "r1", "name": "Culurgiones al pomodoro", "category": "primi",
     "ingredients": [{"n": "culurgiones freschi", "qty": 200, "unit": "g", "cost": 2.80},
                     {"n": "salsa pomodoro", "qty": 80, "unit": "g", "cost": 0.35},
                     {"n": "pecorino", "qty": 20, "unit": "g", "cost": 0.42},
                     {"n": "basilico/olio", "qty": 1, "unit": "pz", "cost": 0.15}],
     "selling_price": 16.0, "monthly_sales": 310,
     "allergens": ["glutine", "uova", "latte"]},
    {"id": "r2", "name": "Fregola con arselle", "category": "primi",
     "ingredients": [{"n": "fregola", "qty": 90, "unit": "g", "cost": 0.55},
                     {"n": "arselle", "qty": 250, "unit": "g", "cost": 3.90},
                     {"n": "brodo/aromi", "qty": 1, "unit": "pz", "cost": 0.40},
                     {"n": "bottarga", "qty": 8, "unit": "g", "cost": 0.95}],
     "selling_price": 19.0, "monthly_sales": 185,
     "allergens": ["glutine", "molluschi", "pesce"]},
    {"id": "r3", "name": "Porceddu sardo", "category": "secondi",
     "ingredients": [{"n": "maialino", "qty": 350, "unit": "g", "cost": 6.80},
                     {"n": "mirto/contorno", "qty": 1, "unit": "pz", "cost": 0.90}],
     "selling_price": 24.0, "monthly_sales": 240,
     "allergens": []},
    {"id": "r4", "name": "Tagliata di tonno rosso", "category": "secondi",
     "ingredients": [{"n": "tonno rosso", "qty": 200, "unit": "g", "cost": 8.40},
                     {"n": "sesamo/verdure", "qty": 1, "unit": "pz", "cost": 1.10}],
     "selling_price": 26.0, "monthly_sales": 95,
     "allergens": ["pesce", "sesamo"]},
    {"id": "r5", "name": "Seadas con miele", "category": "dessert",
     "ingredients": [{"n": "seadas", "qty": 1, "unit": "pz", "cost": 1.60},
                     {"n": "miele corbezzolo", "qty": 25, "unit": "g", "cost": 0.55},
                     {"n": "olio frittura", "qty": 1, "unit": "pz", "cost": 0.20}],
     "selling_price": 9.0, "monthly_sales": 265,
     "allergens": ["glutine", "latte", "uova"]},
    {"id": "r6", "name": "Zuppa gallurese", "category": "primi",
     "ingredients": [{"n": "pane raffermo", "qty": 120, "unit": "g", "cost": 0.40},
                     {"n": "brodo di pecora", "qty": 200, "unit": "ml", "cost": 0.85},
                     {"n": "pecorino/formaggi", "qty": 80, "unit": "g", "cost": 1.65}],
     "selling_price": 14.0, "monthly_sales": 70,
     "allergens": ["glutine", "latte", "sedano"]},
    {"id": "r7", "name": "Insalata di mare", "category": "antipasti",
     "ingredients": [{"n": "polpo", "qty": 120, "unit": "g", "cost": 3.20},
                     {"n": "gamberi", "qty": 80, "unit": "g", "cost": 2.60},
                     {"n": "verdure/condimento", "qty": 1, "unit": "pz", "cost": 0.70}],
     "selling_price": 18.0, "monthly_sales": 150,
     "allergens": ["molluschi", "crostacei", "pesce", "sedano"]},
]


# ─── Calcoli ──────────────────────────────────────────────────────────────────

def enrich(recipe: dict) -> dict:
    """Aggiunge food cost, margine, incidenza a una ricetta."""
    fc = round(sum(float(i.get("cost") or 0) for i in (recipe.get("ingredients") or [])), 2)
    price = float(recipe.get("selling_price") or 0)
    margin = round(price - fc, 2)
    fc_pct = round(fc / price * 100, 1) if price else 0.0
    return {**recipe, "food_cost": fc, "margin": margin, "food_cost_pct": fc_pct}


def classify_matrix(recipes: List[dict]) -> List[dict]:
    """
    Matrice menu engineering (Kasavana-Smith):
    popolarità vs margine, soglie = medie del menu.
    STAR (alta pop, alto margine) | PLOWHORSE (alta pop, basso margine)
    PUZZLE (bassa pop, alto margine) | DOG (bassa pop, basso margine)
    """
    enriched = [enrich(r) for r in recipes]
    if not enriched:
        return []
    avg_margin = sum(r["margin"] for r in enriched) / len(enriched)
    # soglia popolarità: 70% della media vendite (regola Kasavana-Smith)
    avg_sales = sum(int(r.get("monthly_sales") or 0) for r in enriched) / len(enriched)
    pop_threshold = avg_sales * 0.7

    for r in enriched:
        hi_pop = int(r.get("monthly_sales") or 0) >= pop_threshold
        hi_margin = r["margin"] >= avg_margin
        r["class"] = ("STAR" if hi_pop and hi_margin else
                      "PLOWHORSE" if hi_pop else
                      "PUZZLE" if hi_margin else "DOG")
        r["azione"] = {
            "STAR": "Proteggi: mantieni qualità e visibilità in carta",
            "PLOWHORSE": "Alza il prezzo o riduci il food cost — si vende comunque",
            "PUZZLE": "Riposiziona in carta, fallo raccontare dalla sala, foto/descrizione",
            "DOG": "Rimuovi o reinventa — occupa spazio e magazzino",
        }[r["class"]]
    return enriched


# ─── Loader multi-tenant ────────────────────────────────────────────────────────

def _load_recipes(db, hotel_id: str) -> List[dict]:
    """Ricette dell'hotel dal token. Senza DB (dev locale) usa la demo; con DB
    ritorna SOLO le ricette di quell'hotel (multi-tenant blindato)."""
    if not db:
        return DEMO_RECIPES
    rows = db.table("me_recipes").select("*").eq("hotel_id", hotel_id).execute().data
    return rows or []


# ─── Models ───────────────────────────────────────────────────────────────────

class Ingredient(BaseModel):
    n: str
    qty: float = 0
    unit: str = "g"
    cost: float = Field(ge=0)


class RecipeIn(BaseModel):
    name: str
    category: str = "primi"
    ingredients: List[Ingredient]
    selling_price: float = Field(gt=0)
    monthly_sales: int = 0
    allergens: List[str] = []


# ─── Endpoints ────────────────────────────────────────────────────────────────

@router.get("/health")
def health():
    db = get_supabase()
    return {"module": "menu-engineering", "mode": "supabase" if db else "demo",
            "agent": "C7.7 AI Menu Optimizer", "allergeni_ue": len(ALLERGENI_UE)}


@router.get("/recipes")
def list_recipes(user: UserProfile = Depends(require_user)):
    db = get_supabase()
    return [enrich(r) for r in _load_recipes(db, user.hotel_id)]


@router.post("/recipes")
def create_recipe(payload: RecipeIn, user: UserProfile = Depends(require_user)):
    bad = [a for a in payload.allergens if a not in ALLERGENI_UE]
    if bad:
        raise HTTPException(status_code=422,
                            detail=f"Allergeni non in Allegato II Reg. UE 1169/2011: {bad}")
    data = payload.model_dump()
    data["hotel_id"] = user.hotel_id        # SEMPRE dal token (blindato)
    db = get_supabase()
    if db:
        res = db.table("me_recipes").insert(data).execute()
        return {"ok": True, "data": [enrich(r) for r in (res.data or [])]}
    data["id"] = f"r{len(DEMO_RECIPES)+1}"
    DEMO_RECIPES.append(data)
    return {"ok": True, "data": enrich(data), "mode": "demo"}


@router.delete("/recipes/{recipe_id}")
def delete_recipe(recipe_id: str, user: UserProfile = Depends(require_user)):
    db = get_supabase()
    if db:
        db.table("me_recipes").delete().eq("id", recipe_id).eq("hotel_id", user.hotel_id).execute()
    return {"ok": True}


@router.get("/matrix")
def matrix(user: UserProfile = Depends(require_user)):
    db = get_supabase()
    classified = classify_matrix(_load_recipes(db, user.hotel_id))
    summary = {}
    for c in ("STAR", "PLOWHORSE", "PUZZLE", "DOG"):
        summary[c] = sum(1 for r in classified if r["class"] == c)
    return {"items": classified, "summary": summary}


@router.get("/allergens")
def allergen_matrix(user: UserProfile = Depends(require_user)):
    """Matrice piatti × 14 allergeni UE — pronta per stampa/menu."""
    db = get_supabase()
    rows = _load_recipes(db, user.hotel_id)
    return {"allergeni": ALLERGENI_UE,
            "piatti": [{"name": r["name"], "category": r.get("category"),
                        "allergens": r.get("allergens") or []} for r in rows],
            "nota": "Allegato II Reg. UE 1169/2011 — la matrice va tenuta aggiornata e disponibile per il cliente"}


# ─── Agente C7.7 — AI MENU OPTIMIZER ─────────────────────────────────────────

OPTIMIZER_SYSTEM = (
    "Sei l'agente AI Menu Optimizer di BAD360.ai, esperto di menu engineering per la "
    "ristorazione italiana. Ricevi il menu classificato (matrice Kasavana-Smith) con "
    "food cost, margini e vendite. Produci raccomandazioni CONCRETE e quantificate: "
    "prezzi da ritoccare (di quanto, con stima impatto €/mese), piatti da riposizionare, "
    "piatti da eliminare, opportunità (es. ingrediente condiviso per nuovo piatto Star). "
    "Massimo 6 raccomandazioni, ordinate per impatto economico. Rispondi SOLO in JSON: "
    '{"recommendations": [{"piatto": "...", "azione": "...", "impatto_mensile_eur": 0}], '
    '"sintesi": "2 frasi"}'
)


def _fallback_recommendations(classified: List[dict]) -> dict:
    recs = []
    for r in classified:
        if r["class"] == "PLOWHORSE":
            new_price = round(r["selling_price"] * 1.06, 1)
            impact = round((new_price - r["selling_price"]) * r.get("monthly_sales", 0))
            recs.append({"piatto": r["name"],
                         "azione": f"Alza il prezzo da €{r['selling_price']} a €{new_price} (+6%): è popolare, regge il ritocco",
                         "impatto_mensile_eur": impact})
        elif r["class"] == "DOG":
            recs.append({"piatto": r["name"],
                         "azione": "Valuta la rimozione dalla carta: bassa popolarità e basso margine",
                         "impatto_mensile_eur": 0})
        elif r["class"] == "PUZZLE":
            est = round(r["margin"] * r.get("monthly_sales", 0) * 0.3)
            recs.append({"piatto": r["name"],
                         "azione": "Margine alto ma vende poco: spostalo in alto a destra in carta, foto e racconto della sala (+30% vendite stimato)",
                         "impatto_mensile_eur": est})
    recs.sort(key=lambda x: x["impatto_mensile_eur"], reverse=True)
    return {"recommendations": recs[:6],
            "sintesi": "Priorità: ritocco prezzi sui Plowhorse (impatto immediato), poi spinta sui Puzzle via sala e posizionamento in carta."}


@router.post("/ai/optimize")
async def ai_menu_optimizer(user: UserProfile = Depends(require_user)):
    """C7.7 AI Menu Optimizer: raccomandazioni quantificate sul menu corrente."""
    db = get_supabase()
    classified = classify_matrix(_load_recipes(db, user.hotel_id))

    if ANTHROPIC_API_KEY:
        try:
            compact = [{"nome": r["name"], "classe": r["class"], "prezzo": r["selling_price"],
                        "food_cost": r["food_cost"], "margine": r["margin"],
                        "vendite_mese": r.get("monthly_sales", 0)} for r in classified]
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={"x-api-key": ANTHROPIC_API_KEY,
                             "anthropic-version": "2023-06-01",
                             "content-type": "application/json"},
                    json={"model": "claude-haiku-4-5-20251001", "max_tokens": 900,
                          "system": OPTIMIZER_SYSTEM,
                          "messages": [{"role": "user",
                                        "content": json.dumps(compact, ensure_ascii=False)}]},
                )
            resp.raise_for_status()
            ai_block = json.loads(resp.json()["content"][0]["text"])
        except Exception:
            ai_block = _fallback_recommendations(classified)
    else:
        ai_block = _fallback_recommendations(classified)

    return {"agent": "C7.7 AI Menu Optimizer", **ai_block}
