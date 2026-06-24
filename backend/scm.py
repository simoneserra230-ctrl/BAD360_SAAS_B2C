"""
BAD360.ai — SCM Pro: Fornitori & Ordini (persistenza reale, multi-tenant)
scmpro.html era demo. Qui anagrafica fornitori + ordini d'acquisto persistono.
Tabelle NUOVE scm_fornitori / scm_ordini (hotel_id TEXT) — non riusano le
legacy `fornitori`/`ordini_fornitori` (hotel_id UUID).

Sicurezza: hotel_id SEMPRE dal token (require_user), mai dal client.
"""

from __future__ import annotations
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from backend.database import get_supabase
from backend.auth import require_user, UserProfile

router = APIRouter(prefix="/api/scm", tags=["SCM Pro"])


def _sb():
    sb = get_supabase()
    if not sb:
        raise HTTPException(503, "Database non configurato")
    return sb


# ── FORNITORI ─────────────────────────────────────────────────────────
class Fornitore(BaseModel):
    id: Optional[str] = None
    nome: str
    cat: str = ""
    cert: str = ""
    contatto: str = ""
    sla: int = 85
    spend: float = 0
    stato: str = "ok"
    icon: str = "🏭"


@router.post("/fornitore", summary="Crea/aggiorna un fornitore")
async def upsert_fornitore(payload: Fornitore, user: UserProfile = Depends(require_user)):
    sb = _sb()
    rec = {"hotel_id": user.hotel_id, "nome": payload.nome, "cat": payload.cat,
           "cert": payload.cert, "contatto": payload.contatto, "sla": payload.sla,
           "spend": payload.spend, "stato": payload.stato, "icon": payload.icon,
           "updated_at": datetime.utcnow().isoformat()}
    try:
        if payload.id:
            res = sb.table("scm_fornitori").update(rec).eq("id", payload.id).eq("hotel_id", user.hotel_id).execute()
        else:
            res = sb.table("scm_fornitori").insert(rec).execute()
    except Exception as e:
        raise HTTPException(500, f"Errore salvataggio: {e}")
    return {"ok": True, "fornitore": (res.data or [rec])[0]}


@router.get("/fornitori", summary="Lista fornitori dell'hotel")
async def list_fornitori(user: UserProfile = Depends(require_user)):
    sb = _sb()
    try:
        res = sb.table("scm_fornitori").select("*").eq("hotel_id", user.hotel_id).order("nome").execute()
    except Exception as e:
        raise HTTPException(500, f"Errore lettura: {e}")
    return {"ok": True, "fornitori": res.data or []}


@router.delete("/fornitore/{fornitore_id}", summary="Elimina un fornitore")
async def delete_fornitore(fornitore_id: str, user: UserProfile = Depends(require_user)):
    sb = _sb()
    try:
        sb.table("scm_fornitori").delete().eq("id", fornitore_id).eq("hotel_id", user.hotel_id).execute()
    except Exception as e:
        raise HTTPException(500, f"Errore eliminazione: {e}")
    return {"ok": True}


# ── ORDINI ────────────────────────────────────────────────────────────
class Ordine(BaseModel):
    id: Optional[str] = None
    num: str = ""
    forn: str = ""
    cat: str = "Misto"
    data: Optional[str] = None
    cons: Optional[str] = None
    importo: float = 0
    prod: str = ""
    stato: str = "aperto"        # aperto | transit | ok


@router.post("/ordine", summary="Crea/aggiorna un ordine")
async def upsert_ordine(payload: Ordine, user: UserProfile = Depends(require_user)):
    sb = _sb()
    num = payload.num or ("ORD-" + datetime.utcnow().strftime("%Y%m%d-%H%M%S"))
    rec = {"hotel_id": user.hotel_id, "num": num, "forn": payload.forn, "cat": payload.cat,
           "data": payload.data or datetime.utcnow().date().isoformat(), "cons": payload.cons or None,
           "importo": payload.importo, "prod": payload.prod, "stato": payload.stato,
           "updated_at": datetime.utcnow().isoformat()}
    try:
        if payload.id:
            res = sb.table("scm_ordini").update(rec).eq("id", payload.id).eq("hotel_id", user.hotel_id).execute()
        else:
            res = sb.table("scm_ordini").insert(rec).execute()
    except Exception as e:
        raise HTTPException(500, f"Errore salvataggio: {e}")
    return {"ok": True, "ordine": (res.data or [rec])[0]}


@router.get("/ordini", summary="Lista ordini dell'hotel")
async def list_ordini(user: UserProfile = Depends(require_user), stato: Optional[str] = None):
    sb = _sb()
    q = sb.table("scm_ordini").select("*").eq("hotel_id", user.hotel_id)
    if stato:
        q = q.eq("stato", stato)
    try:
        res = q.order("data", desc=True).execute()
    except Exception as e:
        raise HTTPException(500, f"Errore lettura: {e}")
    rows = res.data or []
    return {"ok": True, "ordini": rows, "totale": len(rows),
            "spesa_totale": round(sum(float(r.get("importo") or 0) for r in rows), 2)}


@router.delete("/ordine/{ordine_id}", summary="Elimina un ordine")
async def delete_ordine(ordine_id: str, user: UserProfile = Depends(require_user)):
    sb = _sb()
    try:
        sb.table("scm_ordini").delete().eq("id", ordine_id).eq("hotel_id", user.hotel_id).execute()
    except Exception as e:
        raise HTTPException(500, f"Errore eliminazione: {e}")
    return {"ok": True}
