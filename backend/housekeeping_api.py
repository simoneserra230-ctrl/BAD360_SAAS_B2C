"""
BAD360.ai — Housekeeping API (persistenza reale, multi-tenant)
housekeeping.html era demo + endpoint insicuri in main.py (hotel_id dal client).
Qui Camere / Forniture / Task persistono su tabelle NUOVE (hotel_id TEXT):
hk_camere / hk_forniture / hk_task.

Sicurezza: hotel_id SEMPRE dal token (require_user), MAI dal client.
I calcoli stateless (par level, costo lavanderia, KPI benchmark) restano in
backend/housekeeping.py e non richiedono persistenza.
"""

from __future__ import annotations
from datetime import datetime, date
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from backend.database import get_supabase
from backend.auth import require_user, UserProfile

router = APIRouter(prefix="/api/hk", tags=["Housekeeping"])


def _sb():
    sb = get_supabase()
    if not sb:
        raise HTTPException(503, "Database non configurato")
    return sb


# ══ CAMERE ════════════════════════════════════════════════════════════
class Camera(BaseModel):
    id: Optional[str] = None
    numero: str
    piano: int = 1
    tipo: str = "Standard"
    stato_hk: str = "pulita"           # da_pulire|in_pulizia|pulita|ispezionata|fuori_servizio
    stato_occupazione: str = "libera"  # libera|occupata|in_partenza|bloccata
    priorita: int = 2
    note: str = ""


class CameraStato(BaseModel):
    stato_hk: Optional[str] = None
    stato_occupazione: Optional[str] = None
    priorita: Optional[int] = None


@router.post("/room", summary="Crea/aggiorna una camera")
async def upsert_room(payload: Camera, user: UserProfile = Depends(require_user)):
    sb = _sb()
    rec = {"hotel_id": user.hotel_id, "numero": payload.numero, "piano": payload.piano,
           "tipo": payload.tipo, "stato_hk": payload.stato_hk,
           "stato_occupazione": payload.stato_occupazione, "priorita": payload.priorita,
           "note": payload.note, "updated_at": datetime.utcnow().isoformat()}
    try:
        if payload.id:
            res = sb.table("hk_camere").update(rec).eq("id", payload.id).eq("hotel_id", user.hotel_id).execute()
        else:
            res = sb.table("hk_camere").insert(rec).execute()
    except Exception as e:
        raise HTTPException(500, f"Errore salvataggio camera: {e}")
    return {"ok": True, "camera": (res.data or [rec])[0]}


@router.get("/rooms", summary="Lista camere dell'hotel con stato HK")
async def list_rooms(user: UserProfile = Depends(require_user), stato_hk: Optional[str] = None):
    sb = _sb()
    q = sb.table("hk_camere").select("*").eq("hotel_id", user.hotel_id)
    if stato_hk:
        q = q.eq("stato_hk", stato_hk)
    try:
        res = q.order("piano").order("numero").execute()
    except Exception as e:
        raise HTTPException(500, f"Errore lettura camere: {e}")
    rooms = res.data or []
    def _c(s): return sum(1 for r in rooms if r.get("stato_hk") == s)
    return {"ok": True, "rooms": rooms, "totale": len(rooms),
            "da_pulire": _c("da_pulire"), "in_pulizia": _c("in_pulizia"),
            "pulite": _c("pulita"), "ispezionate": _c("ispezionata")}


@router.patch("/rooms/{room_id}", summary="Aggiorna stato di una camera")
async def update_room(room_id: str, payload: CameraStato, user: UserProfile = Depends(require_user)):
    sb = _sb()
    rec = {k: v for k, v in payload.dict().items() if v is not None}
    if not rec:
        raise HTTPException(400, "Nessun campo da aggiornare")
    rec["updated_at"] = datetime.utcnow().isoformat()
    try:
        res = sb.table("hk_camere").update(rec).eq("id", room_id).eq("hotel_id", user.hotel_id).execute()
    except Exception as e:
        raise HTTPException(500, f"Errore aggiornamento: {e}")
    return {"ok": True, "camera": (res.data or [{}])[0]}


@router.delete("/room/{room_id}", summary="Elimina una camera")
async def delete_room(room_id: str, user: UserProfile = Depends(require_user)):
    sb = _sb()
    try:
        sb.table("hk_camere").delete().eq("id", room_id).eq("hotel_id", user.hotel_id).execute()
    except Exception as e:
        raise HTTPException(500, f"Errore eliminazione: {e}")
    return {"ok": True}


# ══ FORNITURE ═════════════════════════════════════════════════════════
class Fornitura(BaseModel):
    id: Optional[str] = None
    nome: str
    categoria: str = ""
    giacenza_attuale: float = 0
    par_level: float = 0
    punto_riordino: float = 0


@router.post("/supply", summary="Crea/aggiorna una fornitura HK")
async def upsert_supply(payload: Fornitura, user: UserProfile = Depends(require_user)):
    sb = _sb()
    rec = {"hotel_id": user.hotel_id, "nome": payload.nome, "categoria": payload.categoria,
           "giacenza_attuale": payload.giacenza_attuale, "par_level": payload.par_level,
           "punto_riordino": payload.punto_riordino, "updated_at": datetime.utcnow().isoformat()}
    try:
        if payload.id:
            res = sb.table("hk_forniture").update(rec).eq("id", payload.id).eq("hotel_id", user.hotel_id).execute()
        else:
            res = sb.table("hk_forniture").insert(rec).execute()
    except Exception as e:
        raise HTTPException(500, f"Errore salvataggio fornitura: {e}")
    return {"ok": True, "fornitura": (res.data or [rec])[0]}


@router.get("/supplies", summary="Lista forniture HK con alert scorte")
async def list_supplies(user: UserProfile = Depends(require_user), solo_alert: bool = False):
    sb = _sb()
    try:
        res = sb.table("hk_forniture").select("*").eq("hotel_id", user.hotel_id).order("categoria").order("nome").execute()
    except Exception as e:
        raise HTTPException(500, f"Errore lettura forniture: {e}")
    rows = res.data or []
    for r in rows:
        r["alert"] = float(r.get("giacenza_attuale") or 0) <= float(r.get("punto_riordino") or 0)
    if solo_alert:
        rows = [r for r in rows if r["alert"]]
    return {"ok": True, "supplies": rows, "totale": len(rows),
            "alert_count": sum(1 for r in rows if r["alert"])}


@router.delete("/supply/{supply_id}", summary="Elimina una fornitura HK")
async def delete_supply(supply_id: str, user: UserProfile = Depends(require_user)):
    sb = _sb()
    try:
        sb.table("hk_forniture").delete().eq("id", supply_id).eq("hotel_id", user.hotel_id).execute()
    except Exception as e:
        raise HTTPException(500, f"Errore eliminazione: {e}")
    return {"ok": True}


# ══ TASK ══════════════════════════════════════════════════════════════
class Task(BaseModel):
    id: Optional[str] = None
    camera: str
    tipo: str = "partenza"            # partenza|stayover|deep_clean|ispezione
    stato: str = "assegnato"          # assegnato|in_corso|completato|nc
    priorita: int = 2
    durata_stimata: int = 30
    data: Optional[str] = None
    note: str = ""


class TaskStato(BaseModel):
    stato: str


@router.post("/task", summary="Crea un task di pulizia")
async def create_task(payload: Task, user: UserProfile = Depends(require_user)):
    sb = _sb()
    rec = {"hotel_id": user.hotel_id, "camera": payload.camera, "tipo": payload.tipo,
           "stato": payload.stato, "priorita": payload.priorita,
           "durata_stimata": payload.durata_stimata,
           "data": payload.data or date.today().isoformat(),
           "note": payload.note, "updated_at": datetime.utcnow().isoformat()}
    try:
        if payload.id:
            res = sb.table("hk_task").update(rec).eq("id", payload.id).eq("hotel_id", user.hotel_id).execute()
        else:
            res = sb.table("hk_task").insert(rec).execute()
    except Exception as e:
        raise HTTPException(500, f"Errore salvataggio task: {e}")
    return {"ok": True, "task": (res.data or [rec])[0]}


@router.get("/tasks/daily", summary="Task pianificati per una data (default oggi)")
async def daily_tasks(user: UserProfile = Depends(require_user), data: Optional[str] = None):
    sb = _sb()
    target = data or date.today().isoformat()
    try:
        res = sb.table("hk_task").select("*").eq("hotel_id", user.hotel_id).eq("data", target).order("priorita").execute()
    except Exception as e:
        raise HTTPException(500, f"Errore lettura task: {e}")
    tasks = res.data or []
    def _c(s): return sum(1 for t in tasks if t.get("stato") == s)
    return {"ok": True, "data": target, "tasks": tasks,
            "riepilogo": {"totale": len(tasks), "completati": _c("completato"),
                          "in_corso": _c("in_corso"), "nc": _c("nc"),
                          "da_fare": _c("assegnato")}}


@router.patch("/task/{task_id}", summary="Aggiorna lo stato di un task")
async def update_task(task_id: str, payload: TaskStato, user: UserProfile = Depends(require_user)):
    sb = _sb()
    rec = {"stato": payload.stato, "updated_at": datetime.utcnow().isoformat()}
    try:
        res = sb.table("hk_task").update(rec).eq("id", task_id).eq("hotel_id", user.hotel_id).execute()
    except Exception as e:
        raise HTTPException(500, f"Errore aggiornamento: {e}")
    return {"ok": True, "task": (res.data or [{}])[0]}


@router.delete("/task/{task_id}", summary="Elimina un task")
async def delete_task(task_id: str, user: UserProfile = Depends(require_user)):
    sb = _sb()
    try:
        sb.table("hk_task").delete().eq("id", task_id).eq("hotel_id", user.hotel_id).execute()
    except Exception as e:
        raise HTTPException(500, f"Errore eliminazione: {e}")
    return {"ok": True}
