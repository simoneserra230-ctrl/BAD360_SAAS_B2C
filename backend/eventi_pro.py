"""
BAD360.ai — AI Event/Wedding Coordinator (niche A)

Gestione eventi/matrimoni: anagrafica evento + fornitori con budget tracking +
timeline/checklist generata dall'AI. È il mestiere di BAD reso scalabile e vendibile.
Si aggancia all'ecosistema: un evento usa le Esperienze, diventa lead nel events CRM,
e lo staff arriva da Barman Match.

Sicurezza: hotel_id SEMPRE dal token (require_user). Tabelle: eventi_pro + evento_fornitori.
"""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from backend.database import get_supabase
from backend.auth import require_user, UserProfile
from backend.roles import require_module

router = APIRouter(prefix="/api/eventipro", tags=["Event/Wedding Coordinator"], dependencies=[Depends(require_module("eventipro"))])

STATI = {"lead", "pianificazione", "confermato", "concluso", "annullato"}
DISCLAIMER = "⚠️ Bozza generata da AI — verifica tempistiche, costi e fornitori prima di usarla col cliente."


def _sb():
    sb = get_supabase()
    if not sb:
        raise HTTPException(503, "Database non configurato")
    return sb


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Evento(BaseModel):
    id:         Optional[str] = None
    nome:       str
    tipo:       Optional[str] = "matrimonio"     # matrimonio | aziendale | privato | gala
    data:       Optional[str] = None
    n_invitati: int = 0
    budget:     float = 0.0
    location:   Optional[str] = None
    stato:      Optional[str] = "lead"
    note:       Optional[str] = None


@router.get("/eventi", summary="Lista eventi (admin)")
async def list_eventi(user: UserProfile = Depends(require_user), stato: Optional[str] = None):
    sb = _sb()
    q = sb.table("eventi_pro").select("*").eq("hotel_id", user.hotel_id)
    if stato:
        q = q.eq("stato", stato)
    rows = (q.order("data").execute().data) or []
    return {"ok": True, "eventi": rows, "totale": len(rows)}


@router.post("/eventi", summary="Crea/aggiorna evento")
async def upsert_evento(payload: Evento, user: UserProfile = Depends(require_user)):
    sb = _sb()
    st = (payload.stato or "lead").strip()
    if st not in STATI:
        raise HTTPException(400, f"Stato non valido: {sorted(STATI)}")
    data = {
        "hotel_id": user.hotel_id, "nome": payload.nome.strip(), "tipo": payload.tipo,
        "data": payload.data, "n_invitati": int(payload.n_invitati or 0),
        "budget": float(payload.budget or 0), "location": (payload.location or "").strip(),
        "stato": st, "note": (payload.note or "").strip(), "updated_at": _now(),
    }
    if payload.id:
        res = sb.table("eventi_pro").update(data).eq("id", payload.id).eq("hotel_id", user.hotel_id).execute()
        if not res.data:
            raise HTTPException(404, "Evento non trovato")
        return {"ok": True, "evento": res.data[0]}
    data["created_at"] = _now()
    res = sb.table("eventi_pro").insert(data).execute()
    return {"ok": True, "evento": res.data[0] if res.data else data}


@router.delete("/eventi/{eid}", summary="Elimina evento (+ fornitori)")
async def delete_evento(eid: str, user: UserProfile = Depends(require_user)):
    sb = _sb()
    sb.table("evento_fornitori").delete().eq("evento_id", eid).eq("hotel_id", user.hotel_id).execute()
    sb.table("eventi_pro").delete().eq("id", eid).eq("hotel_id", user.hotel_id).execute()
    return {"ok": True}


# ── fornitori / budget ─────────────────────────────────────────────────
class Fornitore(BaseModel):
    id:        Optional[str] = None
    evento_id: str
    categoria: Optional[str] = "Fornitore"   # Catering, Fiori, Musica, Foto, Staff, Allestimento…
    nome:      Optional[str] = None
    costo:     float = 0.0
    stato:     Optional[str] = "da_contattare"  # da_contattare | contattato | confermato
    note:      Optional[str] = None


@router.get("/eventi/{eid}/fornitori", summary="Fornitori dell'evento + budget")
async def list_fornitori(eid: str, user: UserProfile = Depends(require_user)):
    sb = _sb()
    ev = (sb.table("eventi_pro").select("budget,nome").eq("id", eid).eq("hotel_id", user.hotel_id).execute().data) or []
    if not ev:
        raise HTTPException(404, "Evento non trovato")
    forn = (sb.table("evento_fornitori").select("*").eq("evento_id", eid).eq("hotel_id", user.hotel_id).execute().data) or []
    speso = round(sum(float(f.get("costo") or 0) for f in forn), 2)
    budget = float(ev[0].get("budget") or 0)
    return {"ok": True, "fornitori": forn, "budget": budget, "speso": speso,
            "residuo": round(budget - speso, 2), "perc_usato": round(speso / budget * 100, 1) if budget else 0}


@router.post("/fornitori", summary="Aggiungi/aggiorna fornitore")
async def upsert_fornitore(payload: Fornitore, user: UserProfile = Depends(require_user)):
    sb = _sb()
    data = {
        "hotel_id": user.hotel_id, "evento_id": payload.evento_id,
        "categoria": payload.categoria, "nome": (payload.nome or "").strip(),
        "costo": float(payload.costo or 0), "stato": payload.stato, "note": (payload.note or "").strip(),
    }
    if payload.id:
        res = sb.table("evento_fornitori").update(data).eq("id", payload.id).eq("hotel_id", user.hotel_id).execute()
        if not res.data:
            raise HTTPException(404, "Fornitore non trovato")
        return {"ok": True, "fornitore": res.data[0]}
    res = sb.table("evento_fornitori").insert(data).execute()
    return {"ok": True, "fornitore": res.data[0] if res.data else data}


@router.delete("/fornitori/{fid}", summary="Elimina fornitore")
async def delete_fornitore(fid: str, user: UserProfile = Depends(require_user)):
    sb = _sb()
    sb.table("evento_fornitori").delete().eq("id", fid).eq("hotel_id", user.hotel_id).execute()
    return {"ok": True}


@router.get("/dashboard", summary="KPI eventi")
async def dashboard(user: UserProfile = Depends(require_user)):
    sb = _sb()
    ev = (sb.table("eventi_pro").select("stato,budget,n_invitati").eq("hotel_id", user.hotel_id).execute().data) or []
    def c(s): return sum(1 for e in ev if e.get("stato") == s)
    return {"ok": True, "kpi": {
        "totale": len(ev), "lead": c("lead"), "pianificazione": c("pianificazione"),
        "confermati": c("confermato"), "conclusi": c("concluso"),
        "budget_pipeline": round(sum(float(e.get("budget") or 0) for e in ev if e.get("stato") in ("lead", "pianificazione", "confermato")), 2),
        "invitati_totali": sum(int(e.get("n_invitati") or 0) for e in ev),
    }}


# ── AI: timeline / checklist evento ────────────────────────────────────
@router.post("/eventi/{eid}/ai-timeline", summary="Genera timeline/checklist evento (AI)")
async def ai_timeline(eid: str, user: UserProfile = Depends(require_user)):
    sb = _sb()
    ev = (sb.table("eventi_pro").select("*").eq("id", eid).eq("hotel_id", user.hotel_id).execute().data) or []
    if not ev:
        raise HTTPException(404, "Evento non trovato")
    e = ev[0]
    prompt = (
        "Sei un wedding/event planner esperto. Genera una TIMELINE operativa con CHECKLIST per questo "
        "evento, organizzata per fasi temporali (es. 6 mesi prima, 3 mesi, 1 mese, settimana, giorno-evento). "
        "Per ogni fase elenca i task concreti (fornitori da confermare, pagamenti, sopralluoghi, menù, allestimento, staff). "
        "Markdown conciso. Non inventare costi precisi: se servono importi scrivi '[da definire]'.\n\n"
        f"EVENTO: {e.get('nome')} · tipo: {e.get('tipo')} · data: {e.get('data','n/d')} · "
        f"invitati: {e.get('n_invitati')} · location: {e.get('location','n/d')} · budget: {e.get('budget')}€"
    )
    from backend.ai_agents import _ask_claude
    try:
        out = await _ask_claude(prompt, max_tokens=900)
    except Exception as ex:
        raise HTTPException(502, f"AI non raggiungibile: {ex}")
    return {"ok": True, "timeline_markdown": (out or "").strip(), "disclaimer": DISCLAIMER}
