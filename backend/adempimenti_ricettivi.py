"""
BAD360.ai — Adempimenti ricettivi: CIN / Alloggiati / ISTAT / Imposta di soggiorno (niche C3)

Il "grind" ricorrente di OGNI struttura ricettiva italiana. Qui: config identificativi
(CIN/CIR/Comune + tariffa imposta) + LOG ALLOGGIATI (arrivi) → da cui si calcolano
imposta di soggiorno dovuta e il flusso per Alloggiati Web/ISTAT, + checklist adempimenti.
Human-in-the-loop: gli invii ufficiali (Questura/ISTAT) restano sui portali preposti.

Sicurezza: hotel_id dal token. Tabelle: cin_config + alloggiati_log.
"""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from backend.database import get_supabase
from backend.auth import require_user, UserProfile

router = APIRouter(prefix="/api/adempimenti", tags=["Adempimenti ricettivi"])


def _sb():
    sb = get_supabase()
    if not sb:
        raise HTTPException(503, "Database non configurato")
    return sb


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Config(BaseModel):
    cin_code:           Optional[str] = None
    cir_code:           Optional[str] = None
    comune:             Optional[str] = None
    tariffa_soggiorno:  float = 0.0     # €/persona/notte
    max_notti_tassabili: int = 0        # 0 = nessun tetto; es. 7 = oltre la 7ª notte esente
    note:               Optional[str] = None


@router.get("/config", summary="Config identificativi + imposta (admin)")
async def get_config(user: UserProfile = Depends(require_user)):
    sb = _sb()
    rows = (sb.table("cin_config").select("*").eq("hotel_id", user.hotel_id).execute().data) or []
    return {"ok": True, "config": rows[0] if rows else None}


@router.put("/config", summary="Imposta config")
async def set_config(payload: Config, user: UserProfile = Depends(require_user)):
    sb = _sb()
    data = {"hotel_id": user.hotel_id, "cin_code": (payload.cin_code or "").strip(),
            "cir_code": (payload.cir_code or "").strip(), "comune": (payload.comune or "").strip(),
            "tariffa_soggiorno": float(payload.tariffa_soggiorno or 0), "max_notti_tassabili": int(payload.max_notti_tassabili or 0),
            "note": (payload.note or "").strip(), "updated_at": _now()}
    exist = (sb.table("cin_config").select("hotel_id").eq("hotel_id", user.hotel_id).execute().data) or []
    if exist:
        sb.table("cin_config").update(data).eq("hotel_id", user.hotel_id).execute()
    else:
        sb.table("cin_config").insert(data).execute()
    return {"ok": True, "config": data}


class Alloggiato(BaseModel):
    id:           Optional[str] = None
    data_arrivo:  str
    ospite_nome:  str
    n_ospiti:     int = 1
    n_notti:      int = 1
    esente:       bool = False
    inviato_alloggiati: bool = False
    note:         Optional[str] = None


@router.get("/alloggiati", summary="Log alloggiati (admin)")
async def list_alloggiati(user: UserProfile = Depends(require_user)):
    sb = _sb()
    rows = (sb.table("alloggiati_log").select("*").eq("hotel_id", user.hotel_id).order("data_arrivo", desc=True).execute().data) or []
    return {"ok": True, "alloggiati": rows, "totale": len(rows)}


@router.post("/alloggiati", summary="Registra arrivo")
async def upsert_alloggiato(payload: Alloggiato, user: UserProfile = Depends(require_user)):
    sb = _sb()
    data = {"hotel_id": user.hotel_id, "data_arrivo": payload.data_arrivo, "ospite_nome": payload.ospite_nome.strip(),
            "n_ospiti": int(payload.n_ospiti or 1), "n_notti": int(payload.n_notti or 1), "esente": bool(payload.esente),
            "inviato_alloggiati": bool(payload.inviato_alloggiati), "note": (payload.note or "").strip()}
    if payload.id:
        res = sb.table("alloggiati_log").update(data).eq("id", payload.id).eq("hotel_id", user.hotel_id).execute()
        if not res.data:
            raise HTTPException(404, "Record non trovato")
        return {"ok": True, "record": res.data[0]}
    data["created_at"] = _now()
    res = sb.table("alloggiati_log").insert(data).execute()
    return {"ok": True, "record": res.data[0] if res.data else data}


@router.put("/alloggiati/{aid}/inviato", summary="Segna inviato ad Alloggiati Web")
async def set_inviato(aid: str, user: UserProfile = Depends(require_user), inviato: bool = True):
    sb = _sb()
    res = sb.table("alloggiati_log").update({"inviato_alloggiati": inviato}).eq("id", aid).eq("hotel_id", user.hotel_id).execute()
    if not res.data:
        raise HTTPException(404, "Record non trovato")
    return {"ok": True, "record": res.data[0]}


@router.delete("/alloggiati/{aid}", summary="Elimina record")
async def delete_alloggiato(aid: str, user: UserProfile = Depends(require_user)):
    sb = _sb()
    sb.table("alloggiati_log").delete().eq("id", aid).eq("hotel_id", user.hotel_id).execute()
    return {"ok": True}


@router.get("/dashboard", summary="Imposta soggiorno dovuta + checklist adempimenti")
async def dashboard(user: UserProfile = Depends(require_user)):
    sb = _sb()
    cfg = (sb.table("cin_config").select("*").eq("hotel_id", user.hotel_id).execute().data) or []
    c = cfg[0] if cfg else {}
    tariffa = float(c.get("tariffa_soggiorno") or 0)
    maxn = int(c.get("max_notti_tassabili") or 0)
    logs = (sb.table("alloggiati_log").select("*").eq("hotel_id", user.hotel_id).execute().data) or []
    imposta = 0.0
    pernottamenti = 0
    for l in logs:
        notti = int(l.get("n_notti") or 0)
        if maxn > 0:
            notti = min(notti, maxn)
        osp = int(l.get("n_ospiti") or 0)
        pernottamenti += osp * int(l.get("n_notti") or 0)
        if not l.get("esente"):
            imposta += osp * notti * tariffa
    da_inviare = sum(1 for l in logs if not l.get("inviato_alloggiati"))
    checklist = [
        {"voce": "CIN registrato", "ok": bool(c.get("cin_code"))},
        {"voce": "CIR (codice regionale)", "ok": bool(c.get("cir_code"))},
        {"voce": "Tariffa imposta di soggiorno impostata", "ok": tariffa > 0},
        {"voce": "Alloggiati inviati alla Questura", "ok": da_inviare == 0 and len(logs) > 0},
    ]
    return {"ok": True, "kpi": {
        "imposta_soggiorno_dovuta": round(imposta, 2), "pernottamenti": pernottamenti,
        "arrivi_registrati": len(logs), "alloggiati_da_inviare": da_inviare,
        "cin": c.get("cin_code") or "—", "comune": c.get("comune") or "—",
    }, "checklist": checklist}
