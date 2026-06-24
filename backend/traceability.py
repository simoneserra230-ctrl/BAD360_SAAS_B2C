"""
BAD360.ai — Tracciabilità lotti (ISO 22005) — persistenza reale, multi-tenant
tracciabilita.html era 100% demo. Qui i lotti (carico → scadenza → stato)
persistono. Completa la triade sicurezza alimentare: HACCP + Shelf Life + qui.

Tabella NUOVA: trace_lotti (hotel_id TEXT) — non riusa la legacy `lotti`
(schema ISO22005 diverso, hotel_id UUID) per restare additivi e puliti.
Sicurezza: hotel_id SEMPRE dal token (require_user), mai dal client.
"""

from __future__ import annotations
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from backend.database import get_supabase
from backend.auth import require_user, UserProfile

router = APIRouter(prefix="/api/trace", tags=["Tracciabilità"])


def _sb():
    sb = get_supabase()
    if not sb:
        raise HTTPException(503, "Database non configurato")
    return sb


class Lotto(BaseModel):
    id: Optional[str] = None          # uuid DB (per update/delete)
    codice: str                       # codice lotto (es. LOT-2026-0042)
    prodotto: str = ""
    fornitore: str = ""
    carico: Optional[str] = None      # data carico YYYY-MM-DD
    scad: Optional[str] = None
    qty: str = ""
    origine: str = ""
    stato: str = "ok"                 # ok | warn | nc


@router.post("/lotto", summary="Crea/aggiorna un lotto")
async def upsert_lotto(payload: Lotto, user: UserProfile = Depends(require_user)):
    sb = _sb()
    rec = {
        "hotel_id": user.hotel_id,            # SEMPRE dal token (blindato)
        "codice": payload.codice, "prodotto": payload.prodotto,
        "fornitore": payload.fornitore, "carico": payload.carico or None,
        "scad": payload.scad or None, "qty": payload.qty,
        "origine": payload.origine, "stato": payload.stato,
        "updated_at": datetime.utcnow().isoformat(),
    }
    try:
        if payload.id:
            res = sb.table("trace_lotti").update(rec).eq("id", payload.id).eq("hotel_id", user.hotel_id).execute()
        else:
            res = sb.table("trace_lotti").insert(rec).execute()
    except Exception as e:
        raise HTTPException(500, f"Errore salvataggio: {e}")
    return {"ok": True, "lotto": (res.data or [rec])[0]}


@router.get("/lotti", summary="Lista lotti dell'hotel")
async def list_lotti(user: UserProfile = Depends(require_user)):
    sb = _sb()
    try:
        res = sb.table("trace_lotti").select("*").eq("hotel_id", user.hotel_id).order("carico", desc=True).execute()
    except Exception as e:
        raise HTTPException(500, f"Errore lettura: {e}")
    rows = res.data or []
    return {"ok": True, "lotti": rows, "totale": len(rows),
            "conformi": sum(1 for r in rows if r.get("stato") == "ok"),
            "warning": sum(1 for r in rows if r.get("stato") == "warn"),
            "nc": sum(1 for r in rows if r.get("stato") == "nc")}


@router.delete("/lotto/{lotto_id}", summary="Elimina un lotto")
async def delete_lotto(lotto_id: str, user: UserProfile = Depends(require_user)):
    sb = _sb()
    try:
        sb.table("trace_lotti").delete().eq("id", lotto_id).eq("hotel_id", user.hotel_id).execute()
    except Exception as e:
        raise HTTPException(500, f"Errore eliminazione: {e}")
    return {"ok": True}
