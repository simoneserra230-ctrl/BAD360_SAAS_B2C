"""
BAD360.ai — STR / Ville & Case Vacanza (niche D)

Segmento enorme in Sardegna, NON servito dall'ecosistema hotel-centrico. Gestione
MULTI-UNITÀ (case/ville): anagrafica unità + prenotazioni con check-in/out e canale +
TURNOVER PULIZIE (task auto sul check-out) + verifica ospite (anti-frode light).
La messaggistica ospite si appoggia al Guest Assistant (#1).

Sicurezza: hotel_id (=account gestore) SEMPRE dal token. Tabelle: str_unita + str_prenotazioni.
"""
from __future__ import annotations
from datetime import datetime, timezone, date
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from backend.database import get_supabase
from backend.auth import require_user, UserProfile

router = APIRouter(prefix="/api/str", tags=["STR / Case Vacanza"])
STATI = {"confermata", "in_corso", "conclusa", "annullata"}


def _sb():
    sb = get_supabase()
    if not sb:
        raise HTTPException(503, "Database non configurato")
    return sb


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Unita(BaseModel):
    id:       Optional[str] = None
    nome:     str
    indirizzo: Optional[str] = None
    capienza: int = 2
    note:     Optional[str] = None
    attivo:   bool = True


@router.get("/unita", summary="Unità gestite (admin)")
async def list_unita(user: UserProfile = Depends(require_user)):
    sb = _sb()
    rows = (sb.table("str_unita").select("*").eq("hotel_id", user.hotel_id).order("nome").execute().data) or []
    return {"ok": True, "unita": rows, "totale": len(rows)}


@router.post("/unita", summary="Aggiungi/aggiorna unità")
async def upsert_unita(payload: Unita, user: UserProfile = Depends(require_user)):
    sb = _sb()
    data = {"hotel_id": user.hotel_id, "nome": payload.nome.strip(),
            "indirizzo": (payload.indirizzo or "").strip(), "capienza": int(payload.capienza or 2),
            "note": (payload.note or "").strip(), "attivo": bool(payload.attivo), "updated_at": _now()}
    if payload.id:
        res = sb.table("str_unita").update(data).eq("id", payload.id).eq("hotel_id", user.hotel_id).execute()
        if not res.data:
            raise HTTPException(404, "Unità non trovata")
        return {"ok": True, "unita": res.data[0]}
    res = sb.table("str_unita").insert(data).execute()
    return {"ok": True, "unita": res.data[0] if res.data else data}


@router.delete("/unita/{uid}", summary="Elimina unità")
async def delete_unita(uid: str, user: UserProfile = Depends(require_user)):
    sb = _sb()
    sb.table("str_unita").delete().eq("id", uid).eq("hotel_id", user.hotel_id).execute()
    return {"ok": True}


# ── prenotazioni ───────────────────────────────────────────────────────
class Prenotazione(BaseModel):
    id:          Optional[str] = None
    unita_id:    Optional[str] = None
    unita_nome:  Optional[str] = None
    ospite_nome: str
    canale:      Optional[str] = "diretto"   # diretto | airbnb | booking | altro
    check_in:    Optional[str] = None
    check_out:   Optional[str] = None
    n_ospiti:    int = 1
    importo:     float = 0.0
    stato:       Optional[str] = "confermata"
    verificato:  bool = False
    pulizia_fatta: bool = False
    note:        Optional[str] = None


@router.get("/prenotazioni", summary="Prenotazioni (admin)")
async def list_pren(user: UserProfile = Depends(require_user), stato: Optional[str] = None):
    sb = _sb()
    q = sb.table("str_prenotazioni").select("*").eq("hotel_id", user.hotel_id)
    if stato:
        q = q.eq("stato", stato)
    rows = (q.order("check_in").execute().data) or []
    return {"ok": True, "prenotazioni": rows, "totale": len(rows)}


@router.post("/prenotazioni", summary="Crea/aggiorna prenotazione")
async def upsert_pren(payload: Prenotazione, user: UserProfile = Depends(require_user)):
    sb = _sb()
    st = (payload.stato or "confermata").strip()
    if st not in STATI:
        raise HTTPException(400, f"Stato non valido: {sorted(STATI)}")
    data = {"hotel_id": user.hotel_id, "unita_id": payload.unita_id, "unita_nome": (payload.unita_nome or "").strip(),
            "ospite_nome": payload.ospite_nome.strip(), "canale": payload.canale, "check_in": payload.check_in,
            "check_out": payload.check_out, "n_ospiti": int(payload.n_ospiti or 1), "importo": float(payload.importo or 0),
            "stato": st, "verificato": bool(payload.verificato), "pulizia_fatta": bool(payload.pulizia_fatta),
            "note": (payload.note or "").strip()}
    if payload.id:
        res = sb.table("str_prenotazioni").update(data).eq("id", payload.id).eq("hotel_id", user.hotel_id).execute()
        if not res.data:
            raise HTTPException(404, "Prenotazione non trovata")
        return {"ok": True, "prenotazione": res.data[0]}
    data["created_at"] = _now()
    res = sb.table("str_prenotazioni").insert(data).execute()
    return {"ok": True, "prenotazione": res.data[0] if res.data else data}


@router.put("/prenotazioni/{pid}/flag", summary="Imposta verifica/pulizia (admin)")
async def set_flag(pid: str, user: UserProfile = Depends(require_user),
                   verificato: Optional[bool] = None, pulizia_fatta: Optional[bool] = None):
    sb = _sb()
    upd = {}
    if verificato is not None:
        upd["verificato"] = verificato
    if pulizia_fatta is not None:
        upd["pulizia_fatta"] = pulizia_fatta
    if not upd:
        raise HTTPException(400, "Nessun flag da aggiornare")
    res = sb.table("str_prenotazioni").update(upd).eq("id", pid).eq("hotel_id", user.hotel_id).execute()
    if not res.data:
        raise HTTPException(404, "Prenotazione non trovata")
    return {"ok": True, "prenotazione": res.data[0]}


@router.get("/turnover", summary="Pulizie/turnover (check-out non ancora puliti)")
async def turnover(user: UserProfile = Depends(require_user)):
    sb = _sb()
    rows = (sb.table("str_prenotazioni").select("*").eq("hotel_id", user.hotel_id).execute().data) or []
    da_pulire = [p for p in rows if p.get("check_out") and not p.get("pulizia_fatta")
                 and p.get("stato") in ("in_corso", "conclusa", "confermata")]
    da_pulire.sort(key=lambda p: str(p.get("check_out") or ""))
    return {"ok": True, "da_pulire": da_pulire, "totale": len(da_pulire)}


@router.get("/dashboard", summary="KPI STR")
async def dashboard(user: UserProfile = Depends(require_user)):
    sb = _sb()
    un = (sb.table("str_unita").select("id").eq("hotel_id", user.hotel_id).execute().data) or []
    pr = (sb.table("str_prenotazioni").select("stato,importo,verificato,pulizia_fatta,check_out").eq("hotel_id", user.hotel_id).execute().data) or []
    da_pulire = sum(1 for p in pr if p.get("check_out") and not p.get("pulizia_fatta") and p.get("stato") != "annullata")
    non_verif = sum(1 for p in pr if not p.get("verificato") and p.get("stato") != "annullata")
    ricavo = round(sum(float(p.get("importo") or 0) for p in pr if p.get("stato") in ("in_corso", "conclusa")), 2)
    return {"ok": True, "kpi": {
        "unita": len(un), "prenotazioni": len(pr),
        "in_corso": sum(1 for p in pr if p.get("stato") == "in_corso"),
        "da_pulire": da_pulire, "ospiti_da_verificare": non_verif, "ricavo": ricavo,
    }}
