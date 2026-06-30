"""
BAD360.ai — Hotellerie F&B (persistenza reale, multi-tenant).

hotellerie.html era 100% demo. Qui rendo reale il CUORE operativo: la CARTA VINI
(+ analisi Wine Cost derivata: beverage cost % al calice e alla bottiglia).
Le altre sezioni (drink list, food pairing, F&B RevPAR, AI concierge) restano
demo/analitiche e verranno rese persistenti in seguito.

Sicurezza: hotel_id SEMPRE dal token (require_user), mai dal client.
Tabella: ht_vini (hotel_id TEXT). Vedi supabase/hotellerie_schema.sql.
"""

from __future__ import annotations
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from backend.database import get_supabase
from backend.auth import require_user, UserProfile
from backend.roles import require_module

router = APIRouter(prefix="/api/hotellerie", tags=["Hotellerie F&B"],
                   dependencies=[Depends(require_module("hotellerie"))])  # RBAC: solo manager+direttore+owner

GLASSES_PER_BOTTLE = 6  # calici/bottiglia per stimare il beverage cost al calice


def _sb():
    sb = get_supabase()
    if not sb:
        raise HTTPException(503, "Database non configurato")
    return sb


class Vino(BaseModel):
    id: Optional[str] = None
    nome: str
    prod: str = ""              # produttore
    reg: str = ""              # regione
    tipo: str = "Rosso"        # Rosso | Bianco | Spumante | ...
    annata: Optional[str] = None
    costo: float = 0           # costo di acquisto bottiglia
    calice: float = 0          # prezzo di vendita al calice
    bott: float = 0            # prezzo di vendita bottiglia (carta)
    score: int = 0
    giacenza: int = 0
    descr: str = ""            # descrizione/abbinamento (desc e' parola riservata SQL)


def _enrich(v: dict) -> dict:
    costo = float(v.get("costo") or 0)
    bott = float(v.get("bott") or 0)
    calice = float(v.get("calice") or 0)
    costo_calice = round(costo / GLASSES_PER_BOTTLE, 2) if costo else 0.0
    v["margine_bott"] = round(bott - costo, 2)
    v["pct_bott"] = round(costo / bott * 100, 1) if bott else 0.0
    v["costo_calice"] = costo_calice
    v["pct_calice"] = round(costo_calice / calice * 100, 1) if calice else 0.0
    return v


def _load(db, hotel_id: str, reg: Optional[str] = None):
    q = db.table("ht_vini").select("*").eq("hotel_id", hotel_id)
    if reg:
        q = q.eq("reg", reg)
    return q.order("reg").order("nome").execute().data or []


@router.get("/vini", summary="Carta vini dell'hotel (con beverage cost)")
async def list_vini(user: UserProfile = Depends(require_user), reg: Optional[str] = None):
    sb = _sb()
    rows = [_enrich(v) for v in _load(sb, user.hotel_id, reg)]
    regioni = sorted({v.get("reg") for v in rows if v.get("reg")})
    return {"ok": True, "vini": rows, "totale": len(rows), "regioni": regioni}


@router.post("/vini", summary="Crea/aggiorna un vino in carta")
async def upsert_vino(payload: Vino, user: UserProfile = Depends(require_user)):
    sb = _sb()
    rec = payload.dict(exclude={"id"})
    rec["hotel_id"] = user.hotel_id              # SEMPRE dal token
    try:
        if payload.id:
            res = sb.table("ht_vini").update(rec).eq("id", payload.id).eq("hotel_id", user.hotel_id).execute()
        else:
            res = sb.table("ht_vini").insert(rec).execute()
    except Exception as e:
        raise HTTPException(500, f"Errore salvataggio vino: {e}")
    return {"ok": True, "vino": _enrich((res.data or [rec])[0])}


@router.delete("/vini/{vino_id}", summary="Elimina un vino dalla carta")
async def delete_vino(vino_id: str, user: UserProfile = Depends(require_user)):
    sb = _sb()
    try:
        sb.table("ht_vini").delete().eq("id", vino_id).eq("hotel_id", user.hotel_id).execute()
    except Exception as e:
        raise HTTPException(500, f"Errore eliminazione: {e}")
    return {"ok": True}


@router.get("/winecost", summary="Analisi Wine Cost (beverage cost % carta vini)")
async def winecost(user: UserProfile = Depends(require_user)):
    sb = _sb()
    rows = [_enrich(v) for v in _load(sb, user.hotel_id)]
    avg = round(sum(v["pct_bott"] for v in rows) / len(rows), 1) if rows else 0.0
    return {"ok": True, "items": rows, "pct_medio_bott": avg, "totale": len(rows)}
