"""
BAD360.ai — Reviews & Reputation Manager v1.0
Agente S3.3: risposta AI a recensioni multi-piattaforma (Google, TripAdvisor, TheFork, Booking).
"""

import os, json
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional, List

router = APIRouter(prefix="/api/reviews", tags=["Reviews"])

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

TONE_MAP = {
    "pos": "entusiasta e calorosa, rafforza i punti positivi citati dal cliente, invita a tornare",
    "neu": "professionale e propositiva, ringrazia per il feedback costruttivo, promette miglioramento sui punti critici",
    "neg": "empatica e risolutiva, si scusa sinceramente, spiega le azioni correttive già avviate, offre contatto diretto"
}

PLATFORM_INSTRUCTIONS = {
    "google": "Risposta pubblica Google Business. Tono professionale, max 200 parole.",
    "tripadvisor": "Risposta pubblica TripAdvisor Management Response. Menziona il nome della struttura, max 250 parole.",
    "thefork": "Risposta pubblica TheFork. Focalizzati sul ristorante e sull'esperienza culinaria, max 200 parole.",
    "booking": "Risposta pubblica Booking.com. Menziona i servizi dell'hotel, max 200 parole.",
}


class ReviewReplyRequest(BaseModel):
    review_text: str
    platform: str
    stars: int
    author: str
    sentiment: str = "neu"
    keywords: Optional[List[str]] = []
    struttura_nome: Optional[str] = "la nostra struttura"
    lingua: Optional[str] = "auto"


class BatchReplyRequest(BaseModel):
    reviews: List[ReviewReplyRequest]


@router.post("/ai-reply")
async def ai_reply(req: ReviewReplyRequest):
    """Genera una risposta AI personalizzata per una singola recensione."""
    if not ANTHROPIC_API_KEY:
        return JSONResponse({"reply": _local_reply(req), "source": "local"})

    tone = TONE_MAP.get(req.sentiment, TONE_MAP["neu"])
    platform_hint = PLATFORM_INSTRUCTIONS.get(req.platform, "Risposta pubblica professionale.")
    lang_hint = "" if req.lingua == "auto" else f"Rispondi nella stessa lingua della recensione ({req.lingua})."

    prompt = f"""Sei il responsabile della reputazione di {req.struttura_nome}, struttura ricettiva/ristorazione italiana di alto livello.

Devi scrivere una risposta pubblica alla seguente recensione ricevuta su {req.platform}.

RECENSIONE ({req.stars}/5 stelle):
"{req.review_text}"

Parole chiave citate: {', '.join(req.keywords) if req.keywords else 'nessuna'}

ISTRUZIONI:
- Tono: {tone}
- Formato: {platform_hint}
- Inizia sempre con "Gentile {req.author}," o "Caro/a {req.author},"
- {lang_hint if lang_hint else "Se la recensione è in lingua straniera, rispondi nella stessa lingua."}
- Non ripetere pari pari il testo della recensione
- Non usare formule burocratiche o generiche
- Firma con "Il Team di {req.struttura_nome}"

Scrivi SOLO il testo della risposta, senza spiegazioni aggiuntive."""

    try:
        import httpx
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": ANTHROPIC_API_KEY,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": "claude-haiku-4-5-20251001",
                    "max_tokens": 500,
                    "temperature": 0.6,
                    "messages": [{"role": "user", "content": prompt}],
                },
            )
        if resp.status_code != 200:
            raise ValueError(f"API error {resp.status_code}")
        data = resp.json()
        reply_text = data["content"][0]["text"].strip()
        return {"reply": reply_text, "source": "ai"}

    except Exception as e:
        return JSONResponse({"reply": _local_reply(req), "source": "local", "error": str(e)})


@router.post("/batch-reply")
async def batch_reply(req: BatchReplyRequest):
    """Genera risposte AI per una lista di recensioni."""
    results = []
    for review in req.reviews[:20]:
        res = await ai_reply(review)
        results.append(res)
    return {"results": results, "count": len(results)}


@router.get("/stats")
async def get_stats():
    """Statistiche aggregate (mock — in produzione legge da DB o piattaforme API)."""
    return {
        "total_reviews": 247,
        "avg_rating": 4.3,
        "response_rate_pct": 68,
        "urgent_unanswered": 3,
        "by_platform": {
            "google": {"count": 89, "avg": 4.4},
            "tripadvisor": {"count": 72, "avg": 4.2},
            "thefork": {"count": 54, "avg": 4.5},
            "booking": {"count": 32, "avg": 4.1},
        },
        "sentiment": {"pos": 78, "neu": 14, "neg": 8},
        "top_keywords_pos": ["personale","colazione","pulizia","posizione","vista","professionale"],
        "top_keywords_neg": ["attesa","WiFi","rumore","costo","parcheggio"],
    }


def _local_reply(r: ReviewReplyRequest) -> str:
    """Fallback senza API key — risposte template per sentiment."""
    if r.sentiment == "pos":
        return (f"Gentile {r.author}, la ringraziamo di cuore per la sua splendida recensione! "
                f"Siamo felici che la sua esperienza sia stata piacevole e speriamo di rivederla presto. "
                f"Il Team di {r.struttura_nome}")
    elif r.sentiment == "neg":
        return (f"Gentile {r.author}, la ringraziamo per il suo feedback. "
                f"Siamo dispiaciuti per i disagi riscontrati e abbiamo già avviato le azioni correttive necessarie. "
                f"La preghiamo di contattarci direttamente per trovare una soluzione. "
                f"Il Team di {r.struttura_nome}")
    else:
        return (f"Gentile {r.author}, la ringraziamo per la sua recensione. "
                f"Prendiamo nota dei suoi suggerimenti per migliorare continuamente il nostro servizio. "
                f"Speriamo di poterla rivedere presto. Il Team di {r.struttura_nome}")
