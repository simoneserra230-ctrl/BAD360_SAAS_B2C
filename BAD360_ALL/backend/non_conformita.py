# ═══════════════════════════════════════════════════════════════════
#  BAD.S Unified Platform — Router Non Conformità
#  File: backend/non_conformita.py
#
#  Aggiungere in main.py:
#    from backend.non_conformita import router as nc_router
#    app.include_router(nc_router)
# ═══════════════════════════════════════════════════════════════════

from __future__ import annotations
from datetime import date, datetime
from typing import Optional, List
from uuid import UUID
import os

import anthropic
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from backend.database import get_supabase

router = APIRouter(prefix="/api/nc", tags=["Non Conformità"])

# ──────────────────────────────────────────────────────────────────
#  COSTANTI
# ──────────────────────────────────────────────────────────────────

SLA_ORE = {"critica": 4, "alta": 24, "media": 72, "bassa": 168}

TRANSIZIONI_VALIDE = {
    "aperta":          ["in_contenimento", "in_analisi", "annullata"],
    "in_contenimento": ["in_analisi", "annullata"],
    "in_analisi":      ["in_corso", "annullata"],
    "in_corso":        ["in_verifica", "in_analisi"],
    "in_verifica":     ["chiusa", "in_corso"],
    "chiusa":          [],
    "annullata":       [],
}

# ──────────────────────────────────────────────────────────────────
#  MODELLI PYDANTIC
# ──────────────────────────────────────────────────────────────────

class NCApertura(BaseModel):
    hotel_id:       UUID
    area:           str
    gravita:        str = "media"
    titolo:         str
    descrizione:    str
    evidenza_url:   Optional[str] = None
    # FK opzionali alle sorgenti
    haccp_temp_id:  Optional[UUID] = None
    lotto_id:       Optional[UUID] = None
    fornitore_id:   Optional[UUID] = None
    ordine_id:      Optional[UUID] = None
    azione_immediata: Optional[str] = None
    rilevato_da:    Optional[str] = None


class NCContenimento(BaseModel):
    azione_immediata:       str
    contenimento_operatore: Optional[str] = None


class NCAnalisi(BaseModel):
    metodo_analisi: str = "5why"        # 5why | ishikawa | fta | ai
    causa_radice:   Optional[str] = None
    domande_5why:   Optional[List[dict]] = None  # [{livello:1, domanda:"...", risposta:"..."}]
    usa_ai:         bool = False


class NCPianoAC(BaseModel):
    azione_correttiva:  str
    responsabile_ac:    str
    scadenza_ac:        date


class NCVerifica(BaseModel):
    verifica_descrizione:   str
    verifica_efficace:      bool
    verifica_operatore:     Optional[str] = None
    lezione_appresa:        Optional[str] = None


class NCChiusura(BaseModel):
    lezione_appresa:    str
    chiusa_da:          Optional[str] = None


# ──────────────────────────────────────────────────────────────────
#  HELPERS
# ──────────────────────────────────────────────────────────────────

def _serial(data: dict) -> dict:
    """Converte UUID e date in stringhe per Supabase."""
    out = {}
    for k, v in data.items():
        if v is None:
            continue
        if isinstance(v, UUID):
            out[k] = str(v)
        elif isinstance(v, (date, datetime)):
            out[k] = v.isoformat()
        else:
            out[k] = v
    return out


def _get_nc(sb, nc_id: str) -> dict:
    res = sb.table("non_conformita").select("*").eq("id", nc_id).single().execute()
    if not res.data:
        raise HTTPException(404, f"NC {nc_id} non trovata")
    return res.data


def _log(sb, nc_id: str, stato_da: str, stato_a: str, azione: str, operatore: str = ""):
    sb.table("nc_log").insert({
        "nc_id": nc_id, "stato_da": stato_da,
        "stato_a": stato_a, "azione": azione, "operatore": operatore
    }).execute()


def _cambia_stato(sb, nc_id: str, nuovo_stato: str, operatore: str = "", extra: dict = None):
    nc = _get_nc(sb, nc_id)
    stato_attuale = nc["stato"]

    if nuovo_stato not in TRANSIZIONI_VALIDE.get(stato_attuale, []):
        raise HTTPException(400,
            f"Transizione non ammessa: {stato_attuale} → {nuovo_stato}. "
            f"Ammesse: {TRANSIZIONI_VALIDE[stato_attuale]}")

    update_data = {"stato": nuovo_stato, **(extra or {})}
    sb.table("non_conformita").update(update_data).eq("id", nc_id).execute()
    _log(sb, nc_id, stato_attuale, nuovo_stato, f"Cambio stato: {stato_attuale}→{nuovo_stato}", operatore)
    return nc


# ──────────────────────────────────────────────────────────────────
#  ENDPOINT 1: APERTURA NC
# ──────────────────────────────────────────────────────────────────

@router.post("", summary="Apre una nuova Non Conformità")
async def apri_nc(payload: NCApertura):
    """
    Punto di ingresso: crea la NC in stato 'aperta'.
    Il numero NC (NC-YYYY-MM-NNNN) viene generato automaticamente dal trigger DB.
    Se gravità='critica', viene impostato automaticamente il contenimento immediato.
    """
    sb = get_supabase()
    if not sb:
        raise HTTPException(503, "Database non configurato")

    data = _serial(payload.dict())
    res = sb.table("non_conformita").insert(data).execute()
    if not res.data:
        raise HTTPException(400, "Errore creazione NC")

    nc = res.data[0]
    _log(sb, nc["id"], None, "aperta", "NC aperta", payload.rilevato_da or "")

    return {
        "ok": True,
        "nc_id":      nc["id"],
        "numero_nc":  nc.get("numero_nc"),
        "stato":      nc["stato"],
        "sla_ore":    SLA_ORE.get(payload.gravita, 72),
        "messaggio":  f"NC {nc.get('numero_nc')} aperta. SLA: {SLA_ORE.get(payload.gravita, 72)}h"
    }


# ──────────────────────────────────────────────────────────────────
#  ENDPOINT 2: CONTENIMENTO IMMEDIATO
# ──────────────────────────────────────────────────────────────────

@router.put("/{nc_id}/contenimento", summary="Registra azione di contenimento immediato")
async def registra_contenimento(nc_id: str, payload: NCContenimento):
    """
    Step 2 del ciclo 8D: D3 — Azione contenimento.
    Sposta lo stato in 'in_contenimento' e registra cosa è stato fatto.
    Tipico: isolamento lotto, blocco fornitore, chiusura zona.
    """
    sb = get_supabase()
    if not sb:
        raise HTTPException(503, "Database non configurato")

    _cambia_stato(sb, nc_id, "in_contenimento",
                  payload.contenimento_operatore or "",
                  {"azione_immediata": payload.azione_immediata,
                   "contenimento_operatore": payload.contenimento_operatore,
                   "contenimento_at": datetime.now().isoformat()})

    return {"ok": True, "stato": "in_contenimento", "azione": payload.azione_immediata}


# ──────────────────────────────────────────────────────────────────
#  ENDPOINT 3: ANALISI CAUSA RADICE (con AI opzionale)
# ──────────────────────────────────────────────────────────────────

@router.put("/{nc_id}/analisi", summary="Registra analisi causa radice (opzionale: AI)")
async def registra_analisi(nc_id: str, payload: NCAnalisi):
    """
    Step 3 (8D: D4).
    Se usa_ai=True, Claude analizza la descrizione NC e i 5-Why per
    suggerire causa radice e azioni correttive.
    """
    sb = get_supabase()
    if not sb:
        raise HTTPException(503, "Database non configurato")

    nc = _get_nc(sb, nc_id)
    analisi_ai_text = None

    # Salva i 5-Why se forniti
    if payload.domande_5why:
        for item in payload.domande_5why:
            sb.table("nc_azioni_5why").insert({
                "nc_id": nc_id,
                "livello": item.get("livello", 1),
                "domanda": item.get("domanda", ""),
                "risposta": item.get("risposta", "")
            }).execute()

    # Analisi AI
    if payload.usa_ai:
        analisi_ai_text = await _ai_root_cause(nc, payload)

    update_data = {
        "metodo_analisi": payload.metodo_analisi,
        "causa_radice":   payload.causa_radice,
        "analisi_ai":     analisi_ai_text,
        "analisi_at":     datetime.now().isoformat()
    }
    _cambia_stato(sb, nc_id, "in_analisi", "", update_data)

    return {
        "ok": True,
        "stato":       "in_analisi",
        "causa_radice": payload.causa_radice,
        "analisi_ai":  analisi_ai_text
    }


async def _ai_root_cause(nc: dict, payload: NCAnalisi) -> str:
    """Chiama Claude per analisi causa radice e suggerimento azioni correttive."""
    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

    why_testo = ""
    if payload.domande_5why:
        righe = [f"  Why {w['livello']}: {w['domanda']} → {w.get('risposta','...')}"
                 for w in payload.domande_5why]
        why_testo = "\n".join(righe)

    prompt = f"""Sei un consulente ISO 9001/22000 per strutture ricettive italiane.
Analizza questa Non Conformità e fornisci:
1. Causa radice più probabile
2. Tre azioni correttive concrete e misurabili
3. Azione preventiva per evitare ricorrenze
4. Indicatore KPI per misurare l'efficacia

NON CONFORMITÀ:
- Area: {nc.get('area')}
- Gravità: {nc.get('gravita')}
- Titolo: {nc.get('titolo')}
- Descrizione: {nc.get('descrizione')}
- Azione immediata adottata: {nc.get('azione_immediata', 'nessuna')}

ANALISI 5-WHY:
{why_testo or 'non disponibile'}

Rispondi in italiano, formato conciso, max 300 parole."""

    msg = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=600,
        messages=[{"role": "user", "content": prompt}]
    )
    return msg.content[0].text if msg.content else ""


# ──────────────────────────────────────────────────────────────────
#  ENDPOINT 4: PIANO AZIONE CORRETTIVA
# ──────────────────────────────────────────────────────────────────

@router.put("/{nc_id}/piano-ac", summary="Assegna piano di azione correttiva")
async def assegna_piano_ac(nc_id: str, payload: NCPianoAC):
    """
    Step 4 (8D: D5-D6): definisce cosa fare, chi lo fa e entro quando.
    Obbligatorio prima di procedere alla verifica.
    """
    sb = get_supabase()
    if not sb:
        raise HTTPException(503, "Database non configurato")

    _cambia_stato(sb, nc_id, "in_corso", payload.responsabile_ac, {
        "azione_correttiva":  payload.azione_correttiva,
        "responsabile_ac":    payload.responsabile_ac,
        "scadenza_ac":        payload.scadenza_ac.isoformat(),
        "ac_avviata_at":      datetime.now().isoformat()
    })

    return {
        "ok": True,
        "stato":            "in_corso",
        "responsabile":     payload.responsabile_ac,
        "scadenza":         payload.scadenza_ac.isoformat(),
        "azione":           payload.azione_correttiva
    }


# ──────────────────────────────────────────────────────────────────
#  ENDPOINT 5: VERIFICA EFFICACIA
# ──────────────────────────────────────────────────────────────────

@router.put("/{nc_id}/verifica", summary="Registra verifica efficacia azione correttiva")
async def verifica_efficacia(nc_id: str, payload: NCVerifica):
    """
    Step 5 (8D: D7): l'azione è stata eseguita, si verifica se ha risolto il problema.
    - efficace=True  → NC passa a 'chiusa'
    - efficace=False → NC torna a 'in_corso' per rivalutazione
    """
    sb = get_supabase()
    if not sb:
        raise HTTPException(503, "Database non configurato")

    nuovo_stato = "chiusa" if payload.verifica_efficace else "in_corso"
    extra = {
        "verifica_descrizione": payload.verifica_descrizione,
        "verifica_efficace":    payload.verifica_efficace,
        "verifica_at":          datetime.now().isoformat(),
        "verifica_operatore":   payload.verifica_operatore,
    }
    if payload.verifica_efficace:
        extra["chiusa_at"] = datetime.now().isoformat()
        if payload.lezione_appresa:
            extra["lezione_appresa"] = payload.lezione_appresa

    _cambia_stato(sb, nc_id, nuovo_stato, payload.verifica_operatore or "", extra)

    return {
        "ok":     True,
        "stato":  nuovo_stato,
        "esito":  "NC chiusa con successo" if payload.verifica_efficace
                  else "Azione non efficace — revisione piano richiesta"
    }


# ──────────────────────────────────────────────────────────────────
#  ENDPOINT 6: CHIUSURA FORMALE (8D: D8)
# ──────────────────────────────────────────────────────────────────

@router.put("/{nc_id}/chiudi", summary="Chiusura formale NC con lezione appresa")
async def chiudi_nc(nc_id: str, payload: NCChiusura):
    sb = get_supabase()
    if not sb:
        raise HTTPException(503, "Database non configurato")

    _cambia_stato(sb, nc_id, "chiusa", payload.chiusa_da or "", {
        "lezione_appresa": payload.lezione_appresa,
        "chiusa_da":       payload.chiusa_da,
        "chiusa_at":       datetime.now().isoformat()
    })

    return {"ok": True, "stato": "chiusa", "messaggio": "NC chiusa e documentata ✓"}


# ──────────────────────────────────────────────────────────────────
#  QUERY E DASHBOARD
# ──────────────────────────────────────────────────────────────────

@router.get("", summary="Lista NC con filtri")
async def lista_nc(
    hotel_id:   UUID,
    stato:      Optional[str] = None,
    area:       Optional[str] = None,
    gravita:    Optional[str] = None,
    aperte:     bool = False,           # scorciatoia: solo non chiuse/annullate
    limit:      int  = Query(50, le=200)
):
    sb = get_supabase()
    if not sb:
        return {"nc": _demo_lista(), "totale": 3}

    q = sb.table("non_conformita").select(
        "*, nc_log(stato_a, ts, operatore)"
    ).eq("hotel_id", str(hotel_id))

    if aperte:
        q = q.not_.in_("stato", ["chiusa", "annullata"])
    elif stato:
        q = q.eq("stato", stato)

    if area:
        q = q.eq("area", area)
    if gravita:
        q = q.eq("gravita", gravita)

    res = q.order("rilevato_at", desc=True).limit(limit).execute()
    return {"nc": res.data or [], "totale": len(res.data or [])}


@router.get("/dashboard", summary="📊 KPI Non Conformità")
async def dashboard_nc(hotel_id: UUID):
    """
    KPI per il Responsabile Qualità:
    - NC per stato e area
    - % SLA rispettati
    - Tempo medio chiusura
    - NC ricorrenti (indicatore sistema qualità)
    """
    sb = get_supabase()
    if not sb:
        return _demo_dashboard()

    h = str(hotel_id)
    tutte = sb.table("non_conformita").select(
        "stato, area, gravita, ricorrente, rilevato_at, chiusa_at, scadenza_ac"
    ).eq("hotel_id", h).execute().data or []

    aperte    = [n for n in tutte if n["stato"] not in ("chiusa","annullata")]
    critiche  = [n for n in aperte if n["gravita"] == "critica"]
    ricorr    = sum(1 for n in tutte if n.get("ricorrente"))

    # NC per area
    per_area = {}
    for n in aperte:
        per_area[n["area"]] = per_area.get(n["area"], 0) + 1

    # SLA scaduti
    sla_scaduti = 0
    from datetime import timezone
    for n in aperte:
        sla = SLA_ORE.get(n["gravita"], 72)
        if n.get("rilevato_at"):
            try:
                apertura = datetime.fromisoformat(n["rilevato_at"].replace("Z","+00:00"))
                delta_h = (datetime.now(timezone.utc) - apertura).total_seconds() / 3600
                if delta_h > sla:
                    sla_scaduti += 1
            except Exception:
                pass

    # Tempo medio chiusura (ore) sulle NC chiuse
    tempi = []
    for n in tutte:
        if n["stato"] == "chiusa" and n.get("chiusa_at") and n.get("rilevato_at"):
            try:
                ap = datetime.fromisoformat(n["rilevato_at"].replace("Z","+00:00"))
                ch = datetime.fromisoformat(n["chiusa_at"].replace("Z","+00:00"))
                tempi.append((ch - ap).total_seconds() / 3600)
            except Exception:
                pass

    return {
        "kpi": {
            "totale_nc":           len(tutte),
            "nc_aperte":           len(aperte),
            "nc_critiche_aperte":  len(critiche),
            "sla_scaduti":         sla_scaduti,
            "nc_ricorrenti":       ricorr,
            "per_area":            per_area,
            "tempo_medio_chiusura_ore": round(sum(tempi)/len(tempi), 1) if tempi else None,
            "tasso_chiusura_pct":  round(
                sum(1 for n in tutte if n["stato"]=="chiusa") / len(tutte) * 100, 1
            ) if tutte else 100,
        }
    }


@router.get("/{nc_id}", summary="Dettaglio NC con log e 5-Why")
async def dettaglio_nc(nc_id: str):
    sb = get_supabase()
    if not sb:
        raise HTTPException(503, "Database non configurato")

    nc   = _get_nc(sb, nc_id)
    log  = sb.table("nc_log").select("*").eq("nc_id", nc_id).order("ts").execute().data or []
    why  = sb.table("nc_azioni_5why").select("*").eq("nc_id", nc_id).order("livello").execute().data or []

    return {"nc": nc, "log": log, "5why": why}


@router.delete("/{nc_id}/annulla", summary="Annulla NC (falso positivo)")
async def annulla_nc(nc_id: str, motivo: str = "Falso positivo", operatore: str = ""):
    sb = get_supabase()
    if not sb:
        raise HTTPException(503, "Database non configurato")

    _cambia_stato(sb, nc_id, "annullata", operatore, {"note_annullamento": motivo})
    return {"ok": True, "stato": "annullata"}


# ──────────────────────────────────────────────────────────────────
#  INTEGRAZIONE: NC da HACCP (chiamata da haccp endpoint esistente)
# ──────────────────────────────────────────────────────────────────

@router.post("/from-haccp", summary="Apre NC automatica da alert temperatura HACCP",
             include_in_schema=False)
async def nc_da_haccp(hotel_id: UUID, sensor_id: str, zona: str,
                      temperatura: float, temp_min: float, temp_max: float,
                      severity: str, haccp_temp_id: Optional[UUID] = None):
    """
    Chiamato internamente da backend/haccp_report.py quando
    viene registrata una temperatura fuori range.
    """
    sb = get_supabase()
    if not sb:
        return {"ok": False}

    payload = NCApertura(
        hotel_id=hotel_id,
        area="haccp",
        gravita="critica" if severity == "critical" else "alta",
        titolo=f"Temperatura fuori range — {zona.replace('_', ' ')}",
        descrizione=(
            f"Zona: {zona} | Temperatura rilevata: {temperatura}°C | "
            f"Range ammesso: {temp_min}–{temp_max}°C | Sensor: {sensor_id}"
        ),
        azione_immediata=f"Verificare immediatamente {zona} e spostare prodotti se necessario",
        haccp_temp_id=haccp_temp_id,
        rilevato_da="sistema_iot"
    )
    return await apri_nc(payload)


# ──────────────────────────────────────────────────────────────────
#  DEMO DATA
# ──────────────────────────────────────────────────────────────────

def _demo_lista():
    return [
        {"numero_nc": "NC-2026-03-0001", "area": "haccp", "gravita": "critica",
         "stato": "in_contenimento", "titolo": "Cella frigo +8°C",
         "rilevato_at": "2026-03-30T07:15:00"},
        {"numero_nc": "NC-2026-03-0002", "area": "fornitore", "gravita": "media",
         "stato": "aperta", "titolo": "DDT mancante",
         "rilevato_at": "2026-03-30T09:00:00"},
        {"numero_nc": "NC-2026-03-0003", "area": "housekeeping", "gravita": "bassa",
         "stato": "chiusa", "titolo": "Macchia camera 214",
         "rilevato_at": "2026-03-29T14:30:00"},
    ]


def _demo_dashboard():
    return {
        "kpi": {
            "totale_nc": 12,
            "nc_aperte": 3,
            "nc_critiche_aperte": 1,
            "sla_scaduti": 1,
            "nc_ricorrenti": 2,
            "per_area": {"haccp": 1, "fornitore": 1, "housekeeping": 1},
            "tempo_medio_chiusura_ore": 18.4,
            "tasso_chiusura_pct": 75.0,
        },
        "_demo": True
    }
