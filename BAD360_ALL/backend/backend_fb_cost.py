"""
BAD.S Unified Platform — Modulo Food & Beverage Cost
Router FastAPI per la gestione completa dei costi F&B

Endpoints:
  POST /api/fb/ingrediente          — Crea/aggiorna ingrediente
  GET  /api/fb/ingredienti          — Lista ingredienti hotel
  POST /api/fb/ricetta              — Crea ricetta con distinta base
  GET  /api/fb/ricette              — Lista ricette con food cost %
  GET  /api/fb/ricetta/{id}/cost    — Calcola costo dettagliato ricetta
  POST /api/fb/vendita              — Registra vendita (aggiorna cost reale)
  GET  /api/fb/analysis             — Analisi food/bev cost periodica
  GET  /api/fb/bcg-matrix           — Matrice BCG voci menu
  POST /api/fb/report               — Genera report periodico con AI
  POST /api/ai/fb-advisor           — AI Advisor F&B cost
"""

from typing import Optional, List, Dict, Any
from datetime import date, datetime
from pydantic import BaseModel, Field
from fastapi import APIRouter, HTTPException
import httpx
import json
import os

router = APIRouter(prefix="/api/fb", tags=["Food & Beverage Cost"])

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

# ─── Benchmark di settore (da /api/analytics/kpi-benchmark) ──────────────────
FOOD_COST_BENCHMARK = {3: 35.0, 4: 32.0, 5: 28.0}
BEV_COST_BENCHMARK  = {"cocktail_bar": 22.0, "wine_bar": 30.0, "ristorante": 28.0}


# ─── Pydantic Models ──────────────────────────────────────────────────────────

class IngredienteCreate(BaseModel):
    hotel_id:      str
    nome:          str
    categoria:     str   # spirits | vini | birre | analcolici | carne | pesce | verdure | latticini | secchi
    unita_misura:  str = "kg"
    costo_unitario: float = Field(..., gt=0, description="Costo per unità di misura in EUR")
    fornitore_id:  Optional[str] = None
    allergeni:     List[str] = []
    note:          Optional[str] = None

class RicettaIngredienteInput(BaseModel):
    ingrediente_id: str
    quantita:       float = Field(..., gt=0)
    note:           Optional[str] = None

class RicettaCreate(BaseModel):
    hotel_id:       str
    nome:           str
    tipo:           str   # food | beverage | cocktail | mocktail
    categoria:      Optional[str] = None
    prezzo_vendita: float = Field(..., gt=0)
    iva_pct:        float = 10.0
    ingredienti:    List[RicettaIngredienteInput]
    tempo_prep_min: Optional[int] = None
    bcg_popolarita: str = "media"   # alta | media | bassa
    note_allergie:  Optional[str] = None

class VenditaCreate(BaseModel):
    hotel_id:         str
    ricetta_id:       str
    data_vendita:     date = Field(default_factory=date.today)
    turno:            str = "pranzo"
    quantita_venduta: int = Field(1, ge=1)
    prezzo_effettivo: Optional[float] = None  # se diverso dal prezzo ricetta

class FBAnalysisRequest(BaseModel):
    hotel_id:   str
    data_da:    date
    data_a:     date
    stelle:     int = Field(4, ge=1, le=5)

class FBReportRequest(BaseModel):
    hotel_id:   str
    data_da:    date
    data_a:     date
    stelle:     int = 4
    generate_ai: bool = True


# ─── Helper: Supabase client ──────────────────────────────────────────────────

def sb_headers() -> dict:
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }

async def sb_get(table: str, params: dict) -> list:
    if not (SUPABASE_URL and SUPABASE_KEY):
        return []
    async with httpx.AsyncClient() as client:
        r = await client.get(f"{SUPABASE_URL}/rest/v1/{table}", headers=sb_headers(), params=params)
        return r.json() if r.status_code == 200 else []

async def sb_post(table: str, payload: dict) -> dict:
    if not (SUPABASE_URL and SUPABASE_KEY):
        raise HTTPException(503, "Supabase non configurato — usa .env")
    async with httpx.AsyncClient() as client:
        r = await client.post(f"{SUPABASE_URL}/rest/v1/{table}", headers=sb_headers(), json=payload)
        if r.status_code not in (200, 201):
            raise HTTPException(502, f"Supabase error: {r.text}")
        rows = r.json()
        return rows[0] if rows else {}


# ─── Endpoints: Ingredienti ───────────────────────────────────────────────────

@router.post("/ingrediente", summary="Crea o aggiorna un ingrediente")
async def crea_ingrediente(req: IngredienteCreate):
    """
    Crea un ingrediente nell'anagrafica del hotel.
    Il costo_unitario è riferito all'unità di misura (es: €/kg, €/cl, €/pz).
    """
    payload = req.dict()
    result = await sb_post("fb_ingredienti", payload)
    return {"success": True, "ingrediente": result}


@router.get("/ingredienti", summary="Lista ingredienti hotel")
async def lista_ingredienti(hotel_id: str, categoria: Optional[str] = None):
    """
    Restituisce tutti gli ingredienti attivi del hotel.
    Filtrabile per categoria (spirits, vini, carne, ecc.).
    """
    params = {"hotel_id": f"eq.{hotel_id}", "attivo": "eq.true", "order": "categoria,nome"}
    if categoria:
        params["categoria"] = f"eq.{categoria}"
    ingredienti = await sb_get("fb_ingredienti", params)
    return {"ingredienti": ingredienti, "totale": len(ingredienti)}


# ─── Endpoints: Ricette & Costing ────────────────────────────────────────────

@router.post("/ricetta", summary="Crea ricetta con distinta base ingredienti")
async def crea_ricetta(req: RicettaCreate):
    """
    Crea una ricetta e ne calcola il costo teorico sommando gli ingredienti.

    Food Cost % = (Somma costi ingredienti) / prezzo_vendita * 100
    Il trigger Supabase ricalcola automaticamente ad ogni modifica ingredienti.
    """
    # 1. Recupera costi ingredienti
    costo_totale = 0.0
    allergeni_ricetta = set()

    for item in req.ingredienti:
        rows = await sb_get("fb_ingredienti", {"id": f"eq.{item.ingrediente_id}", "select": "costo_unitario,allergeni,nome"})
        if not rows:
            raise HTTPException(404, f"Ingrediente {item.ingrediente_id} non trovato")
        ing = rows[0]
        costo_totale += float(ing["costo_unitario"]) * item.quantita
        if ing.get("allergeni"):
            allergeni_ricetta.update(ing["allergeni"])

    food_cost_pct = round((costo_totale / req.prezzo_vendita) * 100, 2) if req.prezzo_vendita > 0 else 0

    # 2. Crea ricetta
    ricetta_payload = {
        "hotel_id":       req.hotel_id,
        "nome":           req.nome,
        "tipo":           req.tipo,
        "categoria":      req.categoria,
        "prezzo_vendita": req.prezzo_vendita,
        "iva_pct":        req.iva_pct,
        "costo_ricetta":  round(costo_totale, 4),
        "food_cost_pct":  food_cost_pct,
        "tempo_prep_min": req.tempo_prep_min,
        "bcg_popolarita": req.bcg_popolarita,
        "note_allergie":  req.note_allergie or ", ".join(sorted(allergeni_ricetta)) or None,
    }
    ricetta = await sb_post("fb_ricette", ricetta_payload)
    ricetta_id = ricetta.get("id")

    # 3. Inserisci distinta base
    for item in req.ingredienti:
        await sb_post("fb_ricette_ingredienti", {
            "ricetta_id":      ricetta_id,
            "ingrediente_id":  item.ingrediente_id,
            "quantita":        item.quantita,
            "note":            item.note,
        })

    # 4. Valutazione immediata
    benchmark = FOOD_COST_BENCHMARK.get(4, 32.0)
    warning = food_cost_pct > benchmark

    return {
        "success":       True,
        "ricetta":       ricetta,
        "food_cost_pct": food_cost_pct,
        "costo_ricetta": round(costo_totale, 4),
        "allergeni":     sorted(allergeni_ricetta),
        "analisi": {
            "benchmark_4stelle": benchmark,
            "fuori_target":      warning,
            "margine_lordo_eur": round(req.prezzo_vendita - costo_totale, 2),
            "margine_lordo_pct": round(100 - food_cost_pct, 2),
            "messaggio": (
                f"⚠️ Food cost {food_cost_pct}% sopra il benchmark {benchmark}% per 4★. "
                "Verifica ingredienti o prezzo di vendita."
                if warning else
                f"✅ Food cost {food_cost_pct}% in linea con benchmark {benchmark}% per 4★."
            )
        }
    }


@router.get("/ricette", summary="Lista ricette con food cost calcolato")
async def lista_ricette(hotel_id: str, tipo: Optional[str] = None, stelle: int = 4):
    """Lista ricette attive con food cost % e comparazione benchmark."""
    params = {"hotel_id": f"eq.{hotel_id}", "attiva": "eq.true", "order": "tipo,nome"}
    if tipo:
        params["tipo"] = f"eq.{tipo}"

    ricette = await sb_get("fb_ricette", params)
    benchmark = FOOD_COST_BENCHMARK.get(stelle, 32.0)

    for r in ricette:
        fc = float(r.get("food_cost_pct") or 0)
        r["fuori_target"]     = fc > benchmark
        r["margine_lordo_pct"] = round(100 - fc, 2)
        r["benchmark"]        = benchmark

    return {
        "ricette":           ricette,
        "totale":            len(ricette),
        "benchmark_stelle":  benchmark,
        "fuori_target_n":    sum(1 for r in ricette if r["fuori_target"]),
    }


@router.get("/ricetta/{ricetta_id}/cost", summary="Calcola costo dettagliato ricetta")
async def dettaglio_costo_ricetta(ricetta_id: str):
    """
    Restituisce il dettaglio completo dei costi per singola ricetta:
    lista ingredienti, costo per ingrediente, totale, food cost %.
    """
    ricette = await sb_get("fb_ricette", {"id": f"eq.{ricetta_id}"})
    if not ricette:
        raise HTTPException(404, "Ricetta non trovata")
    ricetta = ricette[0]

    # Ingredienti con costi
    righe = await sb_get(
        "fb_ricette_ingredienti",
        {"ricetta_id": f"eq.{ricetta_id}", "select": "quantita,note,ingrediente_id,fb_ingredienti(nome,categoria,unita_misura,costo_unitario,allergeni)"}
    )

    dettaglio = []
    costo_calcolato = 0.0
    for riga in righe:
        ing = riga.get("fb_ingredienti") or {}
        costo_riga = float(ing.get("costo_unitario", 0)) * float(riga["quantita"])
        costo_calcolato += costo_riga
        dettaglio.append({
            "ingrediente":    ing.get("nome"),
            "categoria":      ing.get("categoria"),
            "quantita":       riga["quantita"],
            "unita":          ing.get("unita_misura"),
            "costo_unitario": ing.get("costo_unitario"),
            "costo_riga":     round(costo_riga, 4),
            "pct_sul_totale": 0,  # calcolato dopo
            "note":           riga.get("note"),
        })

    # Calcola % per ingrediente sul totale ricetta
    for d in dettaglio:
        d["pct_sul_totale"] = round((d["costo_riga"] / costo_calcolato) * 100, 1) if costo_calcolato else 0

    prezzo = float(ricetta.get("prezzo_vendita", 1))
    fc_pct = round((costo_calcolato / prezzo) * 100, 2) if prezzo else 0

    return {
        "ricetta":        ricetta,
        "ingredienti":    sorted(dettaglio, key=lambda x: x["costo_riga"], reverse=True),
        "costo_totale":   round(costo_calcolato, 4),
        "food_cost_pct":  fc_pct,
        "margine_lordo":  round(prezzo - costo_calcolato, 2),
        "gross_profit_pct": round(100 - fc_pct, 2),
    }


# ─── Endpoints: Vendite & Cost Reale ─────────────────────────────────────────

@router.post("/vendita", summary="Registra vendita e aggiorna cost reale")
async def registra_vendita(req: VenditaCreate):
    """
    Registra una vendita e calcola il food/bev cost reale su quella vendita.
    Il cost reale può differire dal teorico per sfridi, esuberi, ecc.
    """
    ricette = await sb_get("fb_ricette", {"id": f"eq.{req.ricetta_id}", "select": "nome,prezzo_vendita,costo_ricetta,tipo"})
    if not ricette:
        raise HTTPException(404, "Ricetta non trovata")
    ricetta = ricette[0]

    prezzo = req.prezzo_effettivo or float(ricetta["prezzo_vendita"])
    costo  = float(ricetta.get("costo_ricetta") or 0)
    revenue     = round(prezzo * req.quantita_venduta, 2)
    costo_tot   = round(costo  * req.quantita_venduta, 4)
    fc_pct      = round((costo_tot / revenue) * 100, 2) if revenue > 0 else 0

    payload = {
        "hotel_id":         req.hotel_id,
        "ricetta_id":       req.ricetta_id,
        "data_vendita":     str(req.data_vendita),
        "turno":            req.turno,
        "quantita_venduta": req.quantita_venduta,
        "prezzo_effettivo": prezzo,
        "revenue":          revenue,
        "costo_totale":     costo_tot,
        "food_cost_pct":    fc_pct,
    }
    result = await sb_post("fb_vendite", payload)
    return {"success": True, "vendita": result, "food_cost_pct": fc_pct, "revenue": revenue}


# ─── Endpoints: Analisi & Report ─────────────────────────────────────────────

@router.get("/analysis", summary="Analisi food/bev cost per periodo")
async def analisi_fb_cost(hotel_id: str, data_da: date, data_a: date, stelle: int = 4):
    """
    Calcola food cost e beverage cost reali per il periodo selezionato.

    Formule:
      Food Cost % = Σ costi food / Σ revenue food × 100
      Bev Cost  % = Σ costi bev  / Σ revenue bev  × 100
      FC Reale    = (Inv.Iniziale + Acquisti - Inv.Finale) / Revenue × 100
    """
    params = {
        "hotel_id":     f"eq.{hotel_id}",
        "data_vendita": f"gte.{data_da}",
        "and":          f"(data_vendita.lte.{data_a})",
        "select":       "revenue,costo_totale,food_cost_pct,fb_ricette(tipo)",
        "limit":        "5000",
    }
    vendite = await sb_get("fb_vendite", params)

    # Separa food da beverage
    food_rev = bev_rev = food_costo = bev_costo = 0.0
    for v in vendite:
        tipo = (v.get("fb_ricette") or {}).get("tipo", "food")
        rev  = float(v.get("revenue") or 0)
        cost = float(v.get("costo_totale") or 0)
        if tipo in ("cocktail", "beverage", "mocktail"):
            bev_rev   += rev
            bev_costo += cost
        else:
            food_rev   += rev
            food_costo += cost

    food_fc_pct = round((food_costo / food_rev) * 100, 2)  if food_rev   > 0 else 0
    bev_fc_pct  = round((bev_costo  / bev_rev)  * 100, 2)  if bev_rev    > 0 else 0
    tot_rev     = food_rev + bev_rev
    tot_costo   = food_costo + bev_costo
    tot_fc_pct  = round((tot_costo / tot_rev) * 100, 2) if tot_rev > 0 else 0

    bm_food = FOOD_COST_BENCHMARK.get(stelle, 32.0)
    bm_bev  = BEV_COST_BENCHMARK["cocktail_bar"]

    return {
        "periodo":   {"da": str(data_da), "a": str(data_a)},
        "stelle":    stelle,
        "food": {
            "revenue":      round(food_rev,   2),
            "costo":        round(food_costo, 2),
            "food_cost_pct": food_fc_pct,
            "benchmark":    bm_food,
            "delta":        round(food_fc_pct - bm_food, 2),
            "status":       "⚠️ sopra target" if food_fc_pct > bm_food else "✅ in target",
            "gross_profit_pct": round(100 - food_fc_pct, 2),
        },
        "beverage": {
            "revenue":     round(bev_rev,   2),
            "costo":       round(bev_costo, 2),
            "bev_cost_pct": bev_fc_pct,
            "benchmark":   bm_bev,
            "delta":       round(bev_fc_pct - bm_bev, 2),
            "status":      "⚠️ sopra target" if bev_fc_pct > bm_bev else "✅ in target",
            "gross_profit_pct": round(100 - bev_fc_pct, 2),
        },
        "totale_fb": {
            "revenue":   round(tot_rev,   2),
            "costo":     round(tot_costo, 2),
            "fb_cost_pct": tot_fc_pct,
            "gross_profit": round(tot_rev - tot_costo, 2),
        },
        "n_vendite": len(vendite),
        "nota": "Dati demo — configura Supabase per dati reali" if not vendite else None,
    }


@router.get("/bcg-matrix", summary="Matrice BCG per menu engineering")
async def bcg_matrix(hotel_id: str, stelle: int = 4):
    """
    Classificazione BCG delle voci di menu:
      STAR         = alta popolarità + food cost in target   → mantieni, promuovi
      CASH COW     = alta popolarità + food cost fuori target → riduci porzione o rivedi prezzo
      QUESTION MARK = bassa popolarità + food cost in target  → promuovi o riposiziona
      DOG          = bassa popolarità + food cost fuori target → elimina dal menu
    """
    ricette = await sb_get("fb_ricette", {
        "hotel_id": f"eq.{hotel_id}",
        "attiva":   "eq.true",
        "select":   "id,nome,tipo,categoria,food_cost_pct,prezzo_vendita,costo_ricetta,bcg_popolarita",
    })
    bm = FOOD_COST_BENCHMARK.get(stelle, 32.0)
    matrix = {"star": [], "cash_cow": [], "question_mark": [], "dog": []}

    for r in ricette:
        fc  = float(r.get("food_cost_pct") or 0)
        pop = r.get("bcg_popolarita", "media")
        alta_pop     = pop == "alta"
        in_target    = fc <= bm
        r["benchmark"] = bm
        r["delta_fc"]  = round(fc - bm, 2)

        if alta_pop and in_target:
            categoria = "star"
        elif alta_pop and not in_target:
            categoria = "cash_cow"
        elif not alta_pop and in_target:
            categoria = "question_mark"
        else:
            categoria = "dog"

        r["bcg_categoria"] = categoria
        matrix[categoria].append(r)

    return {
        "matrix":    matrix,
        "conteggio": {k: len(v) for k, v in matrix.items()},
        "benchmark": bm,
        "suggerimento": (
            f"⭐ Star ({len(matrix['star'])}): promuovi nel menu. "
            f"🐄 Cash Cow ({len(matrix['cash_cow'])}): rivedi prezzo/porzione. "
            f"❓ Question Mark ({len(matrix['question_mark'])}): promuovi con upselling. "
            f"🐕 Dog ({len(matrix['dog'])}): considera di eliminare."
        )
    }


@router.post("/report", summary="Genera report periodico F&B con analisi AI")
async def genera_report(req: FBReportRequest):
    """
    Genera report completo Food & Beverage Cost per il periodo,
    con analisi AI che identifica le aree di miglioramento principali.
    """
    # Calcola analisi
    analysis = await analisi_fb_cost(req.hotel_id, req.data_da, req.data_a, req.stelle)
    bcg      = await bcg_matrix(req.hotel_id, req.stelle)

    analisi_ai = suggerimenti_ai = ""
    if req.generate_ai and ANTHROPIC_API_KEY:
        prompt = (
            f"Analizza questi dati F&B cost per un hotel {req.stelle}★ italiano "
            f"per il periodo {req.data_da} – {req.data_a}:\n\n"
            f"FOOD: revenue €{analysis['food']['revenue']}, "
            f"food cost {analysis['food']['food_cost_pct']}% (benchmark {analysis['food']['benchmark']}%), "
            f"status: {analysis['food']['status']}\n"
            f"BEVERAGE: revenue €{analysis['beverage']['revenue']}, "
            f"bev cost {analysis['beverage']['bev_cost_pct']}% (benchmark {analysis['beverage']['benchmark']}%), "
            f"status: {analysis['beverage']['status']}\n"
            f"BCG: {bcg['conteggio']}\n\n"
            f"Fornisci: 1) Analisi sintetica (3 righe), 2) 3 azioni correttive prioritarie, "
            f"3) KPI da monitorare la settimana successiva. Formato professionale italiano."
        )
        system = (
            "Sei l'AI Advisor F&B di BAD.S Platform. "
            "Sei esperto di food cost, beverage cost, menu engineering e revenue F&B in hotellerie italiana. "
            "Rispondi sempre in italiano professionale e concreto."
        )
        async with httpx.AsyncClient(timeout=60.0) as client:
            r = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={"x-api-key": ANTHROPIC_API_KEY, "anthropic-version": "2023-06-01", "content-type": "application/json"},
                json={"model": "claude-sonnet-4-20250514", "max_tokens": 1000, "system": system, "messages": [{"role": "user", "content": prompt}]},
            )
        if r.status_code == 200:
            data = r.json()
            testo = "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")
            analisi_ai = testo

    # Salva report su Supabase
    report_payload = {
        "hotel_id":           req.hotel_id,
        "periodo_da":         str(req.data_da),
        "periodo_a":          str(req.data_a),
        "food_revenue":       analysis["food"]["revenue"],
        "food_costo":         analysis["food"]["costo"],
        "food_cost_pct":      analysis["food"]["food_cost_pct"],
        "food_cost_target":   analysis["food"]["benchmark"],
        "bev_revenue":        analysis["beverage"]["revenue"],
        "bev_costo":          analysis["beverage"]["costo"],
        "bev_cost_pct":       analysis["beverage"]["bev_cost_pct"],
        "bev_cost_target":    analysis["beverage"]["benchmark"],
        "fb_revenue_totale":  analysis["totale_fb"]["revenue"],
        "fb_costo_totale":    analysis["totale_fb"]["costo"],
        "fb_cost_pct_totale": analysis["totale_fb"]["fb_cost_pct"],
        "gross_profit":       analysis["totale_fb"]["gross_profit"],
        "gross_profit_pct":   round(100 - analysis["totale_fb"]["fb_cost_pct"], 2),
        "top_costi":          json.dumps(bcg["conteggio"]),
        "analisi_ai":         analisi_ai,
        "stato":              "bozza",
    }
    report = await sb_post("fb_cost_report", report_payload)

    return {
        "success":   True,
        "report_id": report.get("id"),
        "analysis":  analysis,
        "bcg":       bcg,
        "analisi_ai": analisi_ai,
        "timestamp": datetime.utcnow().isoformat(),
    }
