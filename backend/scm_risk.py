"""
BAD.S Platform — Modulo SCM Risk Analysis
Router FastAPI per la gestione dei rischi supply chain

Endpoints:
  GET  /api/scm/risk/matrix        — Matrice rischi attivi
  POST /api/scm/risk               — Crea/aggiorna rischio
  PUT  /api/scm/risk/{id}/mitigato — Segna rischio come mitigato
  GET  /api/scm/risk/kpi           — KPI risk overview
"""

from __future__ import annotations
from datetime import date, datetime
from typing import Optional, List, Dict
import os

import httpx
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/scm/risk", tags=["SCM Risk"])

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")

# ── Demo data ────────────────────────────────────────────────────

_DEMO_RISCHI = [
    {
        "id": "demo-r-001",
        "categoria": "fornitore",
        "descrizione": "Fornitore principale fresco — mono-sourcing senza alternativa qualificata",
        "probabilita": 3, "impatto": 4, "score": 12,
        "livello": "alto",
        "misure": "Qualifica secondo fornitore entro Q3 2026",
        "responsabile": "Resp. Acquisti",
        "stato": "aperto",
        "scadenza": "2026-09-30",
    },
    {
        "id": "demo-r-002",
        "categoria": "qualita",
        "descrizione": "Rischio contaminazione microbiologica forniture carne fresca",
        "probabilita": 2, "impatto": 5, "score": 10,
        "livello": "alto",
        "misure": "Audit fornitore mensile + analisi microbiologiche ogni lotto",
        "responsabile": "HACCP Manager",
        "stato": "mitigato",
        "scadenza": "2026-06-30",
    },
    {
        "id": "demo-r-003",
        "categoria": "prezzi",
        "descrizione": "Volatilità prezzi olio extravergine e materie prime commodity",
        "probabilita": 4, "impatto": 3, "score": 12,
        "livello": "alto",
        "misure": "Contratti forward trimestrali su commodity principali",
        "responsabile": "F&B Manager",
        "stato": "aperto",
        "scadenza": "2026-12-31",
    },
    {
        "id": "demo-r-004",
        "categoria": "logistica",
        "descrizione": "Dipendenza da unico vettore refrigerato — rischio rottura catena freddo",
        "probabilita": 2, "impatto": 4, "score": 8,
        "livello": "medio",
        "misure": "Accordo standby con vettore secondario",
        "responsabile": "Resp. Logistica",
        "stato": "aperto",
        "scadenza": "2026-07-31",
    },
    {
        "id": "demo-r-005",
        "categoria": "recall",
        "descrizione": "Piano recall prodotti biologici/allergeni non aggiornato",
        "probabilita": 1, "impatto": 5, "score": 5,
        "livello": "medio",
        "misure": "Aggiornamento mock-recall semestrale ISO 22005",
        "responsabile": "Food Safety Manager",
        "stato": "aperto",
        "scadenza": "2026-06-15",
    },
]

_LIVELLI = {
    (1, 3):   "basso",
    (4, 6):   "medio",
    (7, 12):  "alto",
    (13, 25): "critico",
}


# ── Modelli ─────────────────────────────────────────────────────

class RischioCreate(BaseModel):
    hotel_id: str
    categoria: str          # fornitore | logistica | qualita | prezzi | recall
    fornitore_id: Optional[str] = None
    descrizione: str
    probabilita: int = Field(..., ge=1, le=5)
    impatto:     int = Field(..., ge=1, le=5)
    misure:      Optional[str] = None
    responsabile: Optional[str] = None
    scadenza:    Optional[str] = None
    note:        Optional[str] = None


class RischioUpdate(BaseModel):
    stato: Optional[str] = None     # aperto | mitigato | chiuso
    misure: Optional[str] = None
    note: Optional[str] = None


# ── Helpers ──────────────────────────────────────────────────────

def _calcola_livello(score: int) -> str:
    for (lo, hi), lv in _LIVELLI.items():
        if lo <= score <= hi:
            return lv
    return "critico"


# ── Routes ───────────────────────────────────────────────────────

@router.get("/matrix", summary="Matrice rischi supply chain")
async def get_risk_matrix(hotel_id: str, categoria: Optional[str] = None, stato: Optional[str] = None):
    """
    Restituisce la matrice rischi attivi con heat-map scoring.
    Score = probabilità (1-5) × impatto (1-5).
    Livelli: basso 1-3, medio 4-6, alto 7-12, critico 13-25.
    """
    if not SUPABASE_URL:
        rischi = _DEMO_RISCHI.copy()
        if categoria:
            rischi = [r for r in rischi if r["categoria"] == categoria]
        if stato:
            rischi = [r for r in rischi if r["stato"] == stato]
        return {
            "rischi": rischi,
            "totale": len(rischi),
            "critici": sum(1 for r in rischi if r["livello"] == "critico"),
            "alti":    sum(1 for r in rischi if r["livello"] == "alto"),
            "nota":    "Demo mode — configura Supabase per dati reali",
        }

    params: Dict = {
        "hotel_id": f"eq.{hotel_id}",
        "select": "*",
        "order": "score.desc",
    }
    if categoria:
        params["categoria"] = f"eq.{categoria}"
    if stato:
        params["stato"] = f"eq.{stato}"

    async with httpx.AsyncClient() as client:
        r = await client.get(
            f"{SUPABASE_URL}/rest/v1/scm_rischi",
            headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"},
            params=params,
        )
    rows = r.json() if r.status_code == 200 else []

    return {
        "rischi": rows,
        "totale": len(rows),
        "critici": sum(1 for r in rows if r.get("livello") == "critico"),
        "alti":    sum(1 for r in rows if r.get("livello") == "alto"),
    }


@router.post("", summary="Registra rischio SCM")
async def create_rischio(req: RischioCreate):
    """Registra un nuovo rischio nella matrice con calcolo automatico score e livello."""
    score = req.probabilita * req.impatto
    livello = _calcola_livello(score)

    payload = {
        **req.dict(),
        "score": score,
        "livello": livello,
        "stato": "aperto",
    }

    if not SUPABASE_URL:
        return {"id": "demo-uuid", "score": score, "livello": livello, "nota": "Demo mode"}

    async with httpx.AsyncClient() as client:
        r = await client.post(
            f"{SUPABASE_URL}/rest/v1/scm_rischi",
            headers={
                "apikey": SUPABASE_KEY,
                "Authorization": f"Bearer {SUPABASE_KEY}",
                "Content-Type": "application/json",
                "Prefer": "return=representation",
            },
            json=payload,
        )
    data = r.json()[0] if r.status_code == 201 and r.json() else {}
    return {"id": data.get("id"), "score": score, "livello": livello}


@router.put("/{rischio_id}/stato", summary="Aggiorna stato rischio")
async def update_rischio_stato(rischio_id: str, hotel_id: str, req: RischioUpdate):
    """Aggiorna stato (aperto → mitigato → chiuso) e misure di mitigazione."""
    payload = {k: v for k, v in req.dict().items() if v is not None}
    payload["updated_at"] = datetime.utcnow().isoformat()

    if not SUPABASE_URL:
        return {"aggiornato": True, "id": rischio_id, "nota": "Demo mode"}

    async with httpx.AsyncClient() as client:
        r = await client.patch(
            f"{SUPABASE_URL}/rest/v1/scm_rischi",
            headers={
                "apikey": SUPABASE_KEY,
                "Authorization": f"Bearer {SUPABASE_KEY}",
                "Content-Type": "application/json",
            },
            params={"id": f"eq.{rischio_id}", "hotel_id": f"eq.{hotel_id}"},
            json=payload,
        )
    return {"aggiornato": r.status_code in (200, 204), "id": rischio_id}


@router.get("/kpi", summary="KPI overview rischi SCM")
async def get_risk_kpi(hotel_id: str):
    """Riepilogo KPI risk management: aperti, mitigati, % critici, scaduti."""
    if not SUPABASE_URL:
        return {
            "aperti":    3,
            "mitigati":  1,
            "chiusi":    0,
            "critici":   0,
            "alti":      3,
            "scaduti":   1,
            "score_medio": 9.4,
            "categoria_top_risk": "fornitore",
            "nota": "Demo mode",
        }

    async with httpx.AsyncClient() as client:
        r = await client.get(
            f"{SUPABASE_URL}/rest/v1/scm_rischi",
            headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"},
            params={"hotel_id": f"eq.{hotel_id}", "select": "stato,livello,score,scadenza,categoria"},
        )
    rows = r.json() if r.status_code == 200 else []
    oggi = date.today().isoformat()

    from collections import Counter
    cat_counter: Counter = Counter(r.get("categoria") for r in rows if r.get("stato") == "aperto")
    top_risk = cat_counter.most_common(1)[0][0] if cat_counter else "—"

    scores = [r.get("score", 0) for r in rows if r.get("stato") == "aperto"]
    return {
        "aperti":   sum(1 for r in rows if r.get("stato") == "aperto"),
        "mitigati": sum(1 for r in rows if r.get("stato") == "mitigati"),
        "chiusi":   sum(1 for r in rows if r.get("stato") == "chiuso"),
        "critici":  sum(1 for r in rows if r.get("livello") == "critico"),
        "alti":     sum(1 for r in rows if r.get("livello") == "alto"),
        "scaduti":  sum(1 for r in rows if r.get("scadenza") and r["scadenza"] < oggi),
        "score_medio": round(sum(scores) / len(scores), 1) if scores else 0,
        "categoria_top_risk": top_risk,
    }
