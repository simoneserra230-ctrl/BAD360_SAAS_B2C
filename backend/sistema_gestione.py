"""
BAD360.ai — Sistema di Gestione Integrato ISO (Quality Manager · niche QM-ISO)

Porta nella suite l'ARCHITETTURA di un sistema di gestione ISO (HLS): i ~23 processi standard
(9001 qualità · 14001 ambiente · 45001 sicurezza · 37001 anticorruzione · + HACCP), il loro stato di
adozione per la struttura, la readiness verso la certificazione, e una bozza AI di procedura/politica.
Complementa `cert_api` (certificati) e `non_conformita` (NC/AC): qui si governa IL SISTEMA, non i singoli pezzi.

Deriva dalla mappa processi reale di un SGI certificato (de-brandizzata). Human-in-the-loop: le bozze AI
vanno validate da un consulente qualità.

Sicurezza: hotel_id SEMPRE dal token. Tabelle: sgi_config + sgi_stato.
"""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from backend.database import get_supabase
from backend.auth import require_user, UserProfile
from backend.roles import require_module

router = APIRouter(prefix="/api/sgi", tags=["Sistema di Gestione ISO"], dependencies=[Depends(require_module("sgi"))])
DISCLAIMER = "⚠️ Bozza generata dall'AI — il sistema di gestione va adattato e validato da un consulente qualità sulla realtà della struttura."

# Mappa HLS (High Level Structure) dei processi di un sistema di gestione integrato.
# categoria = clausola HLS ISO; norme = a quali standard il processo è rilevante.
SGI_PROCESSI = [
    {"codice": "400", "nome": "Contesto dell'organizzazione", "categoria": "4. Contesto",
     "norme": ["9001", "14001", "45001", "37001"], "hint": "Analisi SWOT, parti interessate, Canvas"},
    {"codice": "530", "nome": "Ruoli, responsabilità e autorità", "categoria": "5. Leadership",
     "norme": ["9001", "14001", "45001", "37001"], "hint": "Organigramma, deleghe; + prevenzione corruzione/whistleblowing"},
    {"codice": "610", "nome": "Valutazione dei rischi e delle opportunità", "categoria": "6. Pianificazione",
     "norme": ["9001", "14001", "45001", "37001"], "hint": "Risk assessment (anche rischio corruzione)"},
    {"codice": "613", "nome": "Prescrizioni normative e autorizzative", "categoria": "6. Pianificazione",
     "norme": ["14001", "45001"], "hint": "Censimento normative + pianificazione adempimenti"},
    {"codice": "620", "nome": "Obiettivi e indicatori", "categoria": "6. Pianificazione",
     "norme": ["9001", "14001", "45001", "37001"], "hint": "Obiettivi misurabili + KPI"},
    {"codice": "630", "nome": "Pianificazione delle modifiche", "categoria": "6. Pianificazione",
     "norme": ["9001"], "hint": "Change management"},
    {"codice": "710", "nome": "Gestione delle risorse", "categoria": "7. Supporto",
     "norme": ["9001", "45001"], "hint": "Selezione/formazione personale, infrastrutture"},
    {"codice": "720", "nome": "Sviluppo delle competenze", "categoria": "7. Supporto",
     "norme": ["9001"], "hint": "Formazione e addestramento"},
    {"codice": "740", "nome": "Gestione della comunicazione", "categoria": "7. Supporto",
     "norme": ["9001", "14001", "45001"], "hint": "Comunicazioni interne/esterne"},
    {"codice": "750", "nome": "Informazione documentata", "categoria": "7. Supporto",
     "norme": ["9001", "14001", "45001", "37001"], "hint": "Gestione documentale, versioning, copie controllate"},
    {"codice": "810", "nome": "Controllo operativo", "categoria": "8. Operatività",
     "norme": ["9001", "14001", "45001"], "hint": "Esecuzione controllata dei processi"},
    {"codice": "820", "nome": "Gestione commerciale", "categoria": "8. Operatività",
     "norme": ["9001"], "hint": "Offerta, contratti, riesame requisiti cliente"},
    {"codice": "830", "nome": "Progettazione e sviluppo", "categoria": "8. Operatività",
     "norme": ["9001"], "hint": "Piano, input, riesame, verifica, validazione (5 controlli)"},
    {"codice": "840", "nome": "Valutazione dei fornitori", "categoria": "8. Operatività",
     "norme": ["9001", "37001"], "hint": "Albo fornitori, due diligence, soci in affari"},
    {"codice": "850", "nome": "Erogazione del servizio", "categoria": "8. Operatività",
     "norme": ["9001"], "hint": "Il core: erogazione controllata (per l'hotel: F&B, camere, eventi)"},
    {"codice": "820A", "nome": "Gestione delle emergenze", "categoria": "8. Operatività",
     "norme": ["45001"], "hint": "Piano emergenza, squadra, prove"},
    {"codice": "HACCP", "nome": "Autocontrollo alimentare (HACCP)", "categoria": "8. Operatività",
     "norme": ["haccp"], "hint": "Piano HACCP, CCP, monitoraggi (vedi modulo HACCP)"},
    {"codice": "910", "nome": "Monitoraggio, misurazione e analisi", "categoria": "9. Valutazione prestazioni",
     "norme": ["9001", "14001", "45001", "37001"], "hint": "Indicatori, soddisfazione cliente"},
    {"codice": "920", "nome": "Audit interni", "categoria": "9. Valutazione prestazioni",
     "norme": ["9001", "14001", "45001", "37001"], "hint": "Programma audit + rapporti"},
    {"codice": "930", "nome": "Riesame della direzione", "categoria": "9. Valutazione prestazioni",
     "norme": ["9001", "14001", "45001", "37001"], "hint": "Riesame periodico degli input/output SGI"},
    {"codice": "1020", "nome": "Non conformità e azioni correttive", "categoria": "10. Miglioramento",
     "norme": ["9001", "14001", "45001", "37001"], "hint": "NC/AC + verifica efficacia (vedi modulo NC)"},
    {"codice": "1030", "nome": "Miglioramento continuo", "categoria": "10. Miglioramento",
     "norme": ["9001", "14001", "45001", "37001"], "hint": "Piano di miglioramento"},
]

NORME_LABEL = {"9001": "ISO 9001 Qualità", "14001": "ISO 14001 Ambiente", "45001": "ISO 45001 Sicurezza",
               "37001": "ISO 37001 Anticorruzione", "haccp": "HACCP Alimentare"}
STATI = {"da_avviare", "in_corso", "attivo", "da_riesaminare"}


def _sb():
    sb = get_supabase()
    if not sb:
        raise HTTPException(503, "Database non configurato")
    return sb


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Config(BaseModel):
    norme: list = []   # sottoinsieme di 9001/14001/45001/37001/haccp che la struttura persegue


@router.get("/config", summary="Norme perseguite dalla struttura")
async def get_config(user: UserProfile = Depends(require_user)):
    sb = _sb()
    rows = (sb.table("sgi_config").select("*").eq("hotel_id", user.hotel_id).execute().data) or []
    norme = rows[0].get("norme") if rows else None
    if isinstance(norme, str):
        norme = [n for n in norme.split(",") if n]
    return {"ok": True, "norme": norme or ["9001"], "norme_disponibili": NORME_LABEL}


@router.put("/config", summary="Imposta le norme perseguite")
async def set_config(payload: Config, user: UserProfile = Depends(require_user)):
    sb = _sb()
    norme = [n for n in (payload.norme or []) if n in NORME_LABEL] or ["9001"]
    data = {"hotel_id": user.hotel_id, "norme": ",".join(norme), "updated_at": _now()}
    exist = (sb.table("sgi_config").select("hotel_id").eq("hotel_id", user.hotel_id).execute().data) or []
    if exist:
        sb.table("sgi_config").update(data).eq("hotel_id", user.hotel_id).execute()
    else:
        sb.table("sgi_config").insert(data).execute()
    return {"ok": True, "norme": norme}


class StatoBody(BaseModel):
    processo_codice: str
    stato: str
    responsabile: Optional[str] = None
    note: Optional[str] = None


@router.put("/stato", summary="Aggiorna lo stato di adozione di un processo")
async def set_stato(payload: StatoBody, user: UserProfile = Depends(require_user)):
    if payload.processo_codice not in {p["codice"] for p in SGI_PROCESSI}:
        raise HTTPException(400, "Processo sconosciuto")
    if payload.stato not in STATI:
        raise HTTPException(400, f"Stato non valido. Ammessi: {sorted(STATI)}")
    sb = _sb()
    data = {"hotel_id": user.hotel_id, "processo_codice": payload.processo_codice, "stato": payload.stato,
            "responsabile": (payload.responsabile or "").strip(), "note": (payload.note or "").strip(),
            "updated_at": _now()}
    exist = (sb.table("sgi_stato").select("id").eq("hotel_id", user.hotel_id)
             .eq("processo_codice", payload.processo_codice).execute().data) or []
    if exist:
        sb.table("sgi_stato").update(data).eq("hotel_id", user.hotel_id).eq("processo_codice", payload.processo_codice).execute()
    else:
        sb.table("sgi_stato").insert(data).execute()
    return {"ok": True}


def _norme_struttura(sb, hotel_id: str) -> list:
    rows = (sb.table("sgi_config").select("norme").eq("hotel_id", hotel_id).execute().data) or []
    norme = rows[0].get("norme") if rows else None
    if isinstance(norme, str):
        norme = [n for n in norme.split(",") if n]
    return norme or ["9001"]


@router.get("/mappa", summary="Mappa dei processi ISO applicabili + stato di adozione")
async def mappa(user: UserProfile = Depends(require_user)):
    sb = _sb()
    norme = set(_norme_struttura(sb, user.hotel_id))
    stat = (sb.table("sgi_stato").select("*").eq("hotel_id", user.hotel_id).execute().data) or []
    smap = {s["processo_codice"]: s for s in stat}
    out = []
    for p in SGI_PROCESSI:
        if not (set(p["norme"]) & norme):
            continue
        s = smap.get(p["codice"], {})
        out.append({**p, "stato": s.get("stato", "da_avviare"), "responsabile": s.get("responsabile", ""),
                    "note": s.get("note", "")})
    return {"ok": True, "norme": sorted(norme), "processi": out, "totale": len(out)}


@router.get("/dashboard", summary="Readiness del sistema di gestione")
async def dashboard(user: UserProfile = Depends(require_user)):
    r = await mappa(user)
    proc = r["processi"]
    tot = len(proc)
    def c(s): return sum(1 for p in proc if p["stato"] == s)
    attivi = c("attivo")
    return {"ok": True, "kpi": {
        "applicabili": tot, "attivi": attivi, "in_corso": c("in_corso"),
        "da_avviare": c("da_avviare"), "da_riesaminare": c("da_riesaminare"),
        "readiness_pct": round(attivi / tot * 100) if tot else 0,
    }, "norme": r["norme"]}


class BozzaBody(BaseModel):
    processo_codice: str
    tipo_struttura: str = "hotel"


@router.post("/ai/procedura", summary="Genera bozza di procedura per un processo")
async def ai_procedura(body: BozzaBody, user: UserProfile = Depends(require_user)):
    proc = next((p for p in SGI_PROCESSI if p["codice"] == body.processo_codice), None)
    if not proc:
        raise HTTPException(400, "Processo sconosciuto")
    prompt = (
        f"Sei un consulente qualità ISO per l'ospitalità. Redigi una BOZZA sintetica di PROCEDURA per il "
        f"processo '{proc['nome']}' (clausola {proc['categoria']}, norme {', '.join(proc['norme'])}) di una "
        f"struttura ricettiva ({body.tipo_struttura}). Struttura: Scopo, Campo di applicazione, Responsabilità, "
        f"Modalità operative (punti), Registrazioni/Moduli, Indicatori. Concisa, pratica, in italiano. "
        f"Usa [DA ADATTARE] dove servono dati della struttura."
    )
    ai = None
    try:
        from backend.ai_agents import _ask_claude
        ai = await _ask_claude(prompt, max_tokens=900)
    except Exception:
        ai = None
    return {"ok": True, "processo": proc["nome"], "bozza": (ai or "").strip() or "[AI non disponibile — configura ANTHROPIC_API_KEY]",
            "disclaimer": DISCLAIMER}
