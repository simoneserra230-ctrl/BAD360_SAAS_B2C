"""
BAD360.ai — Drink Cost / Ricette (persistenza reale, multi-tenant)
Quarto modulo "fondamenta dati". Il drink cost calculator di bevmanager.html
calcolava il costo ma NON salvava le ricette (SAVED_RECIPES era demo).
Qui le ricette drink persistono: costo e cost% calcolati lato server.

Tabella: drink_recipes (vedi supabase/drinks_schema.sql).
Sicurezza: hotel_id SEMPRE dal token (require_user), mai dal client.
NB: modulo nuovo e PULITO — il vecchio fb_cost.py (/api/fb) usa hotel_id dal
client ed httpx grezzo; questo lo sostituisce per il flusso drink cost.
"""

from __future__ import annotations
from datetime import datetime
from typing import Optional, List

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from backend.database import get_supabase
from backend.auth import require_user, UserProfile
from backend.roles import require_module

router = APIRouter(prefix="/api/drinks", tags=["Drink Cost"],
                   dependencies=[Depends(require_module("drinkcost"))])  # RBAC: solo manager+direttore+owner


def _sb():
    sb = get_supabase()
    if not sb:
        raise HTTPException(503, "Database non configurato")
    return sb


class DrinkIng(BaseModel):
    ing: str = ""
    qty: float = 0
    unit: str = "cl"
    cost: float = 0               # €/unità


class DrinkRecipe(BaseModel):
    id: Optional[str] = None
    nome: str
    prezzo: float = 0
    ingredienti: List[DrinkIng] = []
    note: Optional[str] = None


def _compute(prezzo: float, ingredienti: List[DrinkIng]) -> dict:
    costo = round(sum((i.qty or 0) * (i.cost or 0) for i in ingredienti), 2)
    costpct = round(costo / prezzo * 100, 1) if prezzo else 0.0
    margine = round((prezzo or 0) - costo, 2)
    return {"costo": costo, "costpct": costpct, "margine": margine}


@router.post("/recipe", summary="Salva/aggiorna una ricetta drink (costo calcolato)")
async def upsert_recipe(payload: DrinkRecipe, user: UserProfile = Depends(require_user)):
    sb = _sb()
    calc = _compute(payload.prezzo, payload.ingredienti)
    rec = {
        "hotel_id": user.hotel_id,              # SEMPRE dal token (blindato)
        "nome": payload.nome, "prezzo": payload.prezzo,
        "costo": calc["costo"], "costpct": calc["costpct"],
        "ingredienti": [i.dict() for i in payload.ingredienti],
        "note": payload.note, "updated_at": datetime.utcnow().isoformat(),
    }
    try:
        if payload.id:
            res = sb.table("drink_recipes").update(rec).eq("id", payload.id).eq("hotel_id", user.hotel_id).execute()
        else:
            res = sb.table("drink_recipes").insert(rec).execute()
    except Exception as e:
        raise HTTPException(500, f"Errore salvataggio: {e}")
    saved = (res.data or [rec])[0]
    return {"ok": True, "recipe": {**saved, **calc}}


@router.get("/recipes", summary="Lista ricette drink dell'hotel")
async def list_recipes(user: UserProfile = Depends(require_user)):
    sb = _sb()
    try:
        res = sb.table("drink_recipes").select("*").eq("hotel_id", user.hotel_id).order("nome").execute()
    except Exception as e:
        raise HTTPException(500, f"Errore lettura: {e}")
    return {"ok": True, "recipes": res.data or []}


@router.delete("/recipe/{recipe_id}", summary="Elimina una ricetta drink")
async def delete_recipe(recipe_id: str, user: UserProfile = Depends(require_user)):
    sb = _sb()
    try:
        sb.table("drink_recipes").delete().eq("id", recipe_id).eq("hotel_id", user.hotel_id).execute()
    except Exception as e:
        raise HTTPException(500, f"Errore eliminazione: {e}")
    return {"ok": True}
