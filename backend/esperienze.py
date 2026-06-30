"""
BAD360.ai — Upsell Esperienze (Layer Ospite & Ricavi #2)  ·  IL FLYWHEEL

La struttura pubblica un CATALOGO di esperienze (aperitivo in spiaggia, cocktail
masterclass, degustazioni, tour, transfer…). L'ospite le vede e ne richiede una →
nasce una PRENOTAZIONE. Quando è confermata/erogata genera ricavo ancillare e, se
erogata da BAD/serve staff, diventa il ponte verso l'ecosistema:
  esperienza → evento BAD (events CRM) → staffing via Barman Match.

DUE LATI (come il Guest Assistant):
 - ADMIN (struttura): CRUD catalogo + gestione prenotazioni — require_user, hotel_id dal token.
 - OSPITE (pubblico): vetrina + richiesta esperienza (hotel_id dal path; scrive solo una
   'richiesta' in stato pending che la struttura poi conferma).

Tabelle: esperienze + esperienze_prenotazioni (hotel_id TEXT). Vedi supabase/esperienze_schema.sql.
Registrato in main.py: app.include_router(esperienze_router).
"""

from __future__ import annotations
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel

from backend.database import get_supabase
from backend.auth import require_user, UserProfile

router = APIRouter(prefix="/api/esperienze", tags=["Upsell Esperienze"])

STATI = {"richiesta", "confermata", "erogata", "annullata"}


def _sb():
    sb = get_supabase()
    if not sb:
        raise HTTPException(503, "Database non configurato")
    return sb


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ══ CATALOGO (admin) ═══════════════════════════════════════════════════
class Esperienza(BaseModel):
    id:          Optional[str] = None
    titolo:      str
    descrizione: Optional[str] = None
    categoria:   Optional[str] = "Esperienza"     # Aperitivo, Masterclass, Tour, Degustazione, Transfer…
    prezzo:      float = 0.0
    durata:      Optional[str] = None             # es. "2 ore"
    fornitore:   Optional[str] = "interno"        # interno | BAD | esterno
    richiede_staff: bool = False                  # → ponte Barman Match
    attivo:      bool = True


@router.get("/catalog", summary="Catalogo esperienze della struttura (admin)")
async def list_catalog(user: UserProfile = Depends(require_user)):
    sb = _sb()
    rows = (sb.table("esperienze").select("*").eq("hotel_id", user.hotel_id)
            .order("categoria").execute().data) or []
    return {"ok": True, "esperienze": rows, "totale": len(rows)}


@router.post("/catalog", summary="Aggiungi/aggiorna esperienza (admin)")
async def upsert_catalog(payload: Esperienza, user: UserProfile = Depends(require_user)):
    sb = _sb()
    data = {
        "hotel_id": user.hotel_id,
        "titolo": payload.titolo.strip(),
        "descrizione": (payload.descrizione or "").strip(),
        "categoria": (payload.categoria or "Esperienza").strip(),
        "prezzo": float(payload.prezzo or 0),
        "durata": (payload.durata or "").strip(),
        "fornitore": (payload.fornitore or "interno").strip(),
        "richiede_staff": bool(payload.richiede_staff),
        "attivo": bool(payload.attivo),
        "updated_at": _now(),
    }
    if payload.id:
        res = (sb.table("esperienze").update(data)
               .eq("id", payload.id).eq("hotel_id", user.hotel_id).execute())
        if not res.data:
            raise HTTPException(404, "Esperienza non trovata")
        return {"ok": True, "esperienza": res.data[0]}
    res = sb.table("esperienze").insert(data).execute()
    return {"ok": True, "esperienza": res.data[0] if res.data else data}


@router.delete("/catalog/{exp_id}", summary="Elimina esperienza (admin)")
async def delete_catalog(exp_id: str, user: UserProfile = Depends(require_user)):
    sb = _sb()
    sb.table("esperienze").delete().eq("id", exp_id).eq("hotel_id", user.hotel_id).execute()
    return {"ok": True}


# ══ PRENOTAZIONI (admin) ═══════════════════════════════════════════════
class Prenotazione(BaseModel):
    id:             Optional[str] = None
    esperienza_id:  Optional[str] = None
    esperienza_titolo: Optional[str] = None
    ospite_nome:    str
    ospite_contatto: Optional[str] = None
    data:           Optional[str] = None
    n_persone:      int = 1
    stato:          Optional[str] = "richiesta"
    ricavo:         Optional[float] = None
    note:           Optional[str] = None


@router.get("/prenotazioni", summary="Prenotazioni esperienze (admin)")
async def list_prenotazioni(user: UserProfile = Depends(require_user),
                            stato: Optional[str] = None):
    sb = _sb()
    q = sb.table("esperienze_prenotazioni").select("*").eq("hotel_id", user.hotel_id)
    if stato:
        q = q.eq("stato", stato)
    rows = (q.order("created_at", desc=True).execute().data) or []
    return {"ok": True, "prenotazioni": rows, "totale": len(rows)}


@router.post("/prenotazioni", summary="Crea/aggiorna prenotazione (admin)")
async def upsert_prenotazione(payload: Prenotazione, user: UserProfile = Depends(require_user)):
    sb = _sb()
    stato = (payload.stato or "richiesta").strip()
    if stato not in STATI:
        raise HTTPException(400, f"Stato non valido. Ammessi: {sorted(STATI)}")
    data = {
        "hotel_id": user.hotel_id,
        "esperienza_id": payload.esperienza_id,
        "esperienza_titolo": (payload.esperienza_titolo or "").strip(),
        "ospite_nome": payload.ospite_nome.strip(),
        "ospite_contatto": (payload.ospite_contatto or "").strip(),
        "data": payload.data,
        "n_persone": int(payload.n_persone or 1),
        "stato": stato,
        "ricavo": payload.ricavo,
        "note": (payload.note or "").strip(),
    }
    if payload.id:
        res = (sb.table("esperienze_prenotazioni").update(data)
               .eq("id", payload.id).eq("hotel_id", user.hotel_id).execute())
        if not res.data:
            raise HTTPException(404, "Prenotazione non trovata")
        return {"ok": True, "prenotazione": res.data[0]}
    data["created_at"] = _now()
    res = sb.table("esperienze_prenotazioni").insert(data).execute()
    return {"ok": True, "prenotazione": res.data[0] if res.data else data}


@router.put("/prenotazioni/{pid}/stato", summary="Cambia stato prenotazione (admin)")
async def set_stato(pid: str, user: UserProfile = Depends(require_user),
                    stato: str = Query(...), ricavo: Optional[float] = None):
    if stato not in STATI:
        raise HTTPException(400, f"Stato non valido. Ammessi: {sorted(STATI)}")
    sb = _sb()
    upd = {"stato": stato}
    if ricavo is not None:
        upd["ricavo"] = ricavo
    res = (sb.table("esperienze_prenotazioni").update(upd)
           .eq("id", pid).eq("hotel_id", user.hotel_id).execute())
    if not res.data:
        raise HTTPException(404, "Prenotazione non trovata")
    return {"ok": True, "prenotazione": res.data[0]}


@router.get("/dashboard", summary="KPI esperienze (admin)")
async def dashboard(user: UserProfile = Depends(require_user)):
    sb = _sb()
    pren = (sb.table("esperienze_prenotazioni")
            .select("stato,ricavo,esperienza_titolo").eq("hotel_id", user.hotel_id).execute().data) or []
    def c(s): return sum(1 for p in pren if p.get("stato") == s)
    ricavo = round(sum(float(p.get("ricavo") or 0) for p in pren if p.get("stato") == "erogata"), 2)
    pipeline = round(sum(float(p.get("ricavo") or 0) for p in pren
                         if p.get("stato") in ("richiesta", "confermata")), 2)
    top: dict = {}
    for p in pren:
        if p.get("stato") == "erogata":
            t = p.get("esperienza_titolo") or "—"
            top[t] = top.get(t, 0) + 1
    return {"ok": True, "kpi": {
        "richieste": c("richiesta"), "confermate": c("confermata"),
        "erogate": c("erogata"), "annullate": c("annullata"),
        "ricavo_erogato": ricavo, "pipeline_potenziale": pipeline,
        "top_esperienze": sorted(top.items(), key=lambda x: x[1], reverse=True)[:5],
    }}


# ══ OSPITE: pubblico (hotel_id dal path) ═══════════════════════════════
class RichiestaOspite(BaseModel):
    esperienza_id: Optional[str] = None
    esperienza_titolo: Optional[str] = None
    ospite_nome:   str
    ospite_contatto: Optional[str] = None
    data:          Optional[str] = None
    n_persone:     int = 1
    note:          Optional[str] = None


@router.get("/{hotel_id}/vetrina", summary="Vetrina esperienze per l'ospite (pubblico)")
async def vetrina(hotel_id: str):
    sb = get_supabase()
    if not sb:
        return {"ok": True, "esperienze": []}
    rows = (sb.table("esperienze").select("id,titolo,descrizione,categoria,prezzo,durata")
            .eq("hotel_id", hotel_id).eq("attivo", True).order("categoria").execute().data) or []
    return {"ok": True, "esperienze": rows}


@router.post("/{hotel_id}/richiesta", summary="L'ospite richiede un'esperienza (pubblico)")
async def richiesta_ospite(hotel_id: str, body: RichiestaOspite):
    nome = (body.ospite_nome or "").strip()
    if not nome:
        return {"ok": False, "error": "Nome ospite richiesto"}
    sb = get_supabase()
    if not sb:
        raise HTTPException(503, "Database non configurato")
    data = {
        "hotel_id": hotel_id,
        "esperienza_id": body.esperienza_id,
        "esperienza_titolo": (body.esperienza_titolo or "").strip(),
        "ospite_nome": nome,
        "ospite_contatto": (body.ospite_contatto or "").strip(),
        "data": body.data,
        "n_persone": int(body.n_persone or 1),
        "stato": "richiesta",
        "note": (body.note or "").strip(),
        "created_at": _now(),
    }
    sb.table("esperienze_prenotazioni").insert(data).execute()
    return {"ok": True, "stato": "richiesta",
            "messaggio": "Richiesta inviata! La struttura ti confermerà a breve."}
