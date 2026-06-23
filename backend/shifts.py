"""
BAD360.ai — Turni & Staff (persistenza reale, multi-tenant)
Terzo modulo "fondamenta dati". Prima shiftmanager.html era 100% demo
(0 chiamate backend). Qui anagrafica staff + turni persistono davvero.

Tabelle: staff, turni (vedi supabase/shifts_schema.sql).
Sicurezza: hotel_id SEMPRE dal token (require_user), mai dal client.
"""

from __future__ import annotations
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel

from backend.database import get_supabase
from backend.auth import require_user, UserProfile

router = APIRouter(prefix="/api/shifts", tags=["Turni & Staff"])


def _sb():
    sb = get_supabase()
    if not sb:
        raise HTTPException(503, "Database non configurato")
    return sb


# ── Modelli ───────────────────────────────────────────────────────────
class StaffMember(BaseModel):
    id: Optional[str] = None
    nome: str
    ruolo: str = ""
    reparto: str = ""
    ore_sett: float = 40


class Turno(BaseModel):
    id: Optional[str] = None
    dipendente: str
    ruolo: str = ""
    data: str                     # YYYY-MM-DD
    turno: str = ""               # es. "Mattina 07:00–15:00"
    ore: str = "8h"
    reparto: str = ""
    stato: str = "ok"             # ok | riposo | warn


# ── STAFF (anagrafica dipendenti) ─────────────────────────────────────
@router.post("/staff", summary="Crea/aggiorna un dipendente")
async def upsert_staff(payload: StaffMember, user: UserProfile = Depends(require_user)):
    sb = _sb()
    rec = {"hotel_id": user.hotel_id, "nome": payload.nome, "ruolo": payload.ruolo,
           "reparto": payload.reparto, "ore_sett": payload.ore_sett,
           "updated_at": datetime.utcnow().isoformat()}
    try:
        if payload.id:
            res = sb.table("staff").update(rec).eq("id", payload.id).eq("hotel_id", user.hotel_id).execute()
        else:
            res = sb.table("staff").insert(rec).execute()
    except Exception as e:
        raise HTTPException(500, f"Errore salvataggio: {e}")
    return {"ok": True, "staff": (res.data or [rec])[0]}


@router.get("/staff", summary="Lista dipendenti dell'hotel")
async def list_staff(user: UserProfile = Depends(require_user)):
    sb = _sb()
    try:
        res = sb.table("staff").select("*").eq("hotel_id", user.hotel_id).order("nome").execute()
    except Exception as e:
        raise HTTPException(500, f"Errore lettura: {e}")
    return {"ok": True, "staff": res.data or []}


@router.delete("/staff/{staff_id}", summary="Elimina un dipendente")
async def delete_staff(staff_id: str, user: UserProfile = Depends(require_user)):
    sb = _sb()
    try:
        sb.table("staff").delete().eq("id", staff_id).eq("hotel_id", user.hotel_id).execute()
    except Exception as e:
        raise HTTPException(500, f"Errore eliminazione: {e}")
    return {"ok": True}


# ── TURNI (pianificazione) ────────────────────────────────────────────
@router.post("/turno", summary="Crea/aggiorna un turno")
async def upsert_turno(payload: Turno, user: UserProfile = Depends(require_user)):
    sb = _sb()
    rec = {"hotel_id": user.hotel_id, "dipendente": payload.dipendente, "ruolo": payload.ruolo,
           "data": payload.data, "turno": payload.turno, "ore": payload.ore,
           "reparto": payload.reparto, "stato": payload.stato,
           "updated_at": datetime.utcnow().isoformat()}
    try:
        if payload.id:
            res = sb.table("turni").update(rec).eq("id", payload.id).eq("hotel_id", user.hotel_id).execute()
        else:
            res = sb.table("turni").insert(rec).execute()
    except Exception as e:
        raise HTTPException(500, f"Errore salvataggio: {e}")
    return {"ok": True, "turno": (res.data or [rec])[0]}


@router.get("/turni", summary="Lista turni (filtro per intervallo date)")
async def list_turni(user: UserProfile = Depends(require_user),
                     dal: Optional[str] = Query(None), al: Optional[str] = Query(None),
                     limit: int = Query(300, ge=1, le=1000)):
    sb = _sb()
    q = sb.table("turni").select("*").eq("hotel_id", user.hotel_id)
    if dal:
        q = q.gte("data", dal)
    if al:
        q = q.lte("data", al)
    try:
        res = q.order("data", desc=True).limit(limit).execute()
    except Exception as e:
        raise HTTPException(500, f"Errore lettura: {e}")
    return {"ok": True, "turni": res.data or [], "totale": len(res.data or [])}


@router.delete("/turno/{turno_id}", summary="Elimina un turno")
async def delete_turno(turno_id: str, user: UserProfile = Depends(require_user)):
    sb = _sb()
    try:
        sb.table("turni").delete().eq("id", turno_id).eq("hotel_id", user.hotel_id).execute()
    except Exception as e:
        raise HTTPException(500, f"Errore eliminazione: {e}")
    return {"ok": True}
