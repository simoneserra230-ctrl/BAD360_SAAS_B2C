"""
BAD.S Platform — Modulo Tracciabilità ISO 22005
Router FastAPI per rintracciabilità lotti, filiera e mock recall

Endpoints:
  POST /api/tracciabilita/lotto          — Registra lotto ricevuto
  GET  /api/tracciabilita/lotto/{id}     — Dettaglio lotto + catena
  GET  /api/tracciabilita/one-step-back  — Fornitore precedente lotto
  GET  /api/tracciabilita/one-step-fwd   — Dove è andato il lotto
  POST /api/tracciabilita/mock-recall    — Simula procedura recall
  GET  /api/tracciabilita/bilancio-massa — Bilancio di massa lotto
  GET  /api/tracciabilita/lotti          — Lista lotti hotel
"""

from __future__ import annotations
from datetime import date, datetime
from typing import Optional, List, Dict, Any
import os

import httpx
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from backend.database import get_supabase

router = APIRouter(prefix="/api/tracciabilita", tags=["Tracciabilità ISO 22005"])

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")


# ── Demo data ─────────────────────────────────────────────────────

_DEMO_LOTTI = [
    {
        "id": "lot-001",
        "codice_lotto": "LOT-2026-05-001",
        "prodotto": "Prosciutto Crudo DOP",
        "fornitore": "Salumificio Sardo Srl",
        "data_ricezione": "2026-05-10",
        "data_scadenza": "2026-08-10",
        "quantita_ricevuta": 15.0,
        "unita_misura": "kg",
        "temperatura_ricezione": 4.2,
        "conforme_haccp": True,
        "origine": "IT — Sardegna",
        "stato": "attivo",
    },
    {
        "id": "lot-002",
        "codice_lotto": "LOT-2026-05-002",
        "prodotto": "Pecorino Sardo DOP",
        "fornitore": "Caseificio Nuoro Srl",
        "data_ricezione": "2026-05-12",
        "data_scadenza": "2026-11-12",
        "quantita_ricevuta": 8.5,
        "unita_misura": "kg",
        "temperatura_ricezione": 6.1,
        "conforme_haccp": True,
        "origine": "IT — Nuoro (NU)",
        "stato": "attivo",
    },
    {
        "id": "lot-003",
        "codice_lotto": "LOT-2026-04-018",
        "prodotto": "Olio EVO Bio Sardegna",
        "fornitore": "Frantoi Oristano SpA",
        "data_ricezione": "2026-04-20",
        "data_scadenza": "2027-04-20",
        "quantita_ricevuta": 24.0,
        "unita_misura": "L",
        "temperatura_ricezione": 18.0,
        "conforme_haccp": True,
        "origine": "IT — Oristano (OR)",
        "stato": "attivo",
    },
]

_DEMO_UTILIZZI = [
    {"ricetta": "Antipasto misto sardo", "quantita": 2.5, "data": "2026-05-14", "responsabile": "Chef Marco"},
    {"ricetta": "Tagliere del bartender", "quantita": 1.2, "data": "2026-05-15", "responsabile": "Chef Marco"},
    {"ricetta": "Bruschette sarde", "quantita": 0.8, "data": "2026-05-16", "responsabile": "Chef Sofia"},
]


# ── Modelli ───────────────────────────────────────────────────────

class LottoCreate(BaseModel):
    hotel_id: str
    codice_lotto: str
    prodotto: str
    fornitore_id: Optional[str] = None
    fornitore_nome: Optional[str] = None
    data_ricezione: Optional[str] = None
    data_scadenza: Optional[str] = None
    quantita_ricevuta: float
    unita_misura: str = "kg"
    temperatura_ricezione: Optional[float] = None
    conforme_haccp: bool = True
    documento_ddt: Optional[str] = None
    origine: Optional[str] = None
    note: Optional[str] = None


class UtilizzoCreate(BaseModel):
    hotel_id: str
    lotto_id: str
    ricetta_id: Optional[str] = None
    ricetta_nome: Optional[str] = None
    quantita_utilizzata: float
    data_utilizzo: Optional[str] = None
    responsabile: Optional[str] = None
    note: Optional[str] = None


class MockRecallRequest(BaseModel):
    hotel_id: str
    codice_lotto: str
    motivo: str
    responsabile: str = "Food Safety Manager"
    ambito: str = "interno"   # interno | filiera | pubblico


# ── Routes ────────────────────────────────────────────────────────

@router.get("", summary="Lista lotti hotel")
async def lista_lotti(
    hotel_id: str,
    stato: Optional[str] = None,
    prodotto: Optional[str] = None,
    limit: int = Query(50, le=200),
):
    """Lista lotti ricevuti con filtri per stato e prodotto."""
    if not SUPABASE_URL:
        lotti = _DEMO_LOTTI.copy()
        if stato:
            lotti = [l for l in lotti if l.get("stato") == stato]
        if prodotto:
            lotti = [l for l in lotti if prodotto.lower() in l.get("prodotto", "").lower()]
        return {"lotti": lotti, "totale": len(lotti), "nota": "Demo mode"}

    params: Dict = {
        "hotel_id": f"eq.{hotel_id}",
        "select": "*",
        "order": "data_ricezione.desc",
        "limit": str(limit),
    }
    if stato:
        params["stato"] = f"eq.{stato}"

    async with httpx.AsyncClient() as client:
        r = await client.get(
            f"{SUPABASE_URL}/rest/v1/lotti_tracciabilita",
            headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"},
            params=params,
        )
    rows = r.json() if r.status_code == 200 else []
    return {"lotti": rows, "totale": len(rows)}


@router.post("", summary="Registra lotto ricevuto")
async def crea_lotto(req: LottoCreate):
    """Registra un nuovo lotto in ingresso con dati DDT e conformità HACCP."""
    payload = {
        **req.dict(),
        "data_ricezione": req.data_ricezione or date.today().isoformat(),
        "stato": "attivo",
    }

    if not SUPABASE_URL:
        return {
            "id": "demo-uuid",
            "codice_lotto": req.codice_lotto,
            "prodotto": req.prodotto,
            "nota": "Demo mode",
        }

    async with httpx.AsyncClient() as client:
        r = await client.post(
            f"{SUPABASE_URL}/rest/v1/lotti_tracciabilita",
            headers={
                "apikey": SUPABASE_KEY,
                "Authorization": f"Bearer {SUPABASE_KEY}",
                "Content-Type": "application/json",
                "Prefer": "return=representation",
            },
            json=payload,
        )
    data = r.json()[0] if r.status_code == 201 and r.json() else {}
    return {"id": data.get("id"), "codice_lotto": req.codice_lotto}


@router.get("/one-step-back", summary="One-Step-Back: fornitore precedente")
async def one_step_back(hotel_id: str, codice_lotto: str):
    """
    ISO 22005 One-Step-Back: identifica chi ha fornito il lotto specificato
    e i relativi documenti di accompagnamento (DDT, certificati).
    """
    if not SUPABASE_URL:
        demo_lotto = next((l for l in _DEMO_LOTTI if l["codice_lotto"] == codice_lotto), _DEMO_LOTTI[0])
        return {
            "codice_lotto": codice_lotto,
            "prodotto": demo_lotto["prodotto"],
            "fornitore": {
                "nome": demo_lotto["fornitore"],
                "lotto_fornitore": f"EXT-{codice_lotto}",
                "data_consegna": demo_lotto["data_ricezione"],
                "documento_ddt": f"DDT-{codice_lotto[:10]}",
                "origine": demo_lotto["origine"],
                "certificazioni": ["ISO 22000", "HACCP"],
            },
            "nota": "Demo mode",
        }

    async with httpx.AsyncClient() as client:
        r = await client.get(
            f"{SUPABASE_URL}/rest/v1/lotti_tracciabilita",
            headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"},
            params={
                "hotel_id": f"eq.{hotel_id}",
                "codice_lotto": f"eq.{codice_lotto}",
                "select": "*, fornitori(ragione_sociale,certificazioni)",
            },
        )
    rows = r.json() if r.status_code == 200 and r.json() else []
    if not rows:
        raise HTTPException(status_code=404, detail=f"Lotto '{codice_lotto}' non trovato")

    lotto = rows[0]
    forn = lotto.get("fornitori") or {}
    return {
        "codice_lotto": codice_lotto,
        "prodotto": lotto.get("prodotto"),
        "fornitore": {
            "nome": forn.get("ragione_sociale", lotto.get("fornitore_nome", "—")),
            "lotto_fornitore": lotto.get("lotto_fornitore_esterno"),
            "data_consegna": lotto.get("data_ricezione"),
            "documento_ddt": lotto.get("documento_ddt"),
            "origine": lotto.get("origine"),
            "certificazioni": forn.get("certificazioni", []),
        },
    }


@router.get("/one-step-fwd", summary="One-Step-Forward: utilizzi lotto")
async def one_step_forward(hotel_id: str, codice_lotto: str):
    """
    ISO 22005 One-Step-Forward: identifica dove è stato utilizzato il lotto
    (ricette, reparti, date) per tracciare la filiera interna.
    """
    if not SUPABASE_URL:
        demo_lotto = next((l for l in _DEMO_LOTTI if l["codice_lotto"] == codice_lotto), _DEMO_LOTTI[0])
        q_tot = sum(u["quantita"] for u in _DEMO_UTILIZZI)
        q_rim = demo_lotto["quantita_ricevuta"] - q_tot
        return {
            "codice_lotto": codice_lotto,
            "prodotto": demo_lotto["prodotto"],
            "quantita_ricevuta": demo_lotto["quantita_ricevuta"],
            "quantita_utilizzata": q_tot,
            "quantita_rimanente": round(q_rim, 3),
            "utilizzi": _DEMO_UTILIZZI,
            "nota": "Demo mode",
        }

    async with httpx.AsyncClient() as client:
        r_lotto = await client.get(
            f"{SUPABASE_URL}/rest/v1/lotti_tracciabilita",
            headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"},
            params={"hotel_id": f"eq.{hotel_id}", "codice_lotto": f"eq.{codice_lotto}", "select": "*"},
        )
        lotto_rows = r_lotto.json() if r_lotto.status_code == 200 and r_lotto.json() else []
        if not lotto_rows:
            raise HTTPException(status_code=404, detail=f"Lotto '{codice_lotto}' non trovato")
        lotto = lotto_rows[0]

        r_utilizzi = await client.get(
            f"{SUPABASE_URL}/rest/v1/utilizzi_lotti",
            headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"},
            params={"lotto_id": f"eq.{lotto['id']}", "select": "*", "order": "data_utilizzo.asc"},
        )
        utilizzi = r_utilizzi.json() if r_utilizzi.status_code == 200 else []

    q_usata = sum(float(u.get("quantita_utilizzata", 0)) for u in utilizzi)
    q_rim = float(lotto.get("quantita_ricevuta", 0)) - q_usata

    return {
        "codice_lotto": codice_lotto,
        "prodotto": lotto.get("prodotto"),
        "quantita_ricevuta": lotto.get("quantita_ricevuta"),
        "quantita_utilizzata": round(q_usata, 3),
        "quantita_rimanente": round(q_rim, 3),
        "utilizzi": utilizzi,
    }


@router.post("/mock-recall", summary="Simula procedura recall lotto")
async def mock_recall(req: MockRecallRequest):
    """
    Simula la procedura di ritiro/recall secondo ISO 22005 e Reg. CE 178/2002.
    Identifica: lotti impattati, clienti/reparti coinvolti, quantità da ritirare.
    """
    if not SUPABASE_URL:
        demo_lotto = next(
            (l for l in _DEMO_LOTTI if l["codice_lotto"] == req.codice_lotto),
            _DEMO_LOTTI[0]
        )
        return {
            "recall_id": f"RCL-{datetime.now().strftime('%Y%m%d%H%M%S')}",
            "codice_lotto": req.codice_lotto,
            "prodotto": demo_lotto["prodotto"],
            "motivo": req.motivo,
            "responsabile": req.responsabile,
            "avviato_il": datetime.now().isoformat(),
            "lotti_impattati": [req.codice_lotto],
            "reparti_coinvolti": ["Cucina", "Bar", "Room Service"],
            "quantita_da_ritirare_kg": demo_lotto["quantita_ricevuta"],
            "utilizzi_identificati": len(_DEMO_UTILIZZI),
            "azioni_richieste": [
                "1. Blocco immediato utilizzo lotto in tutti i reparti",
                "2. Identificazione e segregazione scorte residue",
                "3. Notifica al fornitore entro 2 ore",
                f"4. Comunicazione autorità competente (ambito: {req.ambito})",
                "5. Apertura Non Conformità correlata nel sistema HACCP",
                "6. Aggiornamento registro recall con esito entro 48h",
            ],
            "nota": "Demo mode — procedura simulata",
        }

    # In produzione: logica reale su Supabase
    raise HTTPException(
        status_code=503,
        detail="Mock recall su dati reali: configurare Supabase per abilitare"
    )


@router.get("/bilancio-massa", summary="Bilancio di massa lotto")
async def bilancio_massa(hotel_id: str, codice_lotto: str):
    """
    Calcola il bilancio di massa del lotto: ricevuto - utilizzato - scarti = rimanente.
    Verifica conformità ISO 22005 (bilanciamento ≥ 95%).
    """
    if not SUPABASE_URL:
        demo_lotto = next((l for l in _DEMO_LOTTI if l["codice_lotto"] == codice_lotto), _DEMO_LOTTI[0])
        ricevuto = float(demo_lotto["quantita_ricevuta"])
        utilizzato = sum(u["quantita"] for u in _DEMO_UTILIZZI)
        scarti = 0.3
        rimanente = ricevuto - utilizzato - scarti
        bilanciamento_pct = round((utilizzato + scarti + rimanente) / ricevuto * 100, 1)
        return {
            "codice_lotto": codice_lotto,
            "prodotto": demo_lotto["prodotto"],
            "bilancio": {
                "ricevuto":    round(ricevuto, 3),
                "utilizzato":  round(utilizzato, 3),
                "scarti":      round(scarti, 3),
                "rimanente":   round(rimanente, 3),
                "unita":       demo_lotto["unita_misura"],
            },
            "bilanciamento_pct": bilanciamento_pct,
            "conforme_iso22005": bilanciamento_pct >= 95,
            "nota": "Demo mode",
        }

    # In produzione: query Supabase
    raise HTTPException(status_code=503, detail="Configura Supabase per bilancio su dati reali")
