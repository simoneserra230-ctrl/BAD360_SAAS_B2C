"""
BAD360.ai — Compliance Radar (niche C2, l'ombrello del cluster compliance)

Dato il PROFILO della struttura (tipo, camere, posti letto, regione, dipendenti, cucina,
piscina), elenca gli OBBLIGHI applicabili + scadenze + stato + HINT verso BA.IA (bandi per
finanziare gli interventi) e Academy/SSFormazione (formazione obbligatoria).
È un RADAR/guida: human-in-the-loop, scadenze indicative → verifica su fonte ufficiale.

Sicurezza: hotel_id dal token. Tabelle: compliance_profile + compliance_status.
"""
from __future__ import annotations
from datetime import date, datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from backend.database import get_supabase
from backend.auth import require_user, UserProfile

router = APIRouter(prefix="/api/compliance", tags=["Compliance Radar"])
ALERT_DAYS = 90

# Knowledge base obblighi (curata, INDICATIVA — verifica su fonte ufficiale).
# applies: condizioni AND. Chiavi: sempre, min_camere, min_posti_letto, min_dipendenti, cucina, piscina, vende_online.
COMPLIANCE_RULES = [
    {"key": "cin", "titolo": "CIN — Codice Identificativo Nazionale (BDSR)", "categoria": "turismo",
     "norma": "L. 191/2024 / DL 145/2023", "periodicita": "una_tantum",
     "scadenza_nota": "Obbligatorio dal nov 2024 (sanzioni dal gen 2025); tenere aggiornato",
     "fonte": "Ministero del Turismo — BDSR", "applies": {"sempre": True}},
    {"key": "alloggiati", "titolo": "Comunicazione alloggiati alla Questura", "categoria": "ordine_pubblico",
     "norma": "Art. 109 TULPS", "periodicita": "ricorrente (ogni arrivo, entro 24h)",
     "scadenza_nota": "Adempimento continuo ad ogni check-in", "fonte": "Alloggiati Web - Polizia di Stato",
     "applies": {"sempre": True}},
    {"key": "istat", "titolo": "Comunicazione flussi turistici ISTAT", "categoria": "turismo",
     "norma": "Rilevazioni regionali", "periodicita": "ricorrente (mensile)",
     "scadenza_nota": "Invio periodico sul portale regionale (Ross1000/Sinfonia/Turismo5…)",
     "fonte": "Portale turistico regionale", "applies": {"sempre": True}},
    {"key": "imposta_soggiorno", "titolo": "Imposta di soggiorno (riscossione + rendiconto)", "categoria": "fiscale",
     "norma": "Regolamento comunale", "periodicita": "ricorrente",
     "scadenza_nota": "Dove istituita dal Comune: riscossione + dichiarazione/versamento periodico",
     "fonte": "Comune", "applies": {"sempre": True}},
    {"key": "scia_antincendio", "titolo": "SCIA antincendio", "categoria": "antincendio",
     "norma": "DPR 151/2011 / DM 9.4.1994", "periodicita": "una_tantum + rinnovo",
     "scadenza_nota": "SCIA antincendio (struttura >25 p.l.); verifica scadenze e proroghe",
     "fonte": "VVF / SUAP", "applies": {"min_posti_letto": 25},
     "formazione_hint": "Corso addetto antincendio", "bando_hint": "Bandi sicurezza/antincendio"},
    {"key": "cpi_adeguamento", "titolo": "Adeguamento prevenzione incendi (RTV ricettive)", "categoria": "antincendio",
     "norma": "DM 9.8.2016 e proroghe", "periodicita": "scadenza fissa",
     "scadenza_nota": "Adeguamento RTV entro 31/12/2026 (controlli biennali >50 p.l.)",
     "fonte": "VVF", "applies": {"min_posti_letto": 25}, "bando_hint": "Bandi adeguamento sicurezza"},
    {"key": "metering_energia", "titolo": "Sistemi di rilevamento consumi energia/acqua", "categoria": "energia",
     "norma": "D.Lgs 199/2021 (attuativo)", "periodicita": "una_tantum (impianto)",
     "scadenza_nota": "Obbligo metering per hotel oltre ~20 camere (dal 2025)",
     "fonte": "GSE / decreto attuativo", "applies": {"min_camere": 20},
     "bando_hint": "Efficienza energetica / Transizione 5.0"},
    {"key": "iso14001_emas", "titolo": "Piano gestione ambientale (ISO 14001 / EMAS)", "categoria": "ambiente",
     "norma": "Norma di settore", "periodicita": "certificazione + mantenimento",
     "scadenza_nota": "Per hotel oltre ~50 camere (dal 1/7/2025): piano ambientale certificabile",
     "fonte": "Ente di certificazione", "applies": {"min_camere": 50},
     "bando_hint": "Certificazione ambientale / green"},
    {"key": "haccp", "titolo": "Autocontrollo HACCP", "categoria": "sicurezza_alimentare",
     "norma": "Reg. CE 852/2004", "periodicita": "continuo + formazione",
     "scadenza_nota": "Piano di autocontrollo + monitoraggi (vedi modulo HACCP)",
     "fonte": "ASL", "applies": {"cucina": True}, "formazione_hint": "Corso HACCP"},
    {"key": "gdpr", "titolo": "Privacy dati ospiti (GDPR)", "categoria": "privacy",
     "norma": "Reg. UE 2016/679", "periodicita": "continuo",
     "scadenza_nota": "Informativa, registro trattamenti, misure; dati ospite sono sensibili",
     "fonte": "Garante Privacy", "applies": {"sempre": True}},
    {"key": "eaa", "titolo": "Accessibilità sito/booking (European Accessibility Act)", "categoria": "digitale",
     "norma": "Dir. UE 2019/882 (EAA)", "periodicita": "continuo",
     "scadenza_nota": "Dal giu 2025 siti/booking accessibili (WCAG 2.1 AA); esenti micro <10 dip — vedi modulo EAA",
     "fonte": "EN 301 549", "applies": {"sempre": True}},
    {"key": "whistleblowing", "titolo": "Canale whistleblowing", "categoria": "governance",
     "norma": "D.Lgs 24/2023", "periodicita": "una_tantum (canale attivo)",
     "scadenza_nota": "Obbligatorio per ≥50 dipendenti (o Modello 231)",
     "fonte": "ANAC", "applies": {"min_dipendenti": 50}},
    {"key": "formazione_sicurezza", "titolo": "Formazione sicurezza lavoro (D.Lgs 81/08)", "categoria": "sicurezza_lavoro",
     "norma": "D.Lgs 81/2008 / Accordo Stato-Regioni", "periodicita": "aggiornamento (5 anni)",
     "scadenza_nota": "Formazione lavoratori/preposti/dirigenti + aggiornamenti periodici",
     "fonte": "Accordo SR", "applies": {"min_dipendenti": 1}, "formazione_hint": "Corsi sicurezza 81/08 (SSFormazione)"},
    {"key": "rinnovo_formazione", "titolo": "Rinnovo formazione (antincendio/HACCP/primo soccorso)", "categoria": "formazione",
     "norma": "Varie", "periodicita": "ogni 2-3 anni",
     "scadenza_nota": "Aggiornamento periodico degli attestati del personale",
     "fonte": "—", "applies": {"sempre": True}, "formazione_hint": "Academy / SSFormazione"},
]


def _sb():
    sb = get_supabase()
    if not sb:
        raise HTTPException(503, "Database non configurato")
    return sb


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _applies(rule: dict, p: dict) -> bool:
    cond = rule.get("applies", {})
    if cond.get("sempre"):
        return True
    if "min_camere" in cond and (p.get("n_camere") or 0) < cond["min_camere"]:
        return False
    if "min_posti_letto" in cond and (p.get("n_posti_letto") or 0) < cond["min_posti_letto"]:
        return False
    if "min_dipendenti" in cond and (p.get("n_dipendenti") or 0) < cond["min_dipendenti"]:
        return False
    if cond.get("cucina") and not p.get("cucina"):
        return False
    if cond.get("piscina") and not p.get("piscina"):
        return False
    return True


def _stato(fatto: bool, scadenza) -> tuple:
    if scadenza:
        try:
            d = date.fromisoformat(str(scadenza)[:10])
            g = (d - date.today()).days
            if g < 0:
                return "scaduto", g
            if g <= ALERT_DAYS:
                return "in_scadenza", g
            return "ok", g
        except ValueError:
            pass
    return ("ok", None) if fatto else ("da_fare", None)


class Profilo(BaseModel):
    tipo_struttura: Optional[str] = "hotel"   # hotel | b&b | agriturismo | casa_vacanza | ristorante | bar
    n_camere:       int = 0
    n_posti_letto:  int = 0
    regione:        Optional[str] = None
    n_dipendenti:   int = 0
    cucina:         bool = False
    piscina:        bool = False


@router.get("/profile", summary="Profilo struttura (admin)")
async def get_profile(user: UserProfile = Depends(require_user)):
    sb = _sb()
    rows = (sb.table("compliance_profile").select("*").eq("hotel_id", user.hotel_id).execute().data) or []
    return {"ok": True, "profile": rows[0] if rows else None}


@router.put("/profile", summary="Imposta profilo struttura")
async def set_profile(payload: Profilo, user: UserProfile = Depends(require_user)):
    sb = _sb()
    data = {"hotel_id": user.hotel_id, "tipo_struttura": payload.tipo_struttura,
            "n_camere": int(payload.n_camere or 0), "n_posti_letto": int(payload.n_posti_letto or 0),
            "regione": (payload.regione or "").strip(), "n_dipendenti": int(payload.n_dipendenti or 0),
            "cucina": bool(payload.cucina), "piscina": bool(payload.piscina), "updated_at": _now()}
    exist = (sb.table("compliance_profile").select("hotel_id").eq("hotel_id", user.hotel_id).execute().data) or []
    if exist:
        sb.table("compliance_profile").update(data).eq("hotel_id", user.hotel_id).execute()
    else:
        sb.table("compliance_profile").insert(data).execute()
    return {"ok": True, "profile": data}


class StatusBody(BaseModel):
    obbligo_key:      str
    fatto:            bool = False
    data_adempimento: Optional[str] = None
    data_scadenza:    Optional[str] = None
    note:             Optional[str] = None


@router.put("/status", summary="Aggiorna stato di un obbligo")
async def set_status(payload: StatusBody, user: UserProfile = Depends(require_user)):
    if payload.obbligo_key not in {r["key"] for r in COMPLIANCE_RULES}:
        raise HTTPException(400, "Obbligo sconosciuto")
    sb = _sb()
    data = {"hotel_id": user.hotel_id, "obbligo_key": payload.obbligo_key, "fatto": bool(payload.fatto),
            "data_adempimento": payload.data_adempimento, "data_scadenza": payload.data_scadenza,
            "note": (payload.note or "").strip(), "updated_at": _now()}
    exist = (sb.table("compliance_status").select("id").eq("hotel_id", user.hotel_id)
             .eq("obbligo_key", payload.obbligo_key).execute().data) or []
    if exist:
        sb.table("compliance_status").update(data).eq("hotel_id", user.hotel_id).eq("obbligo_key", payload.obbligo_key).execute()
    else:
        sb.table("compliance_status").insert(data).execute()
    return {"ok": True}


@router.get("/radar", summary="Radar obblighi applicabili + stato + hint")
async def radar(user: UserProfile = Depends(require_user)):
    sb = _sb()
    prof = (sb.table("compliance_profile").select("*").eq("hotel_id", user.hotel_id).execute().data) or []
    p = prof[0] if prof else {}
    stat = (sb.table("compliance_status").select("*").eq("hotel_id", user.hotel_id).execute().data) or []
    smap = {s["obbligo_key"]: s for s in stat}
    out = []
    for r in COMPLIANCE_RULES:
        if not _applies(r, p):
            continue
        s = smap.get(r["key"], {})
        stato, giorni = _stato(s.get("fatto", False), s.get("data_scadenza"))
        out.append({**{k: r[k] for k in ("key", "titolo", "categoria", "norma", "periodicita", "scadenza_nota", "fonte")},
                    "bando_hint": r.get("bando_hint"), "formazione_hint": r.get("formazione_hint"),
                    "fatto": s.get("fatto", False), "data_scadenza": s.get("data_scadenza"),
                    "note": s.get("note"), "stato": stato, "giorni_alla_scadenza": giorni})
    ordine = {"scaduto": 0, "in_scadenza": 1, "da_fare": 2, "ok": 3}
    out.sort(key=lambda x: ordine.get(x["stato"], 9))
    return {"ok": True, "profilo_impostato": bool(prof), "obblighi": out, "totale": len(out)}


@router.get("/dashboard", summary="KPI compliance")
async def dashboard(user: UserProfile = Depends(require_user)):
    r = await radar(user)
    ob = r["obblighi"]
    def c(s): return sum(1 for o in ob if o["stato"] == s)
    return {"ok": True, "kpi": {
        "applicabili": len(ob), "scaduti": c("scaduto"), "in_scadenza": c("in_scadenza"),
        "da_fare": c("da_fare"), "ok": c("ok"),
        "con_bando": sum(1 for o in ob if o.get("bando_hint")),
        "con_formazione": sum(1 for o in ob if o.get("formazione_hint")),
    }, "profilo_impostato": r["profilo_impostato"]}
