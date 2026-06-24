"""
BAD360.ai — HACCP (persistenza reale, multi-tenant)
Registro temperature HACCP salvato su Supabase, scoped per hotel_id dal JWT.

È il PRIMO modulo "fondamenta dati": trasforma haccp.html da demo a gestionale
vero. Il frontend (haccp.html) chiama già POST /api/haccp/temperature-log e si
aspetta {alert, severity, message}; qui lo persistiamo davvero.

Tabella: haccp_letture (vedi supabase/haccp_schema.sql).
Sicurezza: hotel_id viene SEMPRE dal token (require_user), mai dal client.
"""

from __future__ import annotations
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel

from backend.database import get_supabase
from backend.auth import require_user, UserProfile

router = APIRouter(prefix="/api/haccp", tags=["HACCP"])

# ── Norme di conformità per zona (°C) ─────────────────────────────────
# Fonte: Reg. CE 852/2004 + prassi HoReCa. min/max ammessi per zona.
NORME = {
    "cella_frigo":     {"min": 0,   "max": 4,   "label": "Cella frigo (0–4°C)"},
    "cella_surgelati": {"min": -25,  "max": -18, "label": "Surgelati (≤ -18°C)"},
    "frigo_bar":       {"min": 2,   "max": 6,   "label": "Frigo bar (2–6°C)"},
    "zona_calda":      {"min": 63,  "max": 90,  "label": "Mantenimento caldo (≥ 63°C)"},
    "cantina":         {"min": 10,  "max": 16,  "label": "Cantina vini (10–16°C)"},
    "abbattitore":     {"min": -25,  "max": 3,   "label": "Abbattitore"},
}
DEFAULT_NORMA = {"min": 0, "max": 6, "label": "Generico (0–6°C)"}


def _eval(zona: str, temp: float) -> dict:
    """Valuta la temperatura vs norma → alert/severity/conformità/messaggio."""
    n = NORME.get(zona, DEFAULT_NORMA)
    mn, mx = n["min"], n["max"]
    if mn <= temp <= mx:
        return {"alert": False, "severity": "ok", "conforme_reg": True,
                "message": f"✅ {temp}°C nella norma ({n['label']})"}
    # fuori range: critico se deviazione > 5°C, altrimenti warning
    dev = (temp - mx) if temp > mx else (mn - temp)
    severity = "critical" if dev > 5 else "warning"
    return {"alert": True, "severity": severity, "conforme_reg": False,
            "message": f"⚠️ {temp}°C FUORI norma ({n['label']}) — deviazione {dev:.1f}°C"}


# ── Modelli ───────────────────────────────────────────────────────────
class TempLog(BaseModel):
    zona: str
    temperatura: float
    sensor_id: str = "b360-ui"
    rilevato_da: str = "manuale"
    timestamp: Optional[str] = None
    note: Optional[str] = None


# ── Helpers ───────────────────────────────────────────────────────────
def _sb_or_503():
    sb = get_supabase()
    if not sb:
        raise HTTPException(503, "Database non configurato")
    return sb


def _today_start_iso() -> str:
    now = datetime.now(timezone.utc)
    return now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()


# ── ENDPOINT: registra lettura temperatura ────────────────────────────
@router.post("/temperature-log", summary="Registra una lettura di temperatura HACCP")
async def temperature_log(payload: TempLog, user: UserProfile = Depends(require_user)):
    sb = _sb_or_503()
    ev = _eval(payload.zona, payload.temperatura)
    n = NORME.get(payload.zona, DEFAULT_NORMA)
    record = {
        "hotel_id":     user.hotel_id,          # SEMPRE dal token (blindato)
        "sensor_id":    payload.sensor_id,
        "zona":         payload.zona,
        "temperatura":  payload.temperatura,
        "temp_min_norm": n["min"],
        "temp_max_norm": n["max"],
        "alert":        ev["alert"],
        "severity":     ev["severity"],
        "messaggio":    payload.note or ev["message"],
        "conforme_reg": ev["conforme_reg"],
        "rilevato_da":  payload.rilevato_da,
        "timestamp":    payload.timestamp or datetime.now(timezone.utc).isoformat(),
    }
    try:
        res = sb.table("haccp_letture").insert(record).execute()
    except Exception as e:
        raise HTTPException(500, f"Errore salvataggio: {e}")
    saved = (res.data or [{}])[0]
    return {"ok": True, "id": saved.get("id"),
            "alert": ev["alert"], "severity": ev["severity"], "message": ev["message"]}


# ── ENDPOINT: storico letture ─────────────────────────────────────────
@router.get("/temperature-history", summary="Storico letture temperatura")
async def temperature_history(user: UserProfile = Depends(require_user),
                              zona: Optional[str] = Query(None),
                              limit: int = Query(100, ge=1, le=500)):
    sb = _sb_or_503()
    q = sb.table("haccp_letture").select("*").eq("hotel_id", user.hotel_id)
    if zona:
        q = q.eq("zona", zona)
    try:
        res = q.order("timestamp", desc=True).limit(limit).execute()
    except Exception as e:
        raise HTTPException(500, f"Errore lettura: {e}")
    return {"ok": True, "count": len(res.data or []), "items": res.data or []}


# ── ENDPOINT: alert attivi oggi ───────────────────────────────────────
@router.get("/alerts", summary="Alert temperatura attivi (oggi)")
async def alerts(user: UserProfile = Depends(require_user)):
    sb = _sb_or_503()
    try:
        res = (sb.table("haccp_letture").select("*")
               .eq("hotel_id", user.hotel_id).eq("alert", True)
               .gte("timestamp", _today_start_iso())
               .order("timestamp", desc=True).execute())
    except Exception as e:
        raise HTTPException(500, f"Errore lettura: {e}")
    return {"ok": True, "count": len(res.data or []), "alerts": res.data or []}


# ── ENDPOINT: dashboard sintetica ─────────────────────────────────────
@router.get("/dashboard", summary="KPI HACCP del giorno")
async def dashboard(user: UserProfile = Depends(require_user)):
    sb = _sb_or_503()
    try:
        res = (sb.table("haccp_letture").select("*")
               .eq("hotel_id", user.hotel_id)
               .gte("timestamp", _today_start_iso())
               .order("timestamp", desc=True).execute())
    except Exception as e:
        raise HTTPException(500, f"Errore lettura: {e}")
    rows = res.data or []
    letture = len(rows)
    alert_n = sum(1 for r in rows if r.get("alert"))
    conformi = sum(1 for r in rows if r.get("conforme_reg"))
    # ultima lettura per zona
    per_zona = {}
    for r in rows:  # rows già desc per timestamp → la prima per zona è la più recente
        z = r.get("zona")
        if z and z not in per_zona:
            per_zona[z] = {"temperatura": r.get("temperatura"), "severity": r.get("severity"),
                           "timestamp": r.get("timestamp"), "label": NORME.get(z, DEFAULT_NORMA)["label"]}
    return {"ok": True, "letture_oggi": letture, "alert_oggi": alert_n,
            "conformita_pct": round(100 * conformi / letture) if letture else 100,
            "ultime_per_zona": per_zona}
