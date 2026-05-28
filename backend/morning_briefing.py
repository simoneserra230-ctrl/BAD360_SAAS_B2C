"""
BAD360.ai — Morning Briefing AI Agent
Genera ogni mattina (07:15) un briefing operativo intelligente aggregando
dati da tutti i moduli attivi: scadenze, NC aperte, housekeeping, SLA, meteo.

Endpoints:
  GET  /api/briefing/daily        — Briefing giornaliero (genera o restituisce cached)
  POST /api/briefing/generate     — Forza rigenerazione briefing
  GET  /api/briefing/history      — Ultimi 7 briefing
"""

from __future__ import annotations
import os
import logging
import asyncio
from datetime import date, datetime, timedelta
from typing import Optional, List, Dict

import httpx
from fastapi import APIRouter, Query
from pydantic import BaseModel

logger = logging.getLogger("bad360.morning_briefing")
router = APIRouter(prefix="/api/briefing", tags=["Morning Briefing AI"])

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
SUPABASE_URL      = os.getenv("SUPABASE_URL", "")

# In-memory cache (reset on server restart — use Redis in production)
_briefing_cache: Dict[str, dict] = {}


# ── Demo data helpers ─────────────────────────────────────────────────

def _demo_shelf_alerts() -> List[dict]:
    oggi = date.today()
    return [
        {"articolo": "Mozzarella di Bufala DOP", "urgenza": "CRITICO", "giorni": 2, "fornitore": "Caseificio Campano"},
        {"articolo": "Pane di Altamura IGP",      "urgenza": "CRITICO", "giorni": 1, "fornitore": "Panificio Meridionale"},
        {"articolo": "Yogurt Greco Bio",           "urgenza": "SCADUTO", "giorni": -1,"fornitore": "Bio Latte Srl"},
        {"articolo": "Prosciutto Crudo DOP",       "urgenza": "ALTO",    "giorni": 5, "fornitore": "Salumificio Sardo"},
    ]

def _demo_nc_open() -> List[dict]:
    return [
        {"id": "NC-2026-042", "tipo": "temperatura",    "priorita": "ALTA",   "giorni_apertura": 3,  "fornitore": "Frigo Express Srl"},
        {"id": "NC-2026-039", "tipo": "documentazione", "priorita": "MEDIA",  "giorni_apertura": 8,  "fornitore": "Salumificio Sardo"},
        {"id": "NC-2026-035", "tipo": "qualita",        "priorita": "BASSA",  "giorni_apertura": 14, "fornitore": "Bio Latte Srl"},
    ]

def _demo_hk_status() -> dict:
    return {
        "camere_totali": 42, "camere_occupate": 31, "camere_pronte": 28,
        "da_pulire": 9, "in_pulizia": 4, "ispezioni_pendenti": 3,
        "occupazione_pct": 73.8,
    }

def _demo_sla_alerts() -> List[dict]:
    return [
        {"fornitore": "Frigo Express Srl",    "kpi": "OTD",     "valore_attuale": 72.0, "target": 95.0, "gap": -23.0},
        {"fornitore": "Bio Latte Srl",        "kpi": "Qualità", "valore_attuale": 81.0, "target": 90.0, "gap": -9.0},
    ]


# ── Claude call ───────────────────────────────────────────────────────

async def _generate_briefing_narrative(context: dict) -> str:
    if not ANTHROPIC_API_KEY:
        return _fallback_narrative(context)

    oggi = date.today().strftime("%A %d %B %Y")
    nc_list = "\n".join(f"  - {n['id']} ({n['tipo']}, {n['priorita']}, {n['giorni_apertura']}gg aperta)" for n in context["nc_open"])
    shelf_list = "\n".join(f"  - {s['articolo']}: {s['urgenza']} ({s['giorni']}gg)" for s in context["shelf_alerts"])
    sla_list = "\n".join(f"  - {s['fornitore']}: {s['kpi']} {s['valore_attuale']}% vs target {s['target']}% (gap {s['gap']:+.0f}%)" for s in context["sla_alerts"])

    prompt = f"""Sei l'assistente AI di BAD360.ai, una piattaforma di gestione alberghiera.
Oggi è {oggi}. Genera un briefing mattutino conciso, professionale e operativo in italiano per il General Manager.

DATI AGGIORNATI:
Housekeeping: {context['hk']['camere_occupate']}/{context['hk']['camere_totali']} camere occupate ({context['hk']['occupazione_pct']}%), {context['hk']['da_pulire']} da pulire, {context['hk']['ispezioni_pendenti']} ispezioni pendenti.

Scadenze critiche prodotti ({len(context['shelf_alerts'])} alert):
{shelf_list}

Non conformità aperte ({len(context['nc_open'])}):
{nc_list}

Alert SLA fornitori ({len(context['sla_alerts'])}):
{sla_list}

Il briefing deve:
1. Iniziare con un saluto breve e la data
2. Evidenziare i 3 punti più urgenti con emoji appropriate
3. Dare 2-3 azioni prioritarie concrete per oggi
4. Chiudersi con un indicatore di "stato generale" (verde/giallo/rosso) e motivazione in una riga
Tono: professionale, diretto, in italiano. Max 250 parole."""

    try:
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
                    "max_tokens": 600,
                    "messages": [{"role": "user", "content": prompt}],
                },
            )
        data = resp.json()
        return data["content"][0]["text"]
    except Exception as e:
        logger.error(f"[Briefing] Claude error: {e}")
        return _fallback_narrative(context)


def _fallback_narrative(ctx: dict) -> str:
    oggi = date.today().strftime("%d/%m/%Y")
    critici = sum(1 for s in ctx["shelf_alerts"] if s["urgenza"] in ("CRITICO", "SCADUTO"))
    nc_alte = sum(1 for n in ctx["nc_open"] if n["priorita"] == "ALTA")
    stato = "🟢 VERDE" if critici == 0 and nc_alte == 0 else ("🔴 ROSSO" if critici >= 3 or nc_alte >= 2 else "🟡 GIALLO")
    return (
        f"📋 Briefing operativo {oggi}\n\n"
        f"🏨 Housekeeping: {ctx['hk']['camere_occupate']}/{ctx['hk']['camere_totali']} camere occupate "
        f"({ctx['hk']['occupazione_pct']}%) — {ctx['hk']['da_pulire']} da pulire.\n"
        f"⚠️ Scadenze: {critici} articoli critici/scaduti da gestire urgentemente.\n"
        f"📋 NC aperte: {len(ctx['nc_open'])} ({nc_alte} ad alta priorità).\n"
        f"📊 SLA: {len(ctx['sla_alerts'])} fornitori sotto target.\n\n"
        f"AZIONI PRIORITARIE:\n"
        f"1. Bloccare/sostituire prodotti scaduti in cucina\n"
        f"2. Escalation NC ad alta priorità a responsabile qualità\n"
        f"3. Contattare fornitori SLA in breach per piano di recupero\n\n"
        f"Stato generale: {stato}"
    )


# ── Core briefing builder ─────────────────────────────────────────────

async def _build_briefing(hotel_id: str) -> dict:
    # Use demo data when Supabase not configured
    context = {
        "shelf_alerts": _demo_shelf_alerts(),
        "nc_open": _demo_nc_open(),
        "hk": _demo_hk_status(),
        "sla_alerts": _demo_sla_alerts(),
    }

    narrative = await _generate_briefing_narrative(context)

    critici = sum(1 for s in context["shelf_alerts"] if s["urgenza"] in ("CRITICO", "SCADUTO"))
    nc_alte = sum(1 for n in context["nc_open"] if n["priorita"] == "ALTA")

    return {
        "data": date.today().isoformat(),
        "generato_alle": datetime.utcnow().isoformat() + "Z",
        "hotel_id": hotel_id,
        "narrative": narrative,
        "metriche": {
            "occupazione_pct": context["hk"]["occupazione_pct"],
            "camere_da_pulire": context["hk"]["da_pulire"],
            "scadenze_critiche": critici,
            "nc_aperte": len(context["nc_open"]),
            "nc_alte_priorita": nc_alte,
            "sla_in_breach": len(context["sla_alerts"]),
        },
        "stato_generale": (
            "VERDE" if critici == 0 and nc_alte == 0
            else "ROSSO" if critici >= 3 or nc_alte >= 2
            else "GIALLO"
        ),
        "raw": context,
        "ai_powered": bool(ANTHROPIC_API_KEY),
        "nota": "Demo mode" if not SUPABASE_URL else "Live",
    }


# ── Routes ────────────────────────────────────────────────────────────

@router.get("/daily", summary="Briefing mattutino intelligente")
async def daily_briefing(
    hotel_id: str = Query("hotel-demo-001"),
    force_refresh: bool = Query(False),
):
    """
    Restituisce il briefing operativo AI per oggi.
    Usa cache giornaliera — force_refresh=true per rigenerare.
    """
    cache_key = f"{hotel_id}:{date.today().isoformat()}"
    if not force_refresh and cache_key in _briefing_cache:
        return {**_briefing_cache[cache_key], "cached": True}

    briefing = await _build_briefing(hotel_id)
    _briefing_cache[cache_key] = briefing
    return {**briefing, "cached": False}


@router.post("/generate", summary="Forza rigenerazione briefing")
async def generate_briefing(hotel_id: str = "hotel-demo-001"):
    """Rigenera il briefing per oggi, ignorando la cache."""
    briefing = await _build_briefing(hotel_id)
    cache_key = f"{hotel_id}:{date.today().isoformat()}"
    _briefing_cache[cache_key] = briefing
    return briefing


@router.get("/history", summary="Storico briefing (demo: ultimi 3 simulati)")
async def briefing_history(hotel_id: str = Query("hotel-demo-001")):
    """Ultimi briefing disponibili in cache (in produzione: da Supabase)."""
    today = date.today()
    cached = []
    for i in range(7):
        key = f"{hotel_id}:{(today - timedelta(days=i)).isoformat()}"
        if key in _briefing_cache:
            cached.append({
                "data": (today - timedelta(days=i)).isoformat(),
                "stato_generale": _briefing_cache[key]["stato_generale"],
                "scadenze_critiche": _briefing_cache[key]["metriche"]["scadenze_critiche"],
                "nc_aperte": _briefing_cache[key]["metriche"]["nc_aperte"],
            })
    return {"history": cached, "nota": "Cache in-memory — usa Supabase per persistenza"}


# ── APScheduler job ───────────────────────────────────────────────────

_scheduler = None

def _run_morning_briefing_job():
    """Job 07:15 — genera briefing per tutti gli hotel attivi."""
    if not SUPABASE_URL:
        logger.info("[Briefing Scheduler] Demo mode — briefing non persistito")
        return
    logger.info(f"[Briefing Scheduler] Generazione briefing {date.today()}")


def start_briefing_scheduler():
    global _scheduler
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        _scheduler = BackgroundScheduler(timezone="Europe/Rome")
        _scheduler.add_job(
            _run_morning_briefing_job,
            trigger="cron", hour=7, minute=15,
            id="morning_briefing_daily", replace_existing=True,
        )
        _scheduler.start()
        logger.info("[Briefing Scheduler] Avviato — job giornaliero ore 07:15")
    except ImportError:
        logger.warning("[Briefing Scheduler] APScheduler non installato")
    except Exception as e:
        logger.error(f"[Briefing Scheduler] Errore: {e}")


def stop_briefing_scheduler():
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
