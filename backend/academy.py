"""
BAD360.ai — Academy (LMS interno, multi-tenant).

academy.html era demo. Qui il CUORE LMS reale: catalogo CORSI + ISCRIZIONI/progressi
del personale (chi ha fatto cosa, a che punto, completato quando). Complementare a
Certificazioni (attestati di legge con scadenza) e collegabile a SSFormazione (contenuti).

Sicurezza: hotel_id SEMPRE dal token (require_user), mai dal client.
Tabelle: academy_corsi, academy_iscrizioni (hotel_id TEXT). Vedi supabase/academy_schema.sql.
"""

from __future__ import annotations
from datetime import datetime
from typing import Optional, List

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from backend.database import get_supabase
from backend.auth import require_user, UserProfile

router = APIRouter(prefix="/api/academy", tags=["Academy LMS"])

STATI = ("non_iniziato", "in_corso", "completato")


def _sb():
    sb = get_supabase()
    if not sb:
        raise HTTPException(503, "Database non configurato")
    return sb


# ── CORSI (catalogo) ─────────────────────────────────────────────────
class Corso(BaseModel):
    id: Optional[str] = None
    titolo: str
    categoria: str = ""               # Sicurezza | Sala | Bar | Cucina | Soft skills | ...
    livello: str = "base"            # base | intermedio | avanzato
    durata_ore: float = 1
    tags: List[str] = []
    descrizione: str = ""
    link: str = ""                   # URL contenuto / SSFormazione
    attivo: bool = True


@router.post("/corso", summary="Crea/aggiorna un corso del catalogo")
async def upsert_corso(payload: Corso, user: UserProfile = Depends(require_user)):
    sb = _sb()
    rec = payload.dict(exclude={"id"})
    rec["hotel_id"] = user.hotel_id
    try:
        if payload.id:
            res = sb.table("academy_corsi").update(rec).eq("id", payload.id).eq("hotel_id", user.hotel_id).execute()
        else:
            res = sb.table("academy_corsi").insert(rec).execute()
    except Exception as e:
        raise HTTPException(500, f"Errore salvataggio corso: {e}")
    return {"ok": True, "corso": (res.data or [rec])[0]}


@router.get("/corsi", summary="Catalogo corsi dell'hotel")
async def list_corsi(user: UserProfile = Depends(require_user), livello: Optional[str] = None):
    sb = _sb()
    q = sb.table("academy_corsi").select("*").eq("hotel_id", user.hotel_id)
    if livello:
        q = q.eq("livello", livello)
    rows = q.order("categoria").order("titolo").execute().data or []
    return {"ok": True, "corsi": rows, "totale": len(rows)}


@router.delete("/corso/{corso_id}", summary="Elimina un corso (e le sue iscrizioni)")
async def delete_corso(corso_id: str, user: UserProfile = Depends(require_user)):
    sb = _sb()
    try:
        sb.table("academy_iscrizioni").delete().eq("corso_id", corso_id).eq("hotel_id", user.hotel_id).execute()
        sb.table("academy_corsi").delete().eq("id", corso_id).eq("hotel_id", user.hotel_id).execute()
    except Exception as e:
        raise HTTPException(500, f"Errore eliminazione: {e}")
    return {"ok": True}


# ── ISCRIZIONI / PROGRESSI ───────────────────────────────────────────
class Iscrizione(BaseModel):
    id: Optional[str] = None
    corso_id: str
    dipendente: str
    stato: str = "non_iniziato"
    progresso: int = 0               # 0-100


class ProgressoUpdate(BaseModel):
    stato: Optional[str] = None
    progresso: Optional[int] = None


@router.post("/iscrizione", summary="Iscrivi un dipendente a un corso")
async def upsert_iscrizione(payload: Iscrizione, user: UserProfile = Depends(require_user)):
    sb = _sb()
    rec = payload.dict(exclude={"id"})
    rec["hotel_id"] = user.hotel_id
    if rec.get("stato") not in STATI:
        rec["stato"] = "non_iniziato"
    try:
        if payload.id:
            res = sb.table("academy_iscrizioni").update(rec).eq("id", payload.id).eq("hotel_id", user.hotel_id).execute()
        else:
            res = sb.table("academy_iscrizioni").insert(rec).execute()
    except Exception as e:
        raise HTTPException(500, f"Errore iscrizione: {e}")
    return {"ok": True, "iscrizione": (res.data or [rec])[0]}


@router.get("/iscrizioni", summary="Iscrizioni/progressi (opz. filtra per corso)")
async def list_iscrizioni(user: UserProfile = Depends(require_user), corso_id: Optional[str] = None):
    sb = _sb()
    q = sb.table("academy_iscrizioni").select("*").eq("hotel_id", user.hotel_id)
    if corso_id:
        q = q.eq("corso_id", corso_id)
    rows = q.order("dipendente").execute().data or []
    return {"ok": True, "iscrizioni": rows, "totale": len(rows)}


@router.patch("/iscrizione/{isc_id}", summary="Aggiorna stato/progresso di un'iscrizione")
async def update_iscrizione(isc_id: str, payload: ProgressoUpdate, user: UserProfile = Depends(require_user)):
    sb = _sb()
    rec = {}
    if payload.progresso is not None:
        rec["progresso"] = max(0, min(100, payload.progresso))
    if payload.stato in STATI:
        rec["stato"] = payload.stato
    # auto: progresso 100 => completato + data
    if rec.get("progresso") == 100 and "stato" not in rec:
        rec["stato"] = "completato"
    if rec.get("stato") == "completato":
        rec["data_completamento"] = datetime.utcnow().date().isoformat()
    if not rec:
        raise HTTPException(400, "Nessun campo da aggiornare")
    try:
        res = sb.table("academy_iscrizioni").update(rec).eq("id", isc_id).eq("hotel_id", user.hotel_id).execute()
    except Exception as e:
        raise HTTPException(500, f"Errore aggiornamento: {e}")
    return {"ok": True, "iscrizione": (res.data or [{}])[0]}


@router.delete("/iscrizione/{isc_id}", summary="Rimuovi un'iscrizione")
async def delete_iscrizione(isc_id: str, user: UserProfile = Depends(require_user)):
    sb = _sb()
    try:
        sb.table("academy_iscrizioni").delete().eq("id", isc_id).eq("hotel_id", user.hotel_id).execute()
    except Exception as e:
        raise HTTPException(500, f"Errore eliminazione: {e}")
    return {"ok": True}


# ── DASHBOARD ────────────────────────────────────────────────────────
@router.get("/dashboard", summary="KPI LMS: corsi, iscrizioni, completamento")
async def dashboard(user: UserProfile = Depends(require_user)):
    sb = _sb()
    hid = user.hotel_id
    corsi = sb.table("academy_corsi").select("*").eq("hotel_id", hid).execute().data or []
    isc = sb.table("academy_iscrizioni").select("*").eq("hotel_id", hid).execute().data or []
    completati = sum(1 for i in isc if i.get("stato") == "completato")
    in_corso = sum(1 for i in isc if i.get("stato") == "in_corso")
    completion = round(completati / len(isc) * 100, 1) if isc else 0.0
    return {"ok": True,
            "corsi_totali": len(corsi),
            "corsi_attivi": sum(1 for c in corsi if c.get("attivo")),
            "iscrizioni": len(isc),
            "completati": completati,
            "in_corso": in_corso,
            "completion_rate": completion}
