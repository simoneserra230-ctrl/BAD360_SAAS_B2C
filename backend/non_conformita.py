# ═══════════════════════════════════════════════════════════════════
#  BAD360.ai — Router Non Conformità (NC)  ·  MULTI-TENANT BLINDATO
#  File: backend/non_conformita.py
#
#  Sicurezza (come gli altri moduli gestionali):
#    - require_user su OGNI endpoint
#    - hotel_id SEMPRE da user.hotel_id (mai dal client)
#    - ogni query/mutazione filtrata per hotel_id, anche i lookup per id
#  Tabelle nuove con hotel_id TEXT: vedi supabase/nc_schema.sql
#
#  Registrato in main.py:
#    from backend.non_conformita import router as nc_router
#    app.include_router(nc_router)
# ═══════════════════════════════════════════════════════════════════

from __future__ import annotations
from datetime import date, datetime, timezone
from typing import Optional, List
import os

import anthropic
from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel

from backend.database import get_supabase
from backend.auth import require_user, UserProfile

router = APIRouter(prefix="/api/nc", tags=["Non Conformità"])

# ──────────────────────────────────────────────────────────────────
#  COSTANTI  (SLA allineati alla guida mostrata nel frontend)
# ──────────────────────────────────────────────────────────────────

SLA_ORE = {"critica": 2, "alta": 8, "media": 48, "bassa": 168}

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
#  MODELLI PYDANTIC  (hotel_id NON è più un input del client)
# ──────────────────────────────────────────────────────────────────

class NCApertura(BaseModel):
    area:           str
    gravita:        str = "media"
    titolo:         str
    descrizione:    str
    evidenza_url:   Optional[str] = None
    # riferimenti opzionali alle sorgenti (TEXT, nessun vincolo FK rigido)
    haccp_temp_id:  Optional[str] = None
    lotto_id:       Optional[str] = None
    fornitore_id:   Optional[str] = None
    ordine_id:      Optional[str] = None
    azione_immediata: Optional[str] = None
    rilevato_da:    Optional[str] = None


class NCContenimento(BaseModel):
    azione_immediata:       str
    contenimento_operatore: Optional[str] = None


class NCAnalisi(BaseModel):
    metodo_analisi: str = "5why"        # 5why | ishikawa | fta | ai
    causa_radice:   Optional[str] = None
    domande_5why:   Optional[List[dict]] = None  # [{livello, domanda, risposta}]
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
#  HELPERS  (tutti scoped per hotel_id)
# ──────────────────────────────────────────────────────────────────

def _require_sb():
    sb = get_supabase()
    if not sb:
        raise HTTPException(503, "Database non configurato")
    return sb


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _get_nc(sb, nc_id: str, hotel_id: str) -> dict:
    """Recupera una NC SOLO se appartiene all'hotel dell'utente (altrimenti 404)."""
    res = (sb.table("non_conformita").select("*")
           .eq("id", nc_id).eq("hotel_id", hotel_id).execute())
    rows = res.data or []
    if not rows:
        raise HTTPException(404, f"NC {nc_id} non trovata")
    return rows[0]


def _log(sb, nc_id: str, hotel_id: str, stato_da, stato_a: str, azione: str, operatore: str = ""):
    sb.table("nc_log").insert({
        "nc_id": nc_id, "hotel_id": hotel_id, "stato_da": stato_da,
        "stato_a": stato_a, "azione": azione, "operatore": operatore, "ts": _now()
    }).execute()


def _cambia_stato(sb, nc_id: str, hotel_id: str, nuovo_stato: str, operatore: str = "", extra: dict = None):
    nc = _get_nc(sb, nc_id, hotel_id)         # verifica proprietà PRIMA di mutare
    stato_attuale = nc["stato"]

    if nuovo_stato not in TRANSIZIONI_VALIDE.get(stato_attuale, []):
        raise HTTPException(400,
            f"Transizione non ammessa: {stato_attuale} → {nuovo_stato}. "
            f"Ammesse: {TRANSIZIONI_VALIDE[stato_attuale]}")

    update_data = {"stato": nuovo_stato, **(extra or {})}
    (sb.table("non_conformita").update(update_data)
       .eq("id", nc_id).eq("hotel_id", hotel_id).execute())
    _log(sb, nc_id, hotel_id, stato_attuale, nuovo_stato,
         f"Cambio stato: {stato_attuale}→{nuovo_stato}", operatore)
    return nc


def _genera_numero(sb, hotel_id: str) -> str:
    """Numero NC progressivo per hotel e mese: NC-YYYY-MM-NNNN."""
    now = datetime.now(timezone.utc)
    prefix = f"NC-{now:%Y-%m}"
    res = sb.table("non_conformita").select("numero_nc").eq("hotel_id", hotel_id).execute()
    n = sum(1 for r in (res.data or []) if str(r.get("numero_nc") or "").startswith(prefix)) + 1
    return f"{prefix}-{n:04d}"


# ──────────────────────────────────────────────────────────────────
#  ENDPOINT 1: APERTURA NC
# ──────────────────────────────────────────────────────────────────

@router.post("", summary="Apre una nuova Non Conformità")
async def apri_nc(payload: NCApertura, user: UserProfile = Depends(require_user)):
    """Crea la NC in stato 'aperta' per l'hotel dell'utente. Numero NC generato lato server."""
    sb = _require_sb()
    return _crea_nc(sb, user.hotel_id, payload)


def _crea_nc(sb, hotel_id: str, payload: NCApertura) -> dict:
    data = {k: v for k, v in payload.dict().items() if v is not None}
    data["hotel_id"]   = hotel_id
    data["stato"]      = "aperta"
    data["numero_nc"]  = _genera_numero(sb, hotel_id)
    data["rilevato_at"] = _now()

    res = sb.table("non_conformita").insert(data).execute()
    if not res.data:
        raise HTTPException(400, "Errore creazione NC")

    nc = res.data[0]
    _log(sb, nc["id"], hotel_id, None, "aperta", "NC aperta", payload.rilevato_da or "")
    sla = SLA_ORE.get(payload.gravita, 72)
    return {
        "ok": True,
        "nc_id":      nc["id"],
        "numero_nc":  nc.get("numero_nc"),
        "stato":      nc["stato"],
        "sla_ore":    sla,
        "messaggio":  f"NC {nc.get('numero_nc')} aperta. SLA: {sla}h",
    }


# ──────────────────────────────────────────────────────────────────
#  ENDPOINT 2: CONTENIMENTO IMMEDIATO (8D: D3)
# ──────────────────────────────────────────────────────────────────

@router.put("/{nc_id}/contenimento", summary="Registra azione di contenimento immediato")
async def registra_contenimento(nc_id: str, payload: NCContenimento,
                                 user: UserProfile = Depends(require_user)):
    sb = _require_sb()
    _cambia_stato(sb, nc_id, user.hotel_id, "in_contenimento",
                  payload.contenimento_operatore or "",
                  {"azione_immediata": payload.azione_immediata,
                   "contenimento_operatore": payload.contenimento_operatore,
                   "contenimento_at": _now()})
    return {"ok": True, "stato": "in_contenimento", "azione": payload.azione_immediata}


# ──────────────────────────────────────────────────────────────────
#  ENDPOINT 3: ANALISI CAUSA RADICE (con AI opzionale) (8D: D4)
# ──────────────────────────────────────────────────────────────────

@router.put("/{nc_id}/analisi", summary="Registra analisi causa radice (opzionale: AI)")
async def registra_analisi(nc_id: str, payload: NCAnalisi,
                           user: UserProfile = Depends(require_user)):
    sb = _require_sb()
    nc = _get_nc(sb, nc_id, user.hotel_id)     # verifica proprietà
    analisi_ai_text = None

    # Salva i 5-Why se forniti (scoped per hotel)
    if payload.domande_5why:
        for item in payload.domande_5why:
            sb.table("nc_azioni_5why").insert({
                "nc_id": nc_id,
                "hotel_id": user.hotel_id,
                "livello": item.get("livello", 1),
                "domanda": item.get("domanda", ""),
                "risposta": item.get("risposta", ""),
            }).execute()

    if payload.usa_ai:
        analisi_ai_text = await _ai_root_cause(nc, payload)

    _cambia_stato(sb, nc_id, user.hotel_id, "in_analisi", "", {
        "metodo_analisi": payload.metodo_analisi,
        "causa_radice":   payload.causa_radice,
        "analisi_ai":     analisi_ai_text,
        "analisi_at":     _now(),
    })
    return {"ok": True, "stato": "in_analisi",
            "causa_radice": payload.causa_radice, "analisi_ai": analisi_ai_text}


async def _ai_root_cause(nc: dict, payload: NCAnalisi) -> str:
    """Chiama Claude per analisi causa radice e suggerimento azioni correttive."""
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        return None
    client = anthropic.Anthropic(api_key=api_key)

    why_testo = ""
    if payload.domande_5why:
        righe = [f"  Why {w.get('livello','?')}: {w.get('domanda','')} → {w.get('risposta','...')}"
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

    try:
        msg = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=600,
            messages=[{"role": "user", "content": prompt}],
        )
        return msg.content[0].text if msg.content else ""
    except Exception:
        return None


# ──────────────────────────────────────────────────────────────────
#  ENDPOINT 4: PIANO AZIONE CORRETTIVA (8D: D5-D6)
# ──────────────────────────────────────────────────────────────────

@router.put("/{nc_id}/piano-ac", summary="Assegna piano di azione correttiva")
async def assegna_piano_ac(nc_id: str, payload: NCPianoAC,
                           user: UserProfile = Depends(require_user)):
    sb = _require_sb()
    _cambia_stato(sb, nc_id, user.hotel_id, "in_corso", payload.responsabile_ac, {
        "azione_correttiva":  payload.azione_correttiva,
        "responsabile_ac":    payload.responsabile_ac,
        "scadenza_ac":        payload.scadenza_ac.isoformat(),
        "ac_avviata_at":      _now(),
    })
    return {"ok": True, "stato": "in_corso", "responsabile": payload.responsabile_ac,
            "scadenza": payload.scadenza_ac.isoformat(), "azione": payload.azione_correttiva}


# ──────────────────────────────────────────────────────────────────
#  ENDPOINT 5: VERIFICA EFFICACIA (8D: D7)
# ──────────────────────────────────────────────────────────────────

@router.put("/{nc_id}/verifica", summary="Registra verifica efficacia azione correttiva")
async def verifica_efficacia(nc_id: str, payload: NCVerifica,
                             user: UserProfile = Depends(require_user)):
    """D7: registra l'esito della verifica (da 'in_corso' a 'in_verifica').
    - efficace=True  → resta 'in_verifica', pronta per la chiusura formale (/chiudi, D8)
    - efficace=False → torna 'in_corso' per rivedere il piano d'azione
    """
    sb = _require_sb()
    op = payload.verifica_operatore or ""
    extra = {
        "verifica_descrizione": payload.verifica_descrizione,
        "verifica_efficace":    payload.verifica_efficace,
        "verifica_at":          _now(),
        "verifica_operatore":   payload.verifica_operatore,
    }
    if payload.lezione_appresa:
        extra["lezione_appresa"] = payload.lezione_appresa

    # D7: in_corso → in_verifica (registra la verifica)
    _cambia_stato(sb, nc_id, user.hotel_id, "in_verifica", op, extra)

    if payload.verifica_efficace:
        return {"ok": True, "stato": "in_verifica",
                "esito": "Verifica superata — pronta per la chiusura formale (/chiudi)"}

    # non efficace → rientra in lavorazione
    _cambia_stato(sb, nc_id, user.hotel_id, "in_corso", op, {})
    return {"ok": True, "stato": "in_corso",
            "esito": "Azione non efficace — revisione piano richiesta"}


# ──────────────────────────────────────────────────────────────────
#  ENDPOINT 6: CHIUSURA FORMALE (8D: D8)
# ──────────────────────────────────────────────────────────────────

@router.put("/{nc_id}/chiudi", summary="Chiusura formale NC con lezione appresa")
async def chiudi_nc(nc_id: str, payload: NCChiusura,
                    user: UserProfile = Depends(require_user)):
    sb = _require_sb()
    _cambia_stato(sb, nc_id, user.hotel_id, "chiusa", payload.chiusa_da or "", {
        "lezione_appresa": payload.lezione_appresa,
        "chiusa_da":       payload.chiusa_da,
        "chiusa_at":       _now(),
    })
    return {"ok": True, "stato": "chiusa", "messaggio": "NC chiusa e documentata ✓"}


# ──────────────────────────────────────────────────────────────────
#  QUERY E DASHBOARD  (sempre filtrate per hotel dell'utente)
# ──────────────────────────────────────────────────────────────────

@router.get("", summary="Lista NC con filtri")
async def lista_nc(
    user:       UserProfile = Depends(require_user),
    stato:      Optional[str] = None,
    area:       Optional[str] = None,
    gravita:    Optional[str] = None,
    aperte:     bool = False,
    limit:      int  = Query(50, le=200),
):
    sb = get_supabase()
    if not sb:
        return {"nc": [], "totale": 0}

    q = sb.table("non_conformita").select("*").eq("hotel_id", user.hotel_id)
    if stato:
        q = q.eq("stato", stato)
    if area:
        q = q.eq("area", area)
    if gravita:
        q = q.eq("gravita", gravita)

    rows = (q.order("rilevato_at", desc=True).limit(limit).execute().data) or []
    if aperte:
        rows = [r for r in rows if r.get("stato") not in ("chiusa", "annullata")]
    return {"nc": rows, "totale": len(rows)}


@router.get("/dashboard", summary="📊 KPI Non Conformità")
async def dashboard_nc(user: UserProfile = Depends(require_user)):
    sb = get_supabase()
    if not sb:
        return {"kpi": {}, "timeline": []}

    h = user.hotel_id
    tutte = (sb.table("non_conformita").select(
        "numero_nc, stato, area, gravita, titolo, ricorrente, rilevato_at, chiusa_at, scadenza_ac"
    ).eq("hotel_id", h).execute().data) or []

    aperte   = [n for n in tutte if n.get("stato") not in ("chiusa", "annullata")]
    critiche = [n for n in aperte if n.get("gravita") == "critica"]
    ricorr   = sum(1 for n in tutte if n.get("ricorrente"))

    per_area = {}
    for n in aperte:
        per_area[n.get("area", "—")] = per_area.get(n.get("area", "—"), 0) + 1

    # SLA scaduti
    sla_scaduti = 0
    for n in aperte:
        sla = SLA_ORE.get(n.get("gravita"), 72)
        if n.get("rilevato_at"):
            try:
                apertura = datetime.fromisoformat(str(n["rilevato_at"]).replace("Z", "+00:00"))
                delta_h = (datetime.now(timezone.utc) - apertura).total_seconds() / 3600
                if delta_h > sla:
                    sla_scaduti += 1
            except Exception:
                pass

    # Tempo medio chiusura (ore)
    tempi = []
    for n in tutte:
        if n.get("stato") == "chiusa" and n.get("chiusa_at") and n.get("rilevato_at"):
            try:
                ap = datetime.fromisoformat(str(n["rilevato_at"]).replace("Z", "+00:00"))
                ch = datetime.fromisoformat(str(n["chiusa_at"]).replace("Z", "+00:00"))
                tempi.append((ch - ap).total_seconds() / 3600)
            except Exception:
                pass

    # Timeline ultime aperture (per la card "ULTIME APERTURE")
    ordinate = sorted(tutte, key=lambda n: str(n.get("rilevato_at") or ""), reverse=True)
    timeline = [{
        "data":    (str(n.get("rilevato_at"))[:16].replace("T", " ")),
        "area":    n.get("area"),
        "titolo":  n.get("titolo"),
        "gravita": n.get("gravita"),
    } for n in ordinate[:6]]

    return {
        "kpi": {
            "totale_nc":           len(tutte),
            "nc_aperte":           len(aperte),
            "nc_critiche_aperte":  len(critiche),
            "sla_scaduti":         sla_scaduti,
            "nc_ricorrenti":       ricorr,
            "per_area":            per_area,
            "tempo_medio_chiusura_ore": round(sum(tempi) / len(tempi), 1) if tempi else None,
            "tasso_chiusura_pct":  round(
                sum(1 for n in tutte if n.get("stato") == "chiusa") / len(tutte) * 100, 1
            ) if tutte else 100,
        },
        "timeline": timeline,
    }


@router.get("/{nc_id}", summary="Dettaglio NC con log e 5-Why")
async def dettaglio_nc(nc_id: str, user: UserProfile = Depends(require_user)):
    sb = _require_sb()
    nc  = _get_nc(sb, nc_id, user.hotel_id)    # 404 se non è del tuo hotel
    log = (sb.table("nc_log").select("*").eq("nc_id", nc_id)
           .eq("hotel_id", user.hotel_id).order("ts").execute().data) or []
    why = (sb.table("nc_azioni_5why").select("*").eq("nc_id", nc_id)
           .eq("hotel_id", user.hotel_id).order("livello").execute().data) or []
    return {"nc": nc, "log": log, "5why": why}


@router.delete("/{nc_id}/annulla", summary="Annulla NC (falso positivo)")
async def annulla_nc(nc_id: str, motivo: str = "Falso positivo",
                     user: UserProfile = Depends(require_user)):
    sb = _require_sb()
    _cambia_stato(sb, nc_id, user.hotel_id, "annullata", "", {"note_annullamento": motivo})
    return {"ok": True, "stato": "annullata"}


# ──────────────────────────────────────────────────────────────────
#  INTEGRAZIONE: NC automatica da alert HACCP
#  (l'hotel_id viene SEMPRE dal token, mai dal chiamante esterno)
# ──────────────────────────────────────────────────────────────────

@router.post("/from-haccp", summary="Apre NC automatica da alert temperatura HACCP",
             include_in_schema=False)
async def nc_da_haccp(sensor_id: str, zona: str, temperatura: float,
                      temp_min: float, temp_max: float, severity: str,
                      haccp_temp_id: Optional[str] = None,
                      user: UserProfile = Depends(require_user)):
    sb = _require_sb()
    payload = NCApertura(
        area="haccp",
        gravita="critica" if severity == "critical" else "alta",
        titolo=f"Temperatura fuori range — {zona.replace('_', ' ')}",
        descrizione=(
            f"Zona: {zona} | Temperatura rilevata: {temperatura}°C | "
            f"Range ammesso: {temp_min}–{temp_max}°C | Sensor: {sensor_id}"
        ),
        azione_immediata=f"Verificare immediatamente {zona} e spostare prodotti se necessario",
        haccp_temp_id=haccp_temp_id,
        rilevato_da="sistema_iot",
    )
    return _crea_nc(sb, user.hotel_id, payload)
