"""
BAD360.ai — Quality Manager / multi-cliente (layer trasversale).

Un consulente "Quality Manager" segue la compliance di PIU' strutture. Qui:
  - LATO STRUTTURA: il locale CONCEDE l'accesso al proprio QM (grant) — può concedere
    SOLO sui propri dati (hotel_id dal token). Può revocare.
  - LATO QM: vede il PORTFOLIO = solo le strutture che lo hanno autorizzato, con un
    cruscotto compliance aggregato (scadenze Certificazioni: personale + licenze + aziendali).

Sicurezza: nessun QM può auto-aggiungersi un hotel. Il grant lo crea la struttura,
con hotel_id SEMPRE dal token. Il portfolio del QM filtra per qm_uid = la sua email/id.
Tabella: qm_portfolio. Vedi supabase/qm_schema.sql. ⚠️ migration da applicare.
"""

from __future__ import annotations
from datetime import date
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from backend.database import get_supabase
from backend.auth import require_user, UserProfile

router = APIRouter(prefix="/api/qm", tags=["Quality Manager"])

ALERT_DAYS = 60


def _sb():
    sb = get_supabase()
    if not sb:
        raise HTTPException(503, "Database non configurato")
    return sb


def _parse(s):
    if not s:
        return None
    try:
        return date.fromisoformat(str(s)[:10])
    except ValueError:
        return None


def _status(scadenza):
    d = _parse(scadenza)
    if d is None:
        return "permanente"
    g = (d - date.today()).days
    if g < 0:
        return "scaduto"
    if g <= ALERT_DAYS:
        return "in_scadenza"
    return "ok"


# ══ LATO STRUTTURA: concedi / elenca / revoca l'accesso al QM ═════════
class Grant(BaseModel):
    qm_email: str
    cliente_nome: str = ""        # come la struttura vuole essere etichettata dal QM


@router.post("/grant", summary="La struttura concede l'accesso a un Quality Manager")
async def grant(body: Grant, user: UserProfile = Depends(require_user)):
    sb = _sb()
    qm = (body.qm_email or "").strip().lower()
    if not qm:
        raise HTTPException(400, "Email del Quality Manager mancante")
    rec = {"qm_uid": qm, "hotel_id": user.hotel_id,           # SOLO il proprio hotel
           "cliente_nome": body.cliente_nome or user.hotel_id, "granted_by": user.id}
    try:
        # evita duplicati (stesso qm sullo stesso hotel)
        existing = sb.table("qm_portfolio").select("id").eq("qm_uid", qm).eq("hotel_id", user.hotel_id).execute().data
        if existing:
            sb.table("qm_portfolio").update({"cliente_nome": rec["cliente_nome"]}).eq("id", existing[0]["id"]).execute()
            return {"ok": True, "id": existing[0]["id"], "updated": True}
        res = sb.table("qm_portfolio").insert(rec).execute()
    except Exception as e:
        raise HTTPException(500, f"Errore grant: {e}")
    return {"ok": True, "grant": (res.data or [rec])[0]}


@router.get("/granted", summary="Quality Manager autorizzati da questa struttura")
async def granted(user: UserProfile = Depends(require_user)):
    sb = _sb()
    rows = sb.table("qm_portfolio").select("*").eq("hotel_id", user.hotel_id).execute().data or []
    return {"ok": True, "manager": rows, "totale": len(rows)}


@router.delete("/grant/{grant_id}", summary="Revoca l'accesso a un QM (solo sui propri dati)")
async def revoke(grant_id: str, user: UserProfile = Depends(require_user)):
    sb = _sb()
    try:
        sb.table("qm_portfolio").delete().eq("id", grant_id).eq("hotel_id", user.hotel_id).execute()
    except Exception as e:
        raise HTTPException(500, f"Errore revoca: {e}")
    return {"ok": True}


# ══ LATO QM: portfolio compliance aggregato ═══════════════════════════
def _count_scadenze(rows):
    out = {"scaduto": 0, "in_scadenza": 0, "totale": len(rows)}
    for r in rows:
        s = _status(r.get("data_scadenza"))
        if s in out:
            out[s] += 1
    return out


@router.get("/portfolio", summary="Portfolio del QM: compliance aggregata dei clienti autorizzati")
async def portfolio(user: UserProfile = Depends(require_user)):
    sb = _sb()
    qm = (user.id or "").strip().lower()
    links = sb.table("qm_portfolio").select("*").eq("qm_uid", qm).execute().data or []
    hotels = [l["hotel_id"] for l in links]
    nome = {l["hotel_id"]: l.get("cliente_nome") or l["hotel_id"] for l in links}
    if not hotels:
        return {"ok": True, "is_qm": False, "clienti": [], "totali": {"scaduto": 0, "in_scadenza": 0, "totale": 0}}

    # una query per tabella su tutti gli hotel del QM, poi raggruppo
    def by_hotel(table):
        rows = sb.table(table).select("hotel_id,data_scadenza").in_("hotel_id", hotels).execute().data or []
        g = {h: [] for h in hotels}
        for r in rows:
            g.setdefault(r.get("hotel_id"), []).append(r)
        return g
    try:
        pers = by_hotel("cert_personale")
        lic = by_hotel("cert_licenze")
        az = by_hotel("cert_aziendali")
    except Exception as e:
        raise HTTPException(500, f"Errore portfolio: {e}")

    clienti = []
    tot = {"scaduto": 0, "in_scadenza": 0, "totale": 0}
    for h in hotels:
        allrows = (pers.get(h) or []) + (lic.get(h) or []) + (az.get(h) or [])
        cnt = _count_scadenze(allrows)
        for k in tot:
            tot[k] += cnt[k]
        clienti.append({"hotel_id": h, "cliente_nome": nome[h], **cnt})
    clienti.sort(key=lambda c: (c["scaduto"], c["in_scadenza"]), reverse=True)
    return {"ok": True, "is_qm": True, "clienti": clienti, "totali": tot}
