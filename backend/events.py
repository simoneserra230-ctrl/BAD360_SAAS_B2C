"""
BAD360.ai — Events / CRM eventi (persistenza reale, multi-tenant)
events.html era 100% demo. Qui la pipeline CRM eventi (lead → preventivo →
follow-up → chiuso) persiste davvero. È anche il ponte verso l'ecosistema:
gli eventi (servizio BAD) alimentano lo staffing via Barman Match.

Tabella: eventi (vedi supabase/events_schema.sql).
Sicurezza: hotel_id SEMPRE dal token (require_user), mai dal client.
"""

from __future__ import annotations
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from backend.database import get_supabase
from backend.auth import require_user, UserProfile
from backend.roles import require_module

router = APIRouter(prefix="/api/events", tags=["Events CRM"],
                   dependencies=[Depends(require_module("events"))])  # RBAC: solo manager+direttore+owner


def _sb():
    sb = get_supabase()
    if not sb:
        raise HTTPException(503, "Database non configurato")
    return sb


class Evento(BaseModel):
    id: Optional[str] = None
    nome: str
    tipo: str = ""
    data: Optional[str] = None        # YYYY-MM-DD
    pax: int = 0
    budget: float = 0
    stato: str = "lead"               # lead | preventivo | followup | chiuso
    follow_up: Optional[str] = None
    note: Optional[str] = None


@router.post("/evento", summary="Crea/aggiorna un evento (CRM)")
async def upsert_evento(payload: Evento, user: UserProfile = Depends(require_user)):
    sb = _sb()
    rec = {
        "hotel_id": user.hotel_id,            # SEMPRE dal token (blindato)
        "nome": payload.nome, "tipo": payload.tipo,
        "data": payload.data or None, "pax": payload.pax, "budget": payload.budget,
        "stato": payload.stato, "follow_up": payload.follow_up or None,
        "note": payload.note, "updated_at": datetime.utcnow().isoformat(),
    }
    try:
        if payload.id:
            res = sb.table("eventi").update(rec).eq("id", payload.id).eq("hotel_id", user.hotel_id).execute()
        else:
            res = sb.table("eventi").insert(rec).execute()
    except Exception as e:
        raise HTTPException(500, f"Errore salvataggio: {e}")
    return {"ok": True, "evento": (res.data or [rec])[0]}


@router.get("/eventi", summary="Lista eventi dell'hotel (CRM)")
async def list_eventi(user: UserProfile = Depends(require_user), stato: Optional[str] = None):
    sb = _sb()
    q = sb.table("eventi").select("*").eq("hotel_id", user.hotel_id)
    if stato:
        q = q.eq("stato", stato)
    try:
        res = q.order("data", desc=False).execute()
    except Exception as e:
        raise HTTPException(500, f"Errore lettura: {e}")
    rows = res.data or []
    return {"ok": True, "eventi": rows, "totale": len(rows),
            "valore_pipeline": round(sum(float(r.get("budget") or 0) for r in rows if r.get("stato") != "chiuso"), 2),
            "valore_chiuso": round(sum(float(r.get("budget") or 0) for r in rows if r.get("stato") == "chiuso"), 2)}


@router.delete("/evento/{evento_id}", summary="Elimina un evento")
async def delete_evento(evento_id: str, user: UserProfile = Depends(require_user)):
    sb = _sb()
    try:
        sb.table("eventi").delete().eq("id", evento_id).eq("hotel_id", user.hotel_id).execute()
    except Exception as e:
        raise HTTPException(500, f"Errore eliminazione: {e}")
    return {"ok": True}
