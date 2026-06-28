"""
BAD360.ai — Certificazioni API (persistenza reale, multi-tenant).

Sostituisce la vecchia cert.html (demo con dati hardcoded che mescolava 3 cose).
Tre aree distinte, tutte con hotel_id SEMPRE dal token (require_user), MAI dal client:
  1) cert_personale  — attestati del PERSONALE (HACCP, antincendio, primo soccorso, 81/08...)
  2) cert_licenze    — licenze/autorizzazioni del LOCALE (SCIA, autorizzazione sanitaria, somministrazione)
  3) cert_aziendali  — certificazioni AZIENDALI ISO/EMAS (per chi punta alla certificazione formale)

Lo stato (ok | in_scadenza | scaduto | permanente) e i giorni alla scadenza sono
CALCOLATI in lettura dalla data_scadenza (niente stato finto in DB).
Il piano HACCP/CCP NON si duplica qui: vive nel modulo HACCP (haccp.html / backend.haccp).
"""

from __future__ import annotations
from datetime import date
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from backend.database import get_supabase
from backend.auth import require_user, UserProfile

router = APIRouter(prefix="/api/cert", tags=["Certificazioni"])

ALERT_DAYS = 60          # entro N giorni dalla scadenza = "in scadenza"
IMMINENTI_DAYS = 90      # finestra del cruscotto "scadenze imminenti"


def _sb():
    sb = get_supabase()
    if not sb:
        raise HTTPException(503, "Database non configurato")
    return sb


def _parse_date(s) -> Optional[date]:
    if not s:
        return None
    try:
        return date.fromisoformat(str(s)[:10])
    except ValueError:
        return None


def _status(scadenza, alert_days: int = ALERT_DAYS):
    """Ritorna (stato, giorni_alla_scadenza) dalla data di scadenza."""
    d = _parse_date(scadenza)
    if d is None:
        return "permanente", None
    giorni = (d - date.today()).days
    if giorni < 0:
        return "scaduto", giorni
    if giorni <= alert_days:
        return "in_scadenza", giorni
    return "ok", giorni


def _enrich(row: dict) -> dict:
    stato, giorni = _status(row.get("data_scadenza"))
    row["stato"] = stato
    row["giorni_alla_scadenza"] = giorni
    return row


def _counts(rows):
    def c(s): return sum(1 for r in rows if r.get("stato") == s)
    return {"totale": len(rows), "ok": c("ok"), "in_scadenza": c("in_scadenza"),
            "scaduto": c("scaduto"), "permanente": c("permanente")}


# ══ 1) ATTESTATI PERSONALE ════════════════════════════════════════════
class CertPersonale(BaseModel):
    id: Optional[str] = None
    dipendente: str
    ruolo: str = ""
    tipo: str                          # HACCP|Allergeni|Sicurezza 81/08|Antincendio|Primo Soccorso|Preposto|...
    ente: str = ""
    data_rilascio: Optional[str] = None
    data_scadenza: Optional[str] = None
    file_url: str = ""
    note: str = ""


@router.post("/personale", summary="Crea/aggiorna un attestato del personale")
async def upsert_personale(payload: CertPersonale, user: UserProfile = Depends(require_user)):
    sb = _sb()
    rec = payload.dict(exclude={"id"})
    rec["hotel_id"] = user.hotel_id
    try:
        if payload.id:
            res = sb.table("cert_personale").update(rec).eq("id", payload.id).eq("hotel_id", user.hotel_id).execute()
        else:
            res = sb.table("cert_personale").insert(rec).execute()
    except Exception as e:
        raise HTTPException(500, f"Errore salvataggio attestato: {e}")
    return {"ok": True, "item": _enrich((res.data or [rec])[0])}


@router.get("/personale", summary="Lista attestati del personale (stato calcolato)")
async def list_personale(user: UserProfile = Depends(require_user), dipendente: Optional[str] = None):
    sb = _sb()
    q = sb.table("cert_personale").select("*").eq("hotel_id", user.hotel_id)
    if dipendente:
        q = q.eq("dipendente", dipendente)
    try:
        res = q.order("dipendente").order("tipo").execute()
    except Exception as e:
        raise HTTPException(500, f"Errore lettura attestati: {e}")
    rows = [_enrich(r) for r in (res.data or [])]
    return {"ok": True, "items": rows, **_counts(rows)}


@router.delete("/personale/{item_id}", summary="Elimina un attestato del personale")
async def delete_personale(item_id: str, user: UserProfile = Depends(require_user)):
    sb = _sb()
    try:
        sb.table("cert_personale").delete().eq("id", item_id).eq("hotel_id", user.hotel_id).execute()
    except Exception as e:
        raise HTTPException(500, f"Errore eliminazione: {e}")
    return {"ok": True}


# ══ 2) LICENZE / AUTORIZZAZIONI DEL LOCALE ════════════════════════════
class CertLicenza(BaseModel):
    id: Optional[str] = None
    tipo: str                          # SCIA|Autorizzazione sanitaria|Licenza somministrazione|Registrazione ASL|...
    numero: str = ""
    ente: str = ""
    data_rilascio: Optional[str] = None
    data_scadenza: Optional[str] = None    # vuoto = permanente
    file_url: str = ""
    note: str = ""


@router.post("/licenza", summary="Crea/aggiorna una licenza del locale")
async def upsert_licenza(payload: CertLicenza, user: UserProfile = Depends(require_user)):
    sb = _sb()
    rec = payload.dict(exclude={"id"})
    rec["hotel_id"] = user.hotel_id
    try:
        if payload.id:
            res = sb.table("cert_licenze").update(rec).eq("id", payload.id).eq("hotel_id", user.hotel_id).execute()
        else:
            res = sb.table("cert_licenze").insert(rec).execute()
    except Exception as e:
        raise HTTPException(500, f"Errore salvataggio licenza: {e}")
    return {"ok": True, "item": _enrich((res.data or [rec])[0])}


@router.get("/licenze", summary="Lista licenze/autorizzazioni del locale")
async def list_licenze(user: UserProfile = Depends(require_user)):
    sb = _sb()
    try:
        res = sb.table("cert_licenze").select("*").eq("hotel_id", user.hotel_id).order("tipo").execute()
    except Exception as e:
        raise HTTPException(500, f"Errore lettura licenze: {e}")
    rows = [_enrich(r) for r in (res.data or [])]
    return {"ok": True, "items": rows, **_counts(rows)}


@router.delete("/licenza/{item_id}", summary="Elimina una licenza")
async def delete_licenza(item_id: str, user: UserProfile = Depends(require_user)):
    sb = _sb()
    try:
        sb.table("cert_licenze").delete().eq("id", item_id).eq("hotel_id", user.hotel_id).execute()
    except Exception as e:
        raise HTTPException(500, f"Errore eliminazione: {e}")
    return {"ok": True}


# ══ 3) CERTIFICAZIONI AZIENDALI ISO/EMAS ══════════════════════════════
class CertAziendale(BaseModel):
    id: Optional[str] = None
    norma: str                         # ISO 22000:2018|ISO 9001:2015|EMAS / ISO 14001|...
    ente_certificatore: str = ""
    data_rilascio: Optional[str] = None
    data_scadenza: Optional[str] = None
    prossima_sorveglianza: Optional[str] = None
    file_url: str = ""
    note: str = ""


@router.post("/aziendale", summary="Crea/aggiorna una certificazione aziendale")
async def upsert_aziendale(payload: CertAziendale, user: UserProfile = Depends(require_user)):
    sb = _sb()
    rec = payload.dict(exclude={"id"})
    rec["hotel_id"] = user.hotel_id
    try:
        if payload.id:
            res = sb.table("cert_aziendali").update(rec).eq("id", payload.id).eq("hotel_id", user.hotel_id).execute()
        else:
            res = sb.table("cert_aziendali").insert(rec).execute()
    except Exception as e:
        raise HTTPException(500, f"Errore salvataggio certificazione: {e}")
    return {"ok": True, "item": _enrich((res.data or [rec])[0])}


@router.get("/aziendali", summary="Lista certificazioni aziendali ISO/EMAS")
async def list_aziendali(user: UserProfile = Depends(require_user)):
    sb = _sb()
    try:
        res = sb.table("cert_aziendali").select("*").eq("hotel_id", user.hotel_id).order("norma").execute()
    except Exception as e:
        raise HTTPException(500, f"Errore lettura certificazioni: {e}")
    rows = [_enrich(r) for r in (res.data or [])]
    return {"ok": True, "items": rows, **_counts(rows)}


@router.delete("/aziendale/{item_id}", summary="Elimina una certificazione aziendale")
async def delete_aziendale(item_id: str, user: UserProfile = Depends(require_user)):
    sb = _sb()
    try:
        sb.table("cert_aziendali").delete().eq("id", item_id).eq("hotel_id", user.hotel_id).execute()
    except Exception as e:
        raise HTTPException(500, f"Errore eliminazione: {e}")
    return {"ok": True}


# ══ CRUSCOTTO ═════════════════════════════════════════════════════════
@router.get("/dashboard", summary="Riepilogo compliance + scadenze imminenti (90 gg)")
async def dashboard(user: UserProfile = Depends(require_user)):
    sb = _sb()
    hid = user.hotel_id
    out = {"personale": [], "licenze": [], "aziendali": []}
    try:
        out["personale"] = [_enrich(r) for r in (sb.table("cert_personale").select("*").eq("hotel_id", hid).execute().data or [])]
        out["licenze"] = [_enrich(r) for r in (sb.table("cert_licenze").select("*").eq("hotel_id", hid).execute().data or [])]
        out["aziendali"] = [_enrich(r) for r in (sb.table("cert_aziendali").select("*").eq("hotel_id", hid).execute().data or [])]
    except Exception as e:
        raise HTTPException(500, f"Errore cruscotto: {e}")

    tutti = ([{**r, "area": "personale", "etichetta": f"{r.get('dipendente','')} · {r.get('tipo','')}"} for r in out["personale"]]
             + [{**r, "area": "licenza", "etichetta": r.get("tipo", "")} for r in out["licenze"]]
             + [{**r, "area": "aziendale", "etichetta": r.get("norma", "")} for r in out["aziendali"]])

    imminenti = sorted(
        [r for r in tutti if r.get("giorni_alla_scadenza") is not None and r["giorni_alla_scadenza"] <= IMMINENTI_DAYS],
        key=lambda r: r["giorni_alla_scadenza"],
    )
    riepilogo = _counts(tutti)
    return {"ok": True, "riepilogo": riepilogo,
            "per_area": {"personale": _counts(out["personale"]),
                         "licenze": _counts(out["licenze"]),
                         "aziendali": _counts(out["aziendali"])},
            "scadenze_imminenti": [
                {"area": r["area"], "etichetta": r["etichetta"], "tipo": r.get("tipo") or r.get("norma"),
                 "data_scadenza": r.get("data_scadenza"), "giorni": r["giorni_alla_scadenza"], "stato": r["stato"]}
                for r in imminenti]}
