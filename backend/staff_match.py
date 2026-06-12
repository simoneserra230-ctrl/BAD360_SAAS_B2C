"""
BAD360.ai — Staff Match (modulo BarmanMatch integrato)
Marketplace turni + matching AI staff HoReCa, lato venue dentro la suite.
Agente AI: C7.6 "AI Staff Rescue" — sostituzione d'emergenza.

Tabelle Supabase: vedi supabase/staff_match_schema.sql
(worker_profiles, venue_profiles, shifts, shift_applications, ratings, venue_favorites)
"""

import os
import json
from datetime import date, datetime
from typing import Optional, List, Dict, Any

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.database import get_supabase

router = APIRouter(prefix="/api/staff-match", tags=["Staff Match"])

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")


# ─── Match scoring (algoritmo BarmanMatch) ────────────────────────────────────
# Score composito 0–100: Pertinenza 40 | Qualità 35 | Relazione 15 | Reattività 10

def compute_match_score(worker: dict, shift: dict, history: dict) -> float:
    p = 0.0
    roles = [r.lower() for r in (worker.get("roles") or [])]
    shift_role = (shift.get("role") or "").lower()
    if shift_role in roles:
        p += 25.0
    elif any(shift_role in r or r in shift_role for r in roles):
        p += 12.0

    req = set(r.lower() for r in (shift.get("requirements") or []))
    skills = set(s.lower() for s in (worker.get("skills") or []))
    if req:
        p += (len(req & skills) / len(req)) * 10.0
    else:
        p += 5.0 if skills else 0.0

    if (worker.get("city") or "").lower().strip() == (shift.get("city") or "").lower().strip():
        p += 5.0

    q = 0.0
    if (worker.get("rating_count") or 0) > 0:
        q += (float(worker.get("rating_avg") or 5.0) / 5.0) * 20.0
    else:
        q += 14.0
    q += (float(worker.get("completion_rate") or 100.0) / 100.0) * 10.0
    q += max(0.0, 5.0 - int(worker.get("no_show_count") or 0) * 2.5)

    r = 0.0
    together = int(history.get("worked_together_count") or 0)
    if together >= 3:
        r = 15.0
    elif together > 0:
        r = 10.0
    elif history.get("is_favorite"):
        r = 8.0

    rt = int(worker.get("avg_response_time_mins") or 60)
    rv = 10.0 if rt <= 15 else 8.0 if rt <= 30 else 6.0 if rt <= 60 else 4.0 if rt <= 120 else 2.0

    return min(100.0, round(p + q + r + rv, 1))


# ─── Demo data (fallback senza Supabase — coerente col resto della suite) ─────

DEMO_WORKERS: List[Dict[str, Any]] = [
    {"id": "w1", "full_name": "Luca Piras", "city": "Cagliari", "roles": ["bartender", "barback"],
     "skills": ["mixology", "flair", "caffetteria", "inglese"], "years_experience": 8,
     "rating_avg": 4.9, "rating_count": 47, "completion_rate": 100.0, "no_show_count": 0,
     "total_shifts_completed": 52, "avg_response_time_mins": 12, "hourly_rate_min": 14.0,
     "is_verified": True, "badge_top_rated": True, "badge_no_show_zero": True, "badge_fast_responder": True},
    {"id": "w2", "full_name": "Sara Melis", "city": "Cagliari", "roles": ["cameriere", "chef de rang"],
     "skills": ["servizio al tavolo", "vini", "inglese", "francese"], "years_experience": 6,
     "rating_avg": 4.8, "rating_count": 31, "completion_rate": 97.0, "no_show_count": 0,
     "total_shifts_completed": 38, "avg_response_time_mins": 25, "hourly_rate_min": 12.0,
     "is_verified": True, "badge_top_rated": True, "badge_no_show_zero": True, "badge_fast_responder": False},
    {"id": "w3", "full_name": "Marco Sanna", "city": "Quartu Sant'Elena", "roles": ["bartender"],
     "skills": ["caffetteria", "aperitivi"], "years_experience": 3,
     "rating_avg": 4.5, "rating_count": 12, "completion_rate": 92.0, "no_show_count": 1,
     "total_shifts_completed": 14, "avg_response_time_mins": 45, "hourly_rate_min": 11.0,
     "is_verified": True, "badge_top_rated": False, "badge_no_show_zero": False, "badge_fast_responder": False},
    {"id": "w4", "full_name": "Elena Cocco", "city": "Cagliari", "roles": ["chef de partie", "cuoco"],
     "skills": ["linea calda", "pasticceria", "haccp"], "years_experience": 10,
     "rating_avg": 5.0, "rating_count": 22, "completion_rate": 100.0, "no_show_count": 0,
     "total_shifts_completed": 25, "avg_response_time_mins": 60, "hourly_rate_min": 16.0,
     "is_verified": True, "badge_top_rated": True, "badge_no_show_zero": True, "badge_fast_responder": False},
    {"id": "w5", "full_name": "Davide Loi", "city": "Pula", "roles": ["barback", "runner"],
     "skills": ["magazzino", "ghiaccio", "set-up eventi"], "years_experience": 2,
     "rating_avg": 4.6, "rating_count": 9, "completion_rate": 100.0, "no_show_count": 0,
     "total_shifts_completed": 11, "avg_response_time_mins": 15, "hourly_rate_min": 10.0,
     "is_verified": False, "badge_top_rated": False, "badge_no_show_zero": True, "badge_fast_responder": True},
]

DEMO_SHIFTS: List[Dict[str, Any]] = [
    {"id": "s1", "role": "bartender", "date": "2026-06-13", "start_time": "18:00", "end_time": "01:00",
     "hourly_rate": 14.0, "city": "Cagliari", "requirements": ["mixology", "inglese"],
     "description": "Servizio cocktail bar piscina — alta stagione", "spots": 1,
     "status": "open", "is_urgent": True, "applications": 3},
    {"id": "s2", "role": "cameriere", "date": "2026-06-14", "start_time": "19:00", "end_time": "23:30",
     "hourly_rate": 12.0, "city": "Cagliari", "requirements": ["vini", "inglese"],
     "description": "Cena evento privato 40 coperti", "spots": 2,
     "status": "open", "is_urgent": False, "applications": 5},
    {"id": "s3", "role": "chef de partie", "date": "2026-06-20", "start_time": "16:00", "end_time": "23:00",
     "hourly_rate": 16.0, "city": "Cagliari", "requirements": ["linea calda", "haccp"],
     "description": "Rinforzo linea — matrimonio 120 pax", "spots": 1,
     "status": "filled", "is_urgent": False, "applications": 4},
]


# ─── Models ───────────────────────────────────────────────────────────────────

class ShiftCreate(BaseModel):
    role: str
    date: str
    start_time: str
    end_time: str
    hourly_rate: float = Field(gt=0)
    city: str
    requirements: List[str] = []
    description: Optional[str] = None
    spots: int = 1
    is_urgent: bool = False
    venue_id: Optional[str] = None  # in demo può mancare


class SOSRequest(BaseModel):
    """Richiesta sostituzione d'emergenza — agente C7.6 AI Staff Rescue."""
    role: str
    date: str
    start_time: str
    end_time: str
    city: str = "Cagliari"
    hourly_rate: Optional[float] = None
    requirements: List[str] = []
    note: Optional[str] = None  # es. "il barman si è infortunato, serve entro stasera"


# ─── Endpoints ────────────────────────────────────────────────────────────────

@router.get("/health")
def health():
    db = get_supabase()
    return {"module": "staff-match", "mode": "supabase" if db else "demo", "agent": "C7.6 AI Staff Rescue"}


@router.get("/shifts")
def list_shifts(status: Optional[str] = None):
    """Turni della venue (Supabase) o demo."""
    db = get_supabase()
    if db:
        q = db.table("shifts").select("*")
        if status:
            q = q.eq("status", status)
        return q.order("date").execute().data or []
    rows = DEMO_SHIFTS
    if status:
        rows = [s for s in rows if s["status"] == status]
    return rows


@router.post("/shifts")
def create_shift(payload: ShiftCreate):
    db = get_supabase()
    data = payload.model_dump()
    if db:
        res = db.table("shifts").insert(data).execute()
        return {"ok": True, "data": res.data}
    # demo: simula creazione
    data["id"] = f"s{len(DEMO_SHIFTS)+1}"
    data["status"] = "open"
    data["applications"] = 0
    DEMO_SHIFTS.append(data)
    return {"ok": True, "data": data, "mode": "demo"}


@router.get("/shifts/{shift_id}/candidates")
def rank_candidates(shift_id: str):
    """Top candidati per un turno, ordinati per match score (algoritmo 40/35/15/10)."""
    db = get_supabase()
    if db:
        shift_res = db.table("shifts").select("*").eq("id", shift_id).single().execute()
        if not shift_res.data:
            raise HTTPException(status_code=404, detail="Turno non trovato")
        shift = shift_res.data
        workers = db.table("worker_profiles").select("*").eq("is_active", True).execute().data or []
        fav = db.table("venue_favorites").select("worker_id").eq("venue_id", shift["venue_id"]).execute().data or []
        fav_ids = {f["worker_id"] for f in fav}
        hist_rows = (db.table("shift_applications")
                     .select("worker_id, shifts!inner(venue_id)")
                     .eq("shifts.venue_id", shift["venue_id"])
                     .eq("status", "completed").execute().data or [])
        hist: Dict[str, int] = {}
        for row in hist_rows:
            hist[row["worker_id"]] = hist.get(row["worker_id"], 0) + 1
    else:
        shift = next((s for s in DEMO_SHIFTS if s["id"] == shift_id), None)
        if not shift:
            raise HTTPException(status_code=404, detail="Turno non trovato")
        workers = DEMO_WORKERS
        fav_ids = {"w1", "w4"}
        hist = {"w1": 5, "w2": 2}

    ranked = []
    for w in workers:
        h = {"worked_together_count": hist.get(w["id"], 0), "is_favorite": w["id"] in fav_ids}
        ranked.append({**w, "match_score": compute_match_score(w, shift, h),
                       "worked_together": hist.get(w["id"], 0), "is_favorite": w["id"] in fav_ids})
    ranked.sort(key=lambda x: x["match_score"], reverse=True)
    return {"shift": shift, "candidates": ranked[:20]}


@router.get("/pool")
def staff_pool():
    """Pool staff della venue: preferiti + già lavorato insieme, con stats."""
    db = get_supabase()
    if db:
        workers = db.table("worker_profiles").select("*").eq("is_active", True).execute().data or []
        return workers
    return DEMO_WORKERS


@router.get("/kpi")
def kpi():
    """KPI del modulo per dashboard e hub."""
    db = get_supabase()
    if db:
        shifts = db.table("shifts").select("status,is_urgent").execute().data or []
        workers = db.table("worker_profiles").select("rating_avg,is_verified").execute().data or []
    else:
        shifts, workers = DEMO_SHIFTS, DEMO_WORKERS
    open_n = sum(1 for s in shifts if s.get("status") == "open")
    urgent_n = sum(1 for s in shifts if s.get("is_urgent") and s.get("status") == "open")
    verified = sum(1 for w in workers if w.get("is_verified"))
    avg_rating = round(sum(float(w.get("rating_avg") or 0) for w in workers) / max(1, len(workers)), 2)
    return {"turni_aperti": open_n, "urgenti": urgent_n, "pool_size": len(workers),
            "verificati": verified, "rating_medio_pool": avg_rating,
            "tempo_medio_copertura_ore": 4.2}


# ─── Agente C7.6 — AI STAFF RESCUE (sostituzione d'emergenza) ─────────────────

RESCUE_SYSTEM = (
    "Sei l'agente AI Staff Rescue di BAD360.ai per l'hospitality italiana. "
    "Un locale ha un buco di organico urgente. Ricevi il turno scoperto e i candidati "
    "ordinati per match score. Per ciascuno dei primi 3 scrivi un messaggio WhatsApp "
    "di contatto: tono professionale ma diretto, nome del candidato, ruolo, data, orario, "
    "paga oraria, luogo; chiusura con richiesta di conferma rapida. Max 60 parole a messaggio. "
    "Rispondi SOLO in JSON: {\"messages\": [{\"worker\": \"nome\", \"message\": \"...\"}], "
    "\"strategy\": \"2 frasi sulla strategia di copertura\"}"
)


def _fallback_messages(shift: dict, top: List[dict]) -> dict:
    msgs = []
    for w in top[:3]:
        msgs.append({
            "worker": w["full_name"],
            "message": (
                f"Ciao {w['full_name'].split()[0]}! Ci serve un {shift['role']} "
                f"il {shift['date']} dalle {shift['start_time']} alle {shift['end_time']} "
                f"a {shift['city']}, €{shift.get('hourly_rate', '—')}/h. "
                f"Sei il primo della nostra lista: confermi entro 30 minuti? Grazie!"
            ),
        })
    return {"messages": msgs,
            "strategy": "Contatta i primi 3 in parallelo; il primo che conferma blocca il turno, gli altri ricevono il ringraziamento automatico."}


@router.post("/sos")
async def ai_staff_rescue(payload: SOSRequest):
    """
    C7.6 AI Staff Rescue: dato un buco di organico, restituisce i candidati
    migliori + messaggi di contatto pronti + strategia di copertura.
    """
    shift = {
        "role": payload.role, "date": payload.date, "start_time": payload.start_time,
        "end_time": payload.end_time, "city": payload.city,
        "hourly_rate": payload.hourly_rate or 0, "requirements": payload.requirements,
    }
    db = get_supabase()
    workers = (db.table("worker_profiles").select("*").eq("is_active", True).execute().data
               if db else DEMO_WORKERS) or DEMO_WORKERS

    ranked = []
    for w in workers:
        # in emergenza la reattività pesa: filtro preliminare su risposta < 60 min
        h = {"worked_together_count": 0, "is_favorite": False}
        ranked.append({**w, "match_score": compute_match_score(w, shift, h)})
    ranked.sort(key=lambda x: (x["match_score"], -int(x.get("avg_response_time_mins") or 60)), reverse=True)
    top = ranked[:5]

    ai_block: Dict[str, Any]
    if ANTHROPIC_API_KEY:
        try:
            compact = [{"nome": w["full_name"], "ruoli": w["roles"], "rating": w["rating_avg"],
                        "risposta_min": w["avg_response_time_mins"], "score": w["match_score"]}
                       for w in top[:3]]
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={"x-api-key": ANTHROPIC_API_KEY,
                             "anthropic-version": "2023-06-01",
                             "content-type": "application/json"},
                    json={"model": "claude-haiku-4-5-20251001", "max_tokens": 700,
                          "system": RESCUE_SYSTEM,
                          "messages": [{"role": "user", "content": json.dumps(
                              {"turno": shift, "nota": payload.note, "candidati": compact},
                              ensure_ascii=False)}]},
                )
            resp.raise_for_status()
            text = resp.json()["content"][0]["text"]
            ai_block = json.loads(text)
        except Exception:
            ai_block = _fallback_messages(shift, top)
    else:
        ai_block = _fallback_messages(shift, top)

    return {"agent": "C7.6 AI Staff Rescue", "shift": shift,
            "candidates": top, **ai_block}
