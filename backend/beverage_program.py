"""
BAD360.ai — AI Beverage Program (niche B, la nicchia personale di Simone)

Il "beverage director" in versione AI: carta bevande unica (cocktail+vini+birre+spiriti)
con MENU ENGINEERING (popolarità × margine → star/plowhorse/puzzle/dog) e beverage cost %,
+ AI per generare una carta cocktail stagionale e suggerire abbinamenti.
Distinto da drinks.py (costo singola ricetta) e hotellerie.py (carta vini): qui è la
vista di PROGRAMMA + ottimizzazione AI.

Sicurezza: hotel_id dal token. Tabella: beverage_items.
"""
from __future__ import annotations
from datetime import datetime, timezone
from statistics import median
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from backend.database import get_supabase
from backend.auth import require_user, UserProfile

router = APIRouter(prefix="/api/beverage", tags=["AI Beverage Program"])
DISCLAIMER = "⚠️ Bozza AI — verifica dosi, costi, disponibilità e prezzi prima di metterla in carta."


def _sb():
    sb = get_supabase()
    if not sb:
        raise HTTPException(503, "Database non configurato")
    return sb


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Item(BaseModel):
    id:        Optional[str] = None
    nome:      str
    tipo:      Optional[str] = "cocktail"   # cocktail | vino | birra | spirito | analcolico
    categoria: Optional[str] = None
    prezzo:    float = 0.0
    costo:     float = 0.0
    venduti:   int = 0
    attivo:    bool = True


def _classify(items: list) -> list:
    act = [i for i in items if i.get("attivo", True)]
    vend = [int(i.get("venduti") or 0) for i in act] or [0]
    marg = []
    for i in act:
        p, c = float(i.get("prezzo") or 0), float(i.get("costo") or 0)
        marg.append(p - c)
    med_v = median(vend) if vend else 0
    med_m = median(marg) if marg else 0
    out = []
    for i in items:
        p, c = float(i.get("prezzo") or 0), float(i.get("costo") or 0)
        m = round(p - c, 2)
        i = dict(i)
        i["margine"] = m
        i["margine_pct"] = round(m / p * 100, 1) if p else 0
        i["cost_pct"] = round(c / p * 100, 1) if p else 0
        hi_pop = int(i.get("venduti") or 0) >= med_v
        hi_mar = m >= med_m
        i["classe"] = ("star" if hi_pop and hi_mar else "plowhorse" if hi_pop else
                       "puzzle" if hi_mar else "dog")
        out.append(i)
    return out


@router.get("/items", summary="Carta bevande con menu engineering")
async def list_items(user: UserProfile = Depends(require_user)):
    sb = _sb()
    rows = (sb.table("beverage_items").select("*").eq("hotel_id", user.hotel_id).order("tipo").execute().data) or []
    enriched = _classify(rows)
    pcts = [i["cost_pct"] for i in enriched if i.get("attivo", True) and i["cost_pct"]]
    return {"ok": True, "items": enriched, "totale": len(rows),
            "beverage_cost_pct_medio": round(sum(pcts) / len(pcts), 1) if pcts else 0}


@router.post("/items", summary="Aggiungi/aggiorna voce carta")
async def upsert_item(payload: Item, user: UserProfile = Depends(require_user)):
    sb = _sb()
    data = {
        "hotel_id": user.hotel_id, "nome": payload.nome.strip(), "tipo": payload.tipo,
        "categoria": (payload.categoria or "").strip(), "prezzo": float(payload.prezzo or 0),
        "costo": float(payload.costo or 0), "venduti": int(payload.venduti or 0),
        "attivo": bool(payload.attivo), "updated_at": _now(),
    }
    if payload.id:
        res = sb.table("beverage_items").update(data).eq("id", payload.id).eq("hotel_id", user.hotel_id).execute()
        if not res.data:
            raise HTTPException(404, "Voce non trovata")
        return {"ok": True, "item": res.data[0]}
    res = sb.table("beverage_items").insert(data).execute()
    return {"ok": True, "item": res.data[0] if res.data else data}


@router.delete("/items/{iid}", summary="Elimina voce")
async def delete_item(iid: str, user: UserProfile = Depends(require_user)):
    sb = _sb()
    sb.table("beverage_items").delete().eq("id", iid).eq("hotel_id", user.hotel_id).execute()
    return {"ok": True}


@router.get("/dashboard", summary="KPI beverage program")
async def dashboard(user: UserProfile = Depends(require_user)):
    sb = _sb()
    rows = _classify((sb.table("beverage_items").select("*").eq("hotel_id", user.hotel_id).execute().data) or [])
    act = [i for i in rows if i.get("attivo", True)]
    def cl(k): return sum(1 for i in act if i.get("classe") == k)
    pcts = [i["cost_pct"] for i in act if i["cost_pct"]]
    return {"ok": True, "kpi": {
        "voci": len(act), "star": cl("star"), "plowhorse": cl("plowhorse"),
        "puzzle": cl("puzzle"), "dog": cl("dog"),
        "beverage_cost_pct_medio": round(sum(pcts) / len(pcts), 1) if pcts else 0,
    }}


# ── AI: carta stagionale + abbinamento ─────────────────────────────────
class MenuReq(BaseModel):
    tema: Optional[str] = None        # es. "estate sarda", "mirto e agrumi", "analcolici"
    n: int = 5

class PairingReq(BaseModel):
    piatto_o_occasione: str


@router.post("/ai/menu", summary="Genera proposta carta cocktail (AI)")
async def ai_menu(body: MenuReq, user: UserProfile = Depends(require_user)):
    prompt = (
        "Sei un bar manager/mixologist esperto. Proponi una BOZZA di carta cocktail "
        f"({max(3, min(body.n, 10))} drink) sul tema: '{body.tema or 'signature di stagione'}'. "
        "Per ogni cocktail: nome accattivante, ingredienti principali, breve descrizione e una "
        "FASCIA di prezzo indicativa. Valorizza prodotti del territorio se coerenti. "
        "Non inventare costi precisi: prezzi come fascia indicativa '[da validare]'. Markdown conciso."
    )
    from backend.ai_agents import _ask_claude
    try:
        out = await _ask_claude(prompt, max_tokens=800)
    except Exception as ex:
        raise HTTPException(502, f"AI non raggiungibile: {ex}")
    return {"ok": True, "menu_markdown": (out or "").strip(), "disclaimer": DISCLAIMER}


@router.post("/ai/pairing", summary="Suggerisci abbinamento bevanda (AI, usa la carta)")
async def ai_pairing(body: PairingReq, user: UserProfile = Depends(require_user)):
    sb = get_supabase()
    carta = ""
    if sb:
        rows = (sb.table("beverage_items").select("nome,tipo,categoria").eq("hotel_id", user.hotel_id).eq("attivo", True).execute().data) or []
        carta = "\n".join(f"- {r.get('nome')} ({r.get('tipo')})" for r in rows[:40])
    prompt = (
        "Sei un sommelier/beverage director. Suggerisci l'abbinamento bevanda migliore per: "
        f"'{body.piatto_o_occasione}'. Se possibile scegli DALLA CARTA della struttura qui sotto "
        "(cita il nome); altrimenti proponi una tipologia generica e spiega il perché in 2 righe.\n\n"
        f"CARTA DISPONIBILE:\n{carta or '(carta non disponibile)'}"
    )
    from backend.ai_agents import _ask_claude
    try:
        out = await _ask_claude(prompt, max_tokens=400)
    except Exception as ex:
        raise HTTPException(502, f"AI non raggiungibile: {ex}")
    return {"ok": True, "abbinamento": (out or "").strip(), "disclaimer": DISCLAIMER}
