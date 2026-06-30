"""
BAD360.ai — AI Guest Assistant (Layer Ospite & Ricavi #1)

La struttura carica la sua KNOWLEDGE BASE ospiti (orari check-in/out, wifi, colazione,
servizi, regole, come arrivare, esperienze…). L'ospite chiede in linguaggio naturale e
MULTILINGUA → l'AI risponde USANDO SOLO quella KB (RAG-lite: stesso approccio di BA.IA),
nella lingua dell'ospite, con fallback "contatta la reception" se l'informazione non c'è.

DUE LATI:
 - ADMIN (struttura): CRUD sulla KB — require_user, hotel_id SEMPRE dal token.
 - OSPITE (pubblico): /api/guest/{hotel_id}/ask — l'ospite NON è un utente loggato, quindi
   hotel_id arriva dal path. L'endpoint legge SOLO la guest_kb pubblica di quella struttura
   (info che la struttura ha scelto di pubblicare) + chiama l'AI. Nessun dato interno esposto.

Tabella: guest_kb (hotel_id TEXT). Vedi supabase/guest_assistant_schema.sql.
Registrato in main.py: app.include_router(guest_router).
"""

from __future__ import annotations
import re
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel

from backend.database import get_supabase
from backend.auth import require_user, UserProfile

router = APIRouter(prefix="/api/guest", tags=["AI Guest Assistant"])

MAX_CONTEXT = 5000


def _sb():
    sb = get_supabase()
    if not sb:
        raise HTTPException(503, "Database non configurato")
    return sb


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── retrieval RAG-lite (come BA.IA) ────────────────────────────────────
def _strip_accents(s: str) -> str:
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFD", s or "") if unicodedata.category(c) != "Mn")

_STOP = {"che", "con", "per", "del", "della", "una", "uno", "come", "dove", "quando", "quanto",
         "the", "and", "you", "your", "can", "what", "where", "when", "how", "are", "is",
         "ist", "wie", "wo", "wann", "der", "die", "das", "und", "qué", "como", "donde"}

def _tokenize(q: str):
    raw = re.split(r"[^a-z0-9]+", _strip_accents((q or "").lower()))
    return [t for t in raw if len(t) >= 3 and t not in _STOP]


def _retrieve(entries: list, question: str, k: int = 6) -> list:
    toks = _tokenize(question)
    if not toks:
        return entries[:k]
    scored = []
    for e in entries:
        blob = _strip_accents((str(e.get("titolo", "")) + " " + str(e.get("contenuto", "")) +
                               " " + str(e.get("categoria", ""))).lower())
        title = _strip_accents(str(e.get("titolo", "")).lower())
        score = sum(blob.count(t) + 2 * title.count(t) for t in toks)
        if score > 0:
            scored.append((score, e))
    if not scored:
        return entries[:k]          # KB piccola / nessun match → passa qualche voce comunque
    scored.sort(key=lambda x: x[0], reverse=True)
    return [e for _, e in scored[:k]]


# ══ ADMIN: CRUD knowledge base (require_user, hotel_id dal token) ═══════
class KBEntry(BaseModel):
    id:        Optional[str] = None
    categoria: Optional[str] = "Info"      # es. Check-in, Wifi, Colazione, Servizi, Regole, Esperienze
    titolo:    str
    contenuto: str
    attivo:    bool = True


@router.get("/kb", summary="KB ospiti della struttura (admin)")
async def list_kb(user: UserProfile = Depends(require_user)):
    sb = _sb()
    rows = (sb.table("guest_kb").select("*").eq("hotel_id", user.hotel_id)
            .order("categoria").execute().data) or []
    return {"ok": True, "entries": rows, "totale": len(rows)}


@router.post("/kb", summary="Aggiungi/aggiorna voce KB (admin)")
async def upsert_kb(payload: KBEntry, user: UserProfile = Depends(require_user)):
    sb = _sb()
    data = {
        "hotel_id": user.hotel_id,
        "categoria": (payload.categoria or "Info").strip(),
        "titolo": payload.titolo.strip(),
        "contenuto": payload.contenuto.strip(),
        "attivo": bool(payload.attivo),
        "updated_at": _now(),
    }
    if payload.id:
        res = (sb.table("guest_kb").update(data)
               .eq("id", payload.id).eq("hotel_id", user.hotel_id).execute())
        if not res.data:
            raise HTTPException(404, "Voce non trovata")
        return {"ok": True, "entry": res.data[0]}
    res = sb.table("guest_kb").insert(data).execute()
    return {"ok": True, "entry": res.data[0] if res.data else data}


@router.delete("/kb/{entry_id}", summary="Elimina voce KB (admin)")
async def delete_kb(entry_id: str, user: UserProfile = Depends(require_user)):
    sb = _sb()
    sb.table("guest_kb").delete().eq("id", entry_id).eq("hotel_id", user.hotel_id).execute()
    return {"ok": True}


# ══ OSPITE: pubblico (hotel_id dal path; legge SOLO la guest_kb) ════════
class GuestAsk(BaseModel):
    question: str
    lang: Optional[str] = None     # opzionale; di default risponde nella lingua della domanda


def _load_active_kb(sb, hotel_id: str) -> list:
    return (sb.table("guest_kb").select("categoria,titolo,contenuto")
            .eq("hotel_id", hotel_id).eq("attivo", True).execute().data) or []


@router.get("/{hotel_id}/suggested", summary="Domande suggerite per il widget ospite (pubblico)")
async def suggested(hotel_id: str):
    sb = get_supabase()
    if not sb:
        return {"ok": True, "suggested": []}
    kb = _load_active_kb(sb, hotel_id)
    return {"ok": True, "suggested": [e.get("titolo") for e in kb[:6] if e.get("titolo")]}


@router.post("/{hotel_id}/ask", summary="L'ospite chiede (pubblico, RAG sulla KB della struttura)")
async def guest_ask(hotel_id: str, body: GuestAsk):
    q = (body.question or "").strip()
    if not q:
        return {"ok": False, "error": "Domanda vuota"}
    sb = get_supabase()
    if not sb:
        raise HTTPException(503, "Database non configurato")

    kb = _load_active_kb(sb, hotel_id)
    if not kb:
        return {"ok": True, "stato": "kb_vuota",
                "answer": "L'assistente non è ancora configurato per questa struttura. "
                          "Per informazioni contatta direttamente la reception."}

    top = _retrieve(kb, q, k=6)
    contesto = "\n".join(
        f"• [{e.get('categoria','Info')}] {e.get('titolo','')}: {e.get('contenuto','')}" for e in top
    )[:MAX_CONTEXT]

    lang_hint = (f"Rispondi in {body.lang}. " if body.lang else
                 "Rispondi nella STESSA LINGUA della domanda dell'ospite. ")
    prompt = (
        "Sei l'assistente virtuale di una struttura ricettiva. Rispondi alla DOMANDA dell'ospite "
        "usando ESCLUSIVAMENTE le INFORMAZIONI della struttura qui sotto.\n"
        f"- {lang_hint}\n"
        "- Tono cordiale, accogliente e conciso.\n"
        "- Se l'informazione NON è presente nelle informazioni fornite, NON inventare: invita "
        "gentilmente l'ospite a contattare la reception.\n"
        "- Non inventare orari/prezzi non presenti nel testo.\n\n"
        f"INFORMAZIONI STRUTTURA:\n{contesto}\n\n"
        f"DOMANDA OSPITE: {q}\nRISPOSTA:"
    )
    from backend.ai_agents import _ask_claude
    try:
        answer = await _ask_claude(prompt, max_tokens=500)
    except Exception as e:
        raise HTTPException(502, f"AI non raggiungibile: {e}")
    return {"ok": True, "stato": "ok", "answer": (answer or "").strip(),
            "usate": [e.get("titolo") for e in top]}


# ── dashboard admin (conteggi) ─────────────────────────────────────────
@router.get("/dashboard", summary="Stato KB ospiti (admin)")
async def dashboard(user: UserProfile = Depends(require_user)):
    sb = _sb()
    rows = (sb.table("guest_kb").select("categoria,attivo").eq("hotel_id", user.hotel_id).execute().data) or []
    cats: dict = {}
    for r in rows:
        cats[r.get("categoria", "Info")] = cats.get(r.get("categoria", "Info"), 0) + 1
    return {"ok": True, "totale": len(rows),
            "attive": sum(1 for r in rows if r.get("attivo")),
            "per_categoria": cats}
