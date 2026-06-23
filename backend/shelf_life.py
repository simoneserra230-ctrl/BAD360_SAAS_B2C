"""
BAD.S Platform — Modulo Shelf Life FEFO
Router FastAPI + APScheduler giornaliero per alert scadenze

Endpoints:
  GET  /api/shelf-life              — Lista articoli con scadenze
  GET  /api/shelf-life/alerts       — Alert scadenze critiche
  POST /api/shelf-life/articolo     — Aggiorna scadenza articolo
  GET  /api/shelf-life/fefo-order   — Ordine prelievo FEFO
  GET  /api/shelf-life/summary      — Riepilogo scadenze mensile
  POST /api/shelf-life/blocca-lotto — Blocca lotto scaduto/richiamato
"""

from __future__ import annotations
from datetime import date, datetime, timedelta
from typing import Optional, List, Dict
import os
import logging

import httpx
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

logger = logging.getLogger("bad360.shelf_life")

router = APIRouter(prefix="/api/shelf-life", tags=["Shelf Life FEFO"])

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")

# ── Soglie urgenza ────────────────────────────────────────────────

def _urgenza(giorni: int) -> str:
    if giorni < 0:
        return "SCADUTO"
    if giorni <= 3:
        return "CRITICO"
    if giorni <= 7:
        return "ALTO"
    if giorni <= 14:
        return "ATTENZIONE"
    return "OK"


# ── Demo data ─────────────────────────────────────────────────────

def _demo_inventario() -> List[Dict]:
    oggi = date.today()
    return [
        {
            "id": "sl-001", "articolo": "Prosciutto Crudo DOP",
            "categoria": "Salumi", "lotto": "LOT-2026-05-001",
            "giacenza_attuale": 8.0, "unita_misura": "kg",
            "data_scadenza": (oggi + timedelta(days=5)).isoformat(),
            "giorni_alla_scadenza": 5, "urgenza": "ALTO",
            "lotto_bloccato": False, "fornitore": "Salumificio Sardo Srl",
        },
        {
            "id": "sl-002", "articolo": "Mozzarella di Bufala DOP",
            "categoria": "Latticini", "lotto": "LOT-2026-05-022",
            "giacenza_attuale": 3.2, "unita_misura": "kg",
            "data_scadenza": (oggi + timedelta(days=2)).isoformat(),
            "giorni_alla_scadenza": 2, "urgenza": "CRITICO",
            "lotto_bloccato": False, "fornitore": "Caseificio Campano SpA",
        },
        {
            "id": "sl-003", "articolo": "Yogurt Greco Bio",
            "categoria": "Latticini", "lotto": "LOT-2026-05-031",
            "giacenza_attuale": 6.0, "unita_misura": "kg",
            "data_scadenza": (oggi - timedelta(days=1)).isoformat(),
            "giorni_alla_scadenza": -1, "urgenza": "SCADUTO",
            "lotto_bloccato": True, "fornitore": "Bio Latte Srl",
        },
        {
            "id": "sl-004", "articolo": "Bottarga di Muggine",
            "categoria": "Pesce/Ittico", "lotto": "LOT-2026-04-008",
            "giacenza_attuale": 1.5, "unita_misura": "kg",
            "data_scadenza": (oggi + timedelta(days=45)).isoformat(),
            "giorni_alla_scadenza": 45, "urgenza": "OK",
            "lotto_bloccato": False, "fornitore": "Pescheria Cagliari Srl",
        },
        {
            "id": "sl-005", "articolo": "Frutta fresca mista",
            "categoria": "Ortofrutta", "lotto": "LOT-2026-05-041",
            "giacenza_attuale": 12.0, "unita_misura": "kg",
            "data_scadenza": (oggi + timedelta(days=3)).isoformat(),
            "giorni_alla_scadenza": 3, "urgenza": "CRITICO",
            "lotto_bloccato": False, "fornitore": "Frutta & Co. Srl",
        },
        {
            "id": "sl-006", "articolo": "Olio EVO Sardegna Bio",
            "categoria": "Oli e condimenti", "lotto": "LOT-2026-04-018",
            "giacenza_attuale": 18.0, "unita_misura": "L",
            "data_scadenza": (oggi + timedelta(days=330)).isoformat(),
            "giorni_alla_scadenza": 330, "urgenza": "OK",
            "lotto_bloccato": False, "fornitore": "Frantoi Oristano SpA",
        },
        {
            "id": "sl-007", "articolo": "Pane di Altamura IGP",
            "categoria": "Pane e pasta", "lotto": "LOT-2026-05-055",
            "giacenza_attuale": 4.0, "unita_misura": "kg",
            "data_scadenza": (oggi + timedelta(days=1)).isoformat(),
            "giorni_alla_scadenza": 1, "urgenza": "CRITICO",
            "lotto_bloccato": False, "fornitore": "Panificio Meridionale",
        },
    ]


# ── Modelli ───────────────────────────────────────────────────────

class ArticoloScadenzaUpdate(BaseModel):
    hotel_id: str
    inventario_id: str
    data_scadenza: str
    lotto: Optional[str] = None
    note: Optional[str] = None


class BloccaLottoRequest(BaseModel):
    hotel_id: str
    inventario_id: str
    motivo: str = "scaduto"   # scaduto | richiamo | nc_haccp | qualita
    responsabile: Optional[str] = None
    note: Optional[str] = None


# ── Routes ────────────────────────────────────────────────────────

@router.get("", summary="Lista articoli con scadenze FEFO")
async def lista_scadenze(
    hotel_id: str,
    urgenza: Optional[str] = None,
    categoria: Optional[str] = None,
    solo_alert: bool = False,
    limit: int = Query(100, le=500),
):
    """
    Lista articoli ordinati per scadenza FEFO (First Expired First Out).
    Filtra per urgenza: SCADUTO | CRITICO | ALTO | ATTENZIONE | OK
    """
    if not SUPABASE_URL:
        items = _demo_inventario()
        if urgenza:
            items = [i for i in items if i["urgenza"] == urgenza.upper()]
        if categoria:
            items = [i for i in items if i.get("categoria", "").lower() == categoria.lower()]
        if solo_alert:
            items = [i for i in items if i["urgenza"] in ("SCADUTO", "CRITICO", "ALTO")]
        items_sorted = sorted(items, key=lambda x: x.get("data_scadenza", ""))
        return {
            "articoli": items_sorted[:limit],
            "totale": len(items_sorted),
            "scaduti": sum(1 for i in items_sorted if i["urgenza"] == "SCADUTO"),
            "critici": sum(1 for i in items_sorted if i["urgenza"] == "CRITICO"),
            "nota": "Demo mode",
        }

    params: Dict = {
        "hotel_id": f"eq.{hotel_id}",
        "select": "id,nome,categoria,lotto_attivo,giacenza_attuale,unita_misura,data_scadenza_lotto,lotto_bloccato",
        "order": "data_scadenza_lotto.asc",
        "limit": str(limit),
    }
    if categoria:
        params["categoria"] = f"eq.{categoria}"

    async with httpx.AsyncClient() as client:
        r = await client.get(
            f"{SUPABASE_URL}/rest/v1/inventario",
            headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"},
            params=params,
        )
    rows = r.json() if r.status_code == 200 else []

    oggi = date.today()
    result = []
    for row in rows:
        ds = row.get("data_scadenza_lotto")
        if not ds:
            continue
        d = date.fromisoformat(ds[:10])
        giorni = (d - oggi).days
        urg = _urgenza(giorni)
        if urgenza and urg != urgenza.upper():
            continue
        if solo_alert and urg not in ("SCADUTO", "CRITICO", "ALTO"):
            continue
        result.append({**row, "giorni_alla_scadenza": giorni, "urgenza": urg})

    return {
        "articoli": result,
        "totale": len(result),
        "scaduti": sum(1 for i in result if i["urgenza"] == "SCADUTO"),
        "critici": sum(1 for i in result if i["urgenza"] == "CRITICO"),
    }


@router.get("/alerts", summary="Alert scadenze critiche")
async def get_alerts(hotel_id: str, giorni: int = Query(7, ge=1, le=30)):
    """Articoli in scadenza nei prossimi N giorni o già scaduti."""
    if not SUPABASE_URL:
        items = _demo_inventario()
        alerts = [i for i in items if i["urgenza"] in ("SCADUTO", "CRITICO", "ALTO", "ATTENZIONE")]
        return {
            "alerts": sorted(alerts, key=lambda x: x["giorni_alla_scadenza"]),
            "count_scaduti": sum(1 for a in alerts if a["urgenza"] == "SCADUTO"),
            "count_critici": sum(1 for a in alerts if a["urgenza"] == "CRITICO"),
            "nota": "Demo mode",
        }

    items_resp = await lista_scadenze(hotel_id=hotel_id, solo_alert=True)
    items = items_resp.get("articoli", [])
    cutoff = date.today() + timedelta(days=giorni)
    alerts = [
        i for i in items
        if i["urgenza"] in ("SCADUTO", "CRITICO")
        or (i.get("giorni_alla_scadenza", 999) <= giorni)
    ]
    return {
        "alerts": alerts,
        "count_scaduti": sum(1 for a in alerts if a["urgenza"] == "SCADUTO"),
        "count_critici": sum(1 for a in alerts if a["urgenza"] == "CRITICO"),
    }


@router.get("/fefo-order", summary="Ordine prelievo FEFO")
async def fefo_order(hotel_id: str, categoria: Optional[str] = None):
    """
    Restituisce la lista articoli ordinata FEFO (First Expired First Out)
    per guidare il personale nel prelievo ottimale.
    """
    if not SUPABASE_URL:
        items = _demo_inventario()
        if categoria:
            items = [i for i in items if i.get("categoria", "").lower() == categoria.lower()]
        fefo = sorted(
            [i for i in items if not i.get("lotto_bloccato") and i["urgenza"] != "SCADUTO"],
            key=lambda x: x.get("data_scadenza", "9999")
        )
        return {
            "fefo_list": fefo,
            "istruzioni": "Prelevare sempre l'articolo con data scadenza più vicina",
            "bloccati": sum(1 for i in items if i.get("lotto_bloccato")),
            "nota": "Demo mode",
        }

    items_resp = await lista_scadenze(hotel_id=hotel_id, categoria=categoria)
    fefo = [
        i for i in items_resp.get("articoli", [])
        if not i.get("lotto_bloccato") and i["urgenza"] != "SCADUTO"
    ]
    bloccati = sum(1 for i in items_resp.get("articoli", []) if i.get("lotto_bloccato"))
    return {
        "fefo_list": fefo,
        "istruzioni": "Prelevare sempre l'articolo con data scadenza più vicina",
        "bloccati": bloccati,
    }


@router.get("/summary", summary="Riepilogo mensile scadenze")
async def summary(hotel_id: str):
    """Riepilogo statistico scadenze: distribuzione urgenza, trend sprechi, top categorie a rischio."""
    if not SUPABASE_URL:
        items = _demo_inventario()
        from collections import Counter
        cat_rischio: Counter = Counter(
            i["categoria"] for i in items if i["urgenza"] in ("SCADUTO", "CRITICO", "ALTO")
        )
        return {
            "distribuzione": {
                "SCADUTO":    sum(1 for i in items if i["urgenza"] == "SCADUTO"),
                "CRITICO":    sum(1 for i in items if i["urgenza"] == "CRITICO"),
                "ALTO":       sum(1 for i in items if i["urgenza"] == "ALTO"),
                "ATTENZIONE": sum(1 for i in items if i["urgenza"] == "ATTENZIONE"),
                "OK":         sum(1 for i in items if i["urgenza"] == "OK"),
            },
            "categorie_top_rischio": dict(cat_rischio.most_common(3)),
            "totale_articoli": len(items),
            "nota": "Demo mode",
        }

    items_resp = await lista_scadenze(hotel_id=hotel_id)
    items = items_resp.get("articoli", [])
    from collections import Counter
    cat_rischio = Counter(
        i.get("categoria") for i in items if i.get("urgenza") in ("SCADUTO", "CRITICO", "ALTO")
    )
    return {
        "distribuzione": {
            "SCADUTO":    sum(1 for i in items if i.get("urgenza") == "SCADUTO"),
            "CRITICO":    sum(1 for i in items if i.get("urgenza") == "CRITICO"),
            "ALTO":       sum(1 for i in items if i.get("urgenza") == "ALTO"),
            "ATTENZIONE": sum(1 for i in items if i.get("urgenza") == "ATTENZIONE"),
            "OK":         sum(1 for i in items if i.get("urgenza") == "OK"),
        },
        "categorie_top_rischio": dict(cat_rischio.most_common(3)),
        "totale_articoli": len(items),
    }


@router.post("/blocca-lotto", summary="Blocca lotto scaduto o richiamato")
async def blocca_lotto(req: BloccaLottoRequest):
    """Blocca un lotto per scadenza, richiamo o NC HACCP. Impedisce ulteriori utilizzi."""
    payload = {
        "lotto_bloccato": True,
        "updated_at": datetime.utcnow().isoformat(),
    }

    if not SUPABASE_URL:
        return {
            "bloccato": True,
            "inventario_id": req.inventario_id,
            "motivo": req.motivo,
            "nota": "Demo mode",
        }

    async with httpx.AsyncClient() as client:
        r = await client.patch(
            f"{SUPABASE_URL}/rest/v1/inventario",
            headers={
                "apikey": SUPABASE_KEY,
                "Authorization": f"Bearer {SUPABASE_KEY}",
                "Content-Type": "application/json",
            },
            params={"id": f"eq.{req.inventario_id}", "hotel_id": f"eq.{req.hotel_id}"},
            json=payload,
        )
    return {"bloccato": r.status_code in (200, 204), "inventario_id": req.inventario_id}


# ══════════════════════════════════════════════════════════════════
#  PERSISTENZA REALE (fondamenta dati) — multi-tenant blindato
#  Tabella shelf_life_items; hotel_id SEMPRE dal JWT (require_user).
#  Aggiunge il WRITE PATH che prima mancava: ora l'utente inserisce
#  davvero il suo inventario e lo ritrova. Vedi supabase/shelf_life_schema.sql
# ══════════════════════════════════════════════════════════════════
from fastapi import Depends
from backend.database import get_supabase
from backend.auth import require_user, UserProfile


class ShelfItem(BaseModel):
    id: Optional[str] = None
    articolo: str
    categoria: str = ""
    lotto: str = ""
    giacenza_attuale: float = 0
    unita_misura: str = "kg"
    data_scadenza: str                      # YYYY-MM-DD
    fornitore: str = ""
    note: Optional[str] = None


def _sl_sb():
    sb = get_supabase()
    if not sb:
        raise HTTPException(503, "Database non configurato")
    return sb


def _sl_enrich(row: Dict) -> Dict:
    ds = row.get("data_scadenza")
    giorni = None
    urg = "OK"
    if ds:
        try:
            giorni = (date.fromisoformat(str(ds)[:10]) - date.today()).days
            urg = _urgenza(giorni)
        except Exception:
            pass
    return {**row, "giorni_alla_scadenza": giorni, "urgenza": urg}


@router.post("/item", summary="Crea/aggiorna un articolo dell'inventario (persistente)")
async def upsert_item(payload: ShelfItem, user: UserProfile = Depends(require_user)):
    sb = _sl_sb()
    rec = {
        "hotel_id": user.hotel_id,          # SEMPRE dal token (blindato)
        "articolo": payload.articolo, "categoria": payload.categoria,
        "lotto": payload.lotto, "giacenza_attuale": payload.giacenza_attuale,
        "unita_misura": payload.unita_misura, "data_scadenza": payload.data_scadenza,
        "fornitore": payload.fornitore, "note": payload.note,
        "updated_at": datetime.utcnow().isoformat(),
    }
    try:
        if payload.id:
            res = (sb.table("shelf_life_items").update(rec)
                   .eq("id", payload.id).eq("hotel_id", user.hotel_id).execute())
        else:
            res = sb.table("shelf_life_items").insert(rec).execute()
    except Exception as e:
        raise HTTPException(500, f"Errore salvataggio: {e}")
    saved = (res.data or [rec])[0]
    return {"ok": True, "item": _sl_enrich(saved)}


@router.get("/items", summary="Inventario reale dell'hotel (FEFO)")
async def list_items(user: UserProfile = Depends(require_user),
                     categoria: Optional[str] = None, solo_alert: bool = False):
    sb = _sl_sb()
    q = sb.table("shelf_life_items").select("*").eq("hotel_id", user.hotel_id)
    if categoria:
        q = q.eq("categoria", categoria)
    try:
        res = q.order("data_scadenza").execute()
    except Exception as e:
        raise HTTPException(500, f"Errore lettura: {e}")
    items = [_sl_enrich(r) for r in (res.data or [])]
    if solo_alert:
        items = [i for i in items if i["urgenza"] in ("SCADUTO", "CRITICO", "ALTO")]
    return {"ok": True, "articoli": items, "totale": len(items),
            "scaduti": sum(1 for i in items if i["urgenza"] == "SCADUTO"),
            "critici": sum(1 for i in items if i["urgenza"] == "CRITICO")}


@router.delete("/item/{item_id}", summary="Elimina un articolo")
async def delete_item(item_id: str, user: UserProfile = Depends(require_user)):
    sb = _sl_sb()
    try:
        sb.table("shelf_life_items").delete().eq("id", item_id).eq("hotel_id", user.hotel_id).execute()
    except Exception as e:
        raise HTTPException(500, f"Errore eliminazione: {e}")
    return {"ok": True}


@router.post("/item/{item_id}/blocca", summary="Blocca/sblocca lotto")
async def blocca_item(item_id: str, user: UserProfile = Depends(require_user), blocca: bool = True):
    sb = _sl_sb()
    try:
        sb.table("shelf_life_items").update({"lotto_bloccato": blocca,
            "updated_at": datetime.utcnow().isoformat()}).eq("id", item_id).eq("hotel_id", user.hotel_id).execute()
    except Exception as e:
        raise HTTPException(500, f"Errore: {e}")
    return {"ok": True, "bloccato": blocca}


# ══════════════════════════════════════════════════════════════════
#  SCHEDULER — job giornaliero 07:00 per alert scadenze
# ══════════════════════════════════════════════════════════════════

_scheduler = None


def _run_daily_expiry_check():
    """Job APScheduler: genera alert scadenze e li salva in expiry_alert_log."""
    if not SUPABASE_URL:
        logger.info("[ShelfLife Scheduler] Demo mode — nessun check su Supabase")
        return

    logger.info(f"[ShelfLife Scheduler] Avvio check scadenze {date.today()}")
    # In produzione: iterare su tutti gli hotel attivi e chiamare /alerts
    # Qui stub sincrono — in produzione usare asyncio.run() o httpx sincrono
    logger.info("[ShelfLife Scheduler] Check completato")


def start_scheduler():
    """Avvia lo scheduler APScheduler per il job giornaliero ore 07:00."""
    global _scheduler
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        _scheduler = BackgroundScheduler(timezone="Europe/Rome")
        _scheduler.add_job(
            _run_daily_expiry_check,
            trigger="cron",
            hour=7,
            minute=0,
            id="shelf_life_daily",
            replace_existing=True,
        )
        _scheduler.start()
        logger.info("[ShelfLife Scheduler] Avviato — job giornaliero ore 07:00")
    except ImportError:
        logger.warning("[ShelfLife Scheduler] APScheduler non installato — scheduler disabilitato")
    except Exception as e:
        logger.error(f"[ShelfLife Scheduler] Errore avvio: {e}")


def stop_scheduler():
    """Ferma lo scheduler al shutdown dell'applicazione."""
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("[ShelfLife Scheduler] Fermato")
