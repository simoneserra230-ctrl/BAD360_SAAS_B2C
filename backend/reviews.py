"""
BAD360.ai — Recensioni / Reputation (persistenza reale, multi-tenant)
recensioni.html era 100% demo. Qui le recensioni e le RISPOSTE persistono
(reputation management è un pain HoReCa reale).

Tabella: recensioni (vedi supabase/reviews_schema.sql).
Sicurezza: hotel_id SEMPRE dal token (require_user), mai dal client.
"""

from __future__ import annotations
from datetime import datetime
from typing import Optional, List

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from backend.database import get_supabase
from backend.auth import require_user, UserProfile

router = APIRouter(prefix="/api/reviews", tags=["Recensioni"])


def _sb():
    sb = get_supabase()
    if not sb:
        raise HTTPException(503, "Database non configurato")
    return sb


class Review(BaseModel):
    id: Optional[str] = None
    platform: str = "google"          # google | tripadvisor | thefork | booking
    author: str = ""
    stars: int = 5
    date: Optional[str] = None         # YYYY-MM-DD
    text: str = ""
    sentiment: str = "neu"             # pos | neu | neg
    keywords: List[str] = []
    replied: bool = False
    reply: str = ""


class ReplyBody(BaseModel):
    reply: str = ""


@router.post("/review", summary="Crea/aggiorna una recensione")
async def upsert_review(payload: Review, user: UserProfile = Depends(require_user)):
    sb = _sb()
    rec = {
        "hotel_id": user.hotel_id,             # SEMPRE dal token (blindato)
        "platform": payload.platform, "author": payload.author, "stars": payload.stars,
        "date": payload.date or None, "text": payload.text, "sentiment": payload.sentiment,
        "keywords": payload.keywords, "replied": payload.replied, "reply": payload.reply,
        "updated_at": datetime.utcnow().isoformat(),
    }
    try:
        if payload.id:
            res = sb.table("recensioni").update(rec).eq("id", payload.id).eq("hotel_id", user.hotel_id).execute()
        else:
            res = sb.table("recensioni").insert(rec).execute()
    except Exception as e:
        raise HTTPException(500, f"Errore salvataggio: {e}")
    return {"ok": True, "review": (res.data or [rec])[0]}


@router.get("/list", summary="Lista recensioni dell'hotel")
async def list_reviews(user: UserProfile = Depends(require_user), platform: Optional[str] = None):
    sb = _sb()
    q = sb.table("recensioni").select("*").eq("hotel_id", user.hotel_id)
    if platform:
        q = q.eq("platform", platform)
    try:
        res = q.order("date", desc=True).execute()
    except Exception as e:
        raise HTTPException(500, f"Errore lettura: {e}")
    rows = res.data or []
    return {"ok": True, "recensioni": rows, "totale": len(rows),
            "senza_risposta": sum(1 for r in rows if not r.get("replied"))}


@router.post("/review/{review_id}/reply", summary="Pubblica la risposta a una recensione")
async def reply_review(review_id: str, body: ReplyBody, user: UserProfile = Depends(require_user)):
    sb = _sb()
    try:
        sb.table("recensioni").update({"reply": body.reply, "replied": True,
            "updated_at": datetime.utcnow().isoformat()}).eq("id", review_id).eq("hotel_id", user.hotel_id).execute()
    except Exception as e:
        raise HTTPException(500, f"Errore: {e}")
    return {"ok": True}


@router.delete("/review/{review_id}", summary="Elimina una recensione")
async def delete_review(review_id: str, user: UserProfile = Depends(require_user)):
    sb = _sb()
    try:
        sb.table("recensioni").delete().eq("id", review_id).eq("hotel_id", user.hotel_id).execute()
    except Exception as e:
        raise HTTPException(500, f"Errore eliminazione: {e}")
    return {"ok": True}
