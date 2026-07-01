"""
BAD360.ai — Privacy (GDPR) & Whistleblowing (niche C5)

Chiude il cluster compliance. Tre registri che OGNI struttura deve tenere ma quasi nessuna
tiene in ordine:
  1. Registro dei trattamenti (GDPR Art. 30) — CRUD.
  2. Registro data breach (Art. 33/34) — con flag notifica al Garante entro 72h.
  3. Canale whistleblowing (D.Lgs. 24/2023) — segnalazioni con codice di tracciamento anonimo.
+ helper AI: bozza informativa privacy e set di trattamenti tipici per l'ospitalità.

Human-in-the-loop: gli output AI sono BOZZE; la conformità va validata da un DPO/consulente.
Le segnalazioni whistleblowing sono riservate: vanno gestite solo dal gestore del canale.

Sicurezza: hotel_id SEMPRE dal token. Tabelle: privacy_trattamenti, privacy_breach,
whistleblowing_segnalazioni.
"""
from __future__ import annotations
import secrets
from datetime import datetime, timezone, date
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from backend.database import get_supabase
from backend.auth import require_user, UserProfile

router = APIRouter(prefix="/api/privacy", tags=["Privacy & Whistleblowing"])
DISCLAIMER = "⚠️ Bozza generata dall'AI — la conformità GDPR va validata da un DPO/consulente sui dati reali della struttura."

BASI_GIURIDICHE = {"contratto", "consenso", "obbligo_legale", "legittimo_interesse", "interesse_vitale", "interesse_pubblico"}
WB_CATEGORIE = {"illecito", "sicurezza", "molestie", "frode", "ambiente", "altro"}
WB_STATI = {"ricevuta", "in_esame", "gestita", "archiviata"}
BREACH_STATI = {"aperto", "gestito", "chiuso"}


def _sb():
    sb = get_supabase()
    if not sb:
        raise HTTPException(503, "Database non configurato")
    return sb


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ─────────────────────── 1) Registro trattamenti (Art. 30) ───────────────────────
class Trattamento(BaseModel):
    id:                    Optional[str] = None
    nome:                  str
    finalita:              Optional[str] = None
    base_giuridica:        str = "contratto"
    categorie_dati:        Optional[str] = None
    categorie_interessati: Optional[str] = None
    destinatari:           Optional[str] = None
    trasferimento_extra_ue: bool = False
    conservazione:         Optional[str] = None
    misure_sicurezza:      Optional[str] = None


@router.get("/trattamenti", summary="Registro dei trattamenti (Art. 30)")
async def list_trattamenti(user: UserProfile = Depends(require_user)):
    sb = _sb()
    rows = (sb.table("privacy_trattamenti").select("*").eq("hotel_id", user.hotel_id).order("created_at", desc=True).execute().data) or []
    return {"ok": True, "trattamenti": rows, "totale": len(rows)}


@router.post("/trattamenti", summary="Crea/aggiorna trattamento")
async def upsert_trattamento(payload: Trattamento, user: UserProfile = Depends(require_user)):
    if payload.base_giuridica not in BASI_GIURIDICHE:
        raise HTTPException(400, "Base giuridica non valida")
    sb = _sb()
    data = {"hotel_id": user.hotel_id, "nome": payload.nome.strip(), "finalita": (payload.finalita or "").strip(),
            "base_giuridica": payload.base_giuridica, "categorie_dati": (payload.categorie_dati or "").strip(),
            "categorie_interessati": (payload.categorie_interessati or "").strip(), "destinatari": (payload.destinatari or "").strip(),
            "trasferimento_extra_ue": bool(payload.trasferimento_extra_ue), "conservazione": (payload.conservazione or "").strip(),
            "misure_sicurezza": (payload.misure_sicurezza or "").strip()}
    if payload.id:
        res = sb.table("privacy_trattamenti").update(data).eq("id", payload.id).eq("hotel_id", user.hotel_id).execute()
        if not res.data:
            raise HTTPException(404, "Trattamento non trovato")
        return {"ok": True, "trattamento": res.data[0]}
    data["created_at"] = _now()
    res = sb.table("privacy_trattamenti").insert(data).execute()
    return {"ok": True, "trattamento": res.data[0] if res.data else data}


@router.delete("/trattamenti/{tid}", summary="Elimina trattamento")
async def delete_trattamento(tid: str, user: UserProfile = Depends(require_user)):
    sb = _sb()
    sb.table("privacy_trattamenti").delete().eq("id", tid).eq("hotel_id", user.hotel_id).execute()
    return {"ok": True}


# ─────────────────────── 2) Registro data breach (Art. 33/34) ───────────────────────
class Breach(BaseModel):
    id:               Optional[str] = None
    data_evento:      str
    descrizione:      str
    dati_coinvolti:   Optional[str] = None
    gravita:          str = "media"          # bassa | media | alta
    notificato_garante: bool = False
    data_notifica:    Optional[str] = None
    stato:            str = "aperto"


@router.get("/breach", summary="Registro violazioni dati")
async def list_breach(user: UserProfile = Depends(require_user)):
    sb = _sb()
    rows = (sb.table("privacy_breach").select("*").eq("hotel_id", user.hotel_id).order("data_evento", desc=True).execute().data) or []
    return {"ok": True, "breach": rows, "totale": len(rows)}


@router.post("/breach", summary="Registra violazione")
async def upsert_breach(payload: Breach, user: UserProfile = Depends(require_user)):
    if payload.gravita not in {"bassa", "media", "alta"}:
        raise HTTPException(400, "Gravità non valida")
    if payload.stato not in BREACH_STATI:
        raise HTTPException(400, "Stato non valido")
    sb = _sb()
    data = {"hotel_id": user.hotel_id, "data_evento": payload.data_evento, "descrizione": payload.descrizione.strip(),
            "dati_coinvolti": (payload.dati_coinvolti or "").strip(), "gravita": payload.gravita,
            "notificato_garante": bool(payload.notificato_garante), "data_notifica": payload.data_notifica or None,
            "stato": payload.stato}
    if payload.id:
        res = sb.table("privacy_breach").update(data).eq("id", payload.id).eq("hotel_id", user.hotel_id).execute()
        if not res.data:
            raise HTTPException(404, "Violazione non trovata")
        return {"ok": True, "breach": res.data[0]}
    data["created_at"] = _now()
    res = sb.table("privacy_breach").insert(data).execute()
    return {"ok": True, "breach": res.data[0] if res.data else data}


@router.delete("/breach/{bid}", summary="Elimina violazione")
async def delete_breach(bid: str, user: UserProfile = Depends(require_user)):
    sb = _sb()
    sb.table("privacy_breach").delete().eq("id", bid).eq("hotel_id", user.hotel_id).execute()
    return {"ok": True}


# ─────────────────────── 3) Whistleblowing (D.Lgs. 24/2023) ───────────────────────
class Segnalazione(BaseModel):
    oggetto:     str
    categoria:   str = "altro"
    descrizione: str
    anonima:     bool = True


class SegnalazioneStato(BaseModel):
    stato: str
    esito: Optional[str] = None


@router.get("/whistleblowing", summary="Canale segnalazioni (gestore)")
async def list_segnalazioni(user: UserProfile = Depends(require_user)):
    sb = _sb()
    rows = (sb.table("whistleblowing_segnalazioni").select("*").eq("hotel_id", user.hotel_id).order("created_at", desc=True).execute().data) or []
    return {"ok": True, "segnalazioni": rows, "totale": len(rows)}


@router.post("/whistleblowing", summary="Invia segnalazione (genera codice di tracciamento)")
async def create_segnalazione(payload: Segnalazione, user: UserProfile = Depends(require_user)):
    if payload.categoria not in WB_CATEGORIE:
        raise HTTPException(400, "Categoria non valida")
    sb = _sb()
    codice = "WB-" + secrets.token_hex(4).upper()
    data = {"hotel_id": user.hotel_id, "codice": codice, "oggetto": payload.oggetto.strip(),
            "categoria": payload.categoria, "descrizione": payload.descrizione.strip(),
            "anonima": bool(payload.anonima), "stato": "ricevuta", "esito": "", "created_at": _now()}
    sb.table("whistleblowing_segnalazioni").insert(data).execute()
    # NB: si restituisce solo il codice, non l'id interno — così il segnalante può seguire la pratica.
    return {"ok": True, "codice": codice}


@router.put("/whistleblowing/{sid}/stato", summary="Aggiorna stato/esito segnalazione (gestore)")
async def set_stato_segnalazione(sid: str, payload: SegnalazioneStato, user: UserProfile = Depends(require_user)):
    if payload.stato not in WB_STATI:
        raise HTTPException(400, "Stato non valido")
    sb = _sb()
    res = sb.table("whistleblowing_segnalazioni").update(
        {"stato": payload.stato, "esito": (payload.esito or "").strip()}
    ).eq("id", sid).eq("hotel_id", user.hotel_id).execute()
    if not res.data:
        raise HTTPException(404, "Segnalazione non trovata")
    return {"ok": True, "segnalazione": res.data[0]}


# ─────────────────────── Dashboard ───────────────────────
def _giorni_da(d: Optional[str]) -> Optional[int]:
    if not d:
        return None
    try:
        return (date.today() - date.fromisoformat(str(d)[:10])).days
    except Exception:
        return None


@router.get("/dashboard", summary="KPI privacy + whistleblowing")
async def dashboard(user: UserProfile = Depends(require_user)):
    sb = _sb()
    tratt = (sb.table("privacy_trattamenti").select("*").eq("hotel_id", user.hotel_id).execute().data) or []
    breach = (sb.table("privacy_breach").select("*").eq("hotel_id", user.hotel_id).execute().data) or []
    segn = (sb.table("whistleblowing_segnalazioni").select("*").eq("hotel_id", user.hotel_id).execute().data) or []

    breach_aperti = sum(1 for b in breach if b.get("stato") == "aperto")
    # violazioni non notificate al Garante oltre 72h (alert Art. 33)
    breach_oltre_72h = 0
    for b in breach:
        if not b.get("notificato_garante"):
            g = _giorni_da(b.get("data_evento"))
            if g is not None and g > 3:
                breach_oltre_72h += 1
    segn_aperte = sum(1 for s in segn if s.get("stato") in ("ricevuta", "in_esame"))

    checklist = [
        {"voce": "Registro dei trattamenti compilato (Art. 30)", "ok": len(tratt) > 0},
        {"voce": "Nessuna violazione aperta non gestita", "ok": breach_aperti == 0},
        {"voce": "Notifiche al Garante entro 72h", "ok": breach_oltre_72h == 0},
        {"voce": "Canale whistleblowing attivo (D.Lgs. 24/2023)", "ok": True},
        {"voce": "Segnalazioni prese in carico", "ok": segn_aperte == 0},
    ]
    fatti = sum(1 for c in checklist if c["ok"])
    return {"ok": True, "kpi": {
        "trattamenti": len(tratt), "breach_totali": len(breach), "breach_aperti": breach_aperti,
        "breach_oltre_72h": breach_oltre_72h, "segnalazioni": len(segn), "segnalazioni_aperte": segn_aperte,
        "readiness_pct": round(fatti / len(checklist) * 100),
    }, "checklist": checklist}


# ─────────────────────── AI helpers (human-in-the-loop) ───────────────────────
class InformativaBody(BaseModel):
    tipo_struttura: str = "hotel"
    canali:         Optional[str] = None   # es. "sito, booking, email, telefono"
    nome_struttura: Optional[str] = None


@router.post("/ai/informativa", summary="Genera bozza informativa privacy")
async def ai_informativa(body: InformativaBody, user: UserProfile = Depends(require_user)):
    prompt = (
        "Sei un consulente privacy (GDPR) per l'ospitalità. Redigi una BOZZA di informativa privacy "
        "sintetica e chiara per gli ospiti di una struttura ricettiva italiana. Includi: titolare del "
        "trattamento (placeholder), finalità (prenotazione, check-in/alloggiati web, imposta di soggiorno, "
        "marketing con consenso), basi giuridiche, categorie di dati, conservazione, diritti dell'interessato "
        "(Artt. 15-22), e un placeholder per il DPO. Usa [DA COMPLETARE] per i dati mancanti. Italiano, conciso.\n\n"
        f"Tipo struttura: {body.tipo_struttura}\nNome: {body.nome_struttura or '[DA COMPLETARE]'}\n"
        f"Canali di raccolta: {body.canali or 'sito, booking, reception'}"
    )
    ai = None
    try:
        from backend.ai_agents import _ask_claude
        ai = await _ask_claude(prompt, max_tokens=900)
    except Exception:
        ai = None
    return {"ok": True, "bozza": (ai or "").strip() or "[AI non disponibile — configura ANTHROPIC_API_KEY]", "disclaimer": DISCLAIMER}


@router.post("/ai/registro-suggerito", summary="Suggerisci trattamenti tipici per l'ospitalità")
async def ai_registro(user: UserProfile = Depends(require_user)):
    prompt = (
        "Elenca i trattamenti di dati personali TIPICI di una struttura ricettiva (hotel/B&B/casa vacanza) "
        "da inserire nel registro dei trattamenti (GDPR Art. 30). Per ciascuno indica in una riga: nome — "
        "finalità — base giuridica. Massimo 8 trattamenti, concreti (es. prenotazioni, alloggiati web, "
        "videosorveglianza, marketing, gestione dipendenti, fornitori). Italiano, elenco puntato."
    )
    ai = None
    try:
        from backend.ai_agents import _ask_claude
        ai = await _ask_claude(prompt, max_tokens=700)
    except Exception:
        ai = None
    return {"ok": True, "suggerimenti": (ai or "").strip() or "[AI non disponibile — configura ANTHROPIC_API_KEY]", "disclaimer": DISCLAIMER}
