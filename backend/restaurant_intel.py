"""
BAD360.ai — Restaurant Intelligence (niche E)

Per i clienti ristorazione: log coperti (previsti vs effettivi + no-show) e log sprechi
(food waste). Dashboard con no-show rate e spreco €. AI: forecast domanda + insight
riduzione sprechi (-30/40% in letteratura). Distinto da menu_engineering/food cost.

Sicurezza: hotel_id dal token. Tabelle: rest_coperti + rest_sprechi.
"""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from backend.database import get_supabase
from backend.auth import require_user, UserProfile

router = APIRouter(prefix="/api/restaurant", tags=["Restaurant Intelligence"])
DISCLAIMER = "⚠️ Stima AI — usala come supporto decisionale, non come dato certo."


def _sb():
    sb = get_supabase()
    if not sb:
        raise HTTPException(503, "Database non configurato")
    return sb


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Coperti(BaseModel):
    id:                Optional[str] = None
    data:              str
    coperti_previsti:  int = 0
    coperti_effettivi: int = 0
    no_show:           int = 0
    incasso:           float = 0.0
    note:              Optional[str] = None


class Spreco(BaseModel):
    id:          Optional[str] = None
    data:        Optional[str] = None
    categoria:   Optional[str] = "cucina"     # cucina | bar | sala | magazzino
    quantita_kg: float = 0.0
    valore:      float = 0.0
    causa:       Optional[str] = None
    note:        Optional[str] = None


# ── COPERTI ────────────────────────────────────────────────────────────
@router.get("/coperti", summary="Storico coperti (admin)")
async def list_coperti(user: UserProfile = Depends(require_user)):
    sb = _sb()
    rows = (sb.table("rest_coperti").select("*").eq("hotel_id", user.hotel_id).order("data", desc=True).execute().data) or []
    return {"ok": True, "coperti": rows, "totale": len(rows)}


@router.post("/coperti", summary="Registra coperti del giorno")
async def upsert_coperti(payload: Coperti, user: UserProfile = Depends(require_user)):
    sb = _sb()
    data = {"hotel_id": user.hotel_id, "data": payload.data,
            "coperti_previsti": int(payload.coperti_previsti or 0), "coperti_effettivi": int(payload.coperti_effettivi or 0),
            "no_show": int(payload.no_show or 0), "incasso": float(payload.incasso or 0),
            "note": (payload.note or "").strip(), "updated_at": _now()}
    if payload.id:
        res = sb.table("rest_coperti").update(data).eq("id", payload.id).eq("hotel_id", user.hotel_id).execute()
        if not res.data:
            raise HTTPException(404, "Record non trovato")
        return {"ok": True, "record": res.data[0]}
    res = sb.table("rest_coperti").insert(data).execute()
    return {"ok": True, "record": res.data[0] if res.data else data}


@router.delete("/coperti/{cid}", summary="Elimina record coperti")
async def delete_coperti(cid: str, user: UserProfile = Depends(require_user)):
    sb = _sb()
    sb.table("rest_coperti").delete().eq("id", cid).eq("hotel_id", user.hotel_id).execute()
    return {"ok": True}


# ── SPRECHI ────────────────────────────────────────────────────────────
@router.get("/sprechi", summary="Log sprechi (admin)")
async def list_sprechi(user: UserProfile = Depends(require_user)):
    sb = _sb()
    rows = (sb.table("rest_sprechi").select("*").eq("hotel_id", user.hotel_id).order("data", desc=True).execute().data) or []
    return {"ok": True, "sprechi": rows, "totale": len(rows)}


@router.post("/sprechi", summary="Registra spreco")
async def upsert_spreco(payload: Spreco, user: UserProfile = Depends(require_user)):
    sb = _sb()
    data = {"hotel_id": user.hotel_id, "data": payload.data, "categoria": payload.categoria,
            "quantita_kg": float(payload.quantita_kg or 0), "valore": float(payload.valore or 0),
            "causa": (payload.causa or "").strip(), "note": (payload.note or "").strip()}
    if payload.id:
        res = sb.table("rest_sprechi").update(data).eq("id", payload.id).eq("hotel_id", user.hotel_id).execute()
        if not res.data:
            raise HTTPException(404, "Record non trovato")
        return {"ok": True, "record": res.data[0]}
    data["created_at"] = _now()
    res = sb.table("rest_sprechi").insert(data).execute()
    return {"ok": True, "record": res.data[0] if res.data else data}


@router.delete("/sprechi/{sid}", summary="Elimina spreco")
async def delete_spreco(sid: str, user: UserProfile = Depends(require_user)):
    sb = _sb()
    sb.table("rest_sprechi").delete().eq("id", sid).eq("hotel_id", user.hotel_id).execute()
    return {"ok": True}


@router.get("/dashboard", summary="KPI restaurant intelligence")
async def dashboard(user: UserProfile = Depends(require_user)):
    sb = _sb()
    cop = (sb.table("rest_coperti").select("coperti_previsti,coperti_effettivi,no_show,incasso").eq("hotel_id", user.hotel_id).execute().data) or []
    spr = (sb.table("rest_sprechi").select("valore,quantita_kg").eq("hotel_id", user.hotel_id).execute().data) or []
    tot_eff = sum(int(c.get("coperti_effettivi") or 0) for c in cop)
    tot_ns = sum(int(c.get("no_show") or 0) for c in cop)
    base = tot_eff + tot_ns
    waste_eur = round(sum(float(s.get("valore") or 0) for s in spr), 2)
    return {"ok": True, "kpi": {
        "giorni_registrati": len(cop),
        "coperti_medi": round(tot_eff / len(cop), 1) if cop else 0,
        "no_show_rate_pct": round(tot_ns / base * 100, 1) if base else 0,
        "incasso_totale": round(sum(float(c.get("incasso") or 0) for c in cop), 2),
        "spreco_euro": waste_eur, "spreco_kg": round(sum(float(s.get("quantita_kg") or 0) for s in spr), 1),
    }}


# ── AI: forecast + insight sprechi ─────────────────────────────────────
@router.post("/ai/forecast", summary="Previsione coperti/domanda (AI)")
async def ai_forecast(user: UserProfile = Depends(require_user)):
    sb = _sb()
    cop = (sb.table("rest_coperti").select("data,coperti_effettivi,no_show").eq("hotel_id", user.hotel_id).order("data", desc=True).execute().data) or []
    if len(cop) < 3:
        return {"ok": True, "stato": "pochi_dati", "previsione": "Registra almeno 3-4 giorni di coperti per una previsione utile."}
    serie = "; ".join(f"{c.get('data')}: {c.get('coperti_effettivi')} coperti ({c.get('no_show')} no-show)" for c in cop[:30])
    prompt = (
        "Sei un analista di sala. Dato lo storico coperti, stima i COPERTI ATTESI per i prossimi giorni "
        "(indica un range), evidenzia il pattern (giorni forti/deboli, weekend) e dai 2-3 azioni operative "
        "su staffing e prep per ridurre sprechi e no-show. Conciso. Sono stime, non certezze.\n\n"
        f"STORICO (più recente prima): {serie}"
    )
    from backend.ai_agents import _ask_claude
    try:
        out = await _ask_claude(prompt, max_tokens=600)
    except Exception as ex:
        raise HTTPException(502, f"AI non raggiungibile: {ex}")
    return {"ok": True, "previsione": (out or "").strip(), "disclaimer": DISCLAIMER}


@router.post("/ai/sprechi-insight", summary="Suggerimenti riduzione sprechi (AI)")
async def ai_sprechi(user: UserProfile = Depends(require_user)):
    sb = _sb()
    spr = (sb.table("rest_sprechi").select("data,categoria,quantita_kg,valore,causa").eq("hotel_id", user.hotel_id).order("data", desc=True).execute().data) or []
    if not spr:
        return {"ok": True, "stato": "nessun_dato", "insight": "Registra qualche spreco per ricevere suggerimenti mirati."}
    righe = "; ".join(f"{s.get('categoria')} {s.get('quantita_kg')}kg/{s.get('valore')}€ ({s.get('causa','')})" for s in spr[:30])
    prompt = (
        "Sei un consulente F&B esperto di food cost e riduzione sprechi. Dai 3-5 azioni concrete per ridurre "
        "gli sprechi alla luce di questi dati (porzionatura, FEFO, forecast, menu, fornitori). Conciso.\n\n"
        f"SPRECHI RECENTI: {righe}"
    )
    from backend.ai_agents import _ask_claude
    try:
        out = await _ask_claude(prompt, max_tokens=500)
    except Exception as ex:
        raise HTTPException(502, f"AI non raggiungibile: {ex}")
    return {"ok": True, "insight": (out or "").strip(), "disclaimer": DISCLAIMER}
