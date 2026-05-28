"""
BAD.S Platform — Vendor Rating, SLA Manager, Partnership
Modelli Pydantic, costanti e funzioni di calcolo usate da main.py

Fonti:
  Vendor Rating: Cribis, Ivalua, OnlineProcurement, Gallo (Unibo)
  SLA: Deepser, EENA, Mainsim
  Partnership: Marenzi (UniPD), Teamwork Hospitality
"""

from __future__ import annotations
from datetime import date
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


# ══════════════════════════════════════════════════════════════════
#  VENDOR RATING — COSTANTI
# ══════════════════════════════════════════════════════════════════

VR_CLASSI: Dict[str, Dict] = {
    "A": {"label": "Strategic Partner",  "range": (90, 100), "colore": "#16a34a", "azione": "Rinnovo prioritario, partnership strategica"},
    "B": {"label": "Preferred Supplier", "range": (70,  89), "colore": "#2563eb", "azione": "Monitoraggio trimestrale, possibile upgrade"},
    "C": {"label": "Approved Supplier",  "range": (50,  69), "colore": "#d97706", "azione": "Piano di miglioramento 90 giorni"},
    "D": {"label": "At Risk",            "range": (0,   49), "colore": "#dc2626", "azione": "Audit urgente, piano emergenza fornitore alternativo"},
}

VR_AZIONI: Dict[str, str] = {
    "A": "Proporre accordo quadro pluriennale e preferenza acquisti",
    "B": "Pianificare review trimestrale e roadmap miglioramento",
    "C": "Emettere piano di miglioramento formale con KPI e scadenza 90gg",
    "D": "Attivare procedura di qualifica fornitore alternativo urgente",
}

# Pesi formula Vendor Rating (Cribis/Ivalua best practice)
VR_PESI = {
    "puntualita":  0.30,
    "qualita":     0.25,
    "prezzo":      0.20,
    "compliance":  0.15,
    "reattivita":  0.10,
}


# ══════════════════════════════════════════════════════════════════
#  SLA MANAGER — COSTANTI
# ══════════════════════════════════════════════════════════════════

SLA_DEFAULTS: Dict[str, Dict] = {
    "food_fresh": {
        "target_otd_pct": 97,   "target_otif_pct": 95,
        "target_qualita_pct": 99, "target_prezzo_var_pct": 2,
        "target_risposta_ore": 4,
        "penale_ritardo_pct": 2, "penale_nc_pct": 5,
        "note": "Fresco deperibile — tolleranza zero ritardi",
    },
    "beverage": {
        "target_otd_pct": 95,   "target_otif_pct": 93,
        "target_qualita_pct": 98, "target_prezzo_var_pct": 3,
        "target_risposta_ore": 8,
        "penale_ritardo_pct": 1.5, "penale_nc_pct": 3,
        "note": "Bevande — finestra consegna ± 1 giorno",
    },
    "chimici": {
        "target_otd_pct": 93,   "target_otif_pct": 90,
        "target_qualita_pct": 100, "target_prezzo_var_pct": 5,
        "target_risposta_ore": 24,
        "penale_ritardo_pct": 1, "penale_nc_pct": 10,
        "note": "Schede sicurezza MSDS obbligatorie ad ogni consegna",
    },
    "tessile": {
        "target_otd_pct": 95,   "target_otif_pct": 92,
        "target_qualita_pct": 97, "target_prezzo_var_pct": 3,
        "target_risposta_ore": 12,
        "penale_ritardo_pct": 1, "penale_nc_pct": 3,
        "note": "Biancheria — ciclo lavanderia incluso se contratto full service",
    },
    "manutenzione": {
        "target_otd_pct": 90,   "target_otif_pct": 88,
        "target_qualita_pct": 95, "target_prezzo_var_pct": 5,
        "target_risposta_ore": 2,
        "penale_ritardo_pct": 2, "penale_nc_pct": 5,
        "note": "Emergenze: SLA 2h intervento su impianti critici",
    },
    "tech": {
        "target_otd_pct": 92,   "target_otif_pct": 90,
        "target_qualita_pct": 98, "target_prezzo_var_pct": 4,
        "target_risposta_ore": 8,
        "penale_ritardo_pct": 1, "penale_nc_pct": 5,
        "note": "Uptime SLA separato per servizi cloud",
    },
}


# ══════════════════════════════════════════════════════════════════
#  PARTNERSHIP — COSTANTI
# ══════════════════════════════════════════════════════════════════

PARTNERSHIP_LIVELLI: Dict[str, Dict] = {
    "preferred": {
        "label": "Preferred Supplier",
        "soglia_rating": 70,
        "durata_mesi": 12,
        "benefici": [
            "Accesso anticipato a nuovi capitolati",
            "Condizioni di pagamento 60gg net",
            "Invito a fiere e showroom",
        ],
        "impegni": [
            "Report mensile consegne",
            "Aggiornamento certificazioni annuale",
        ],
        "colore": "#2563eb",
    },
    "strategic": {
        "label": "Strategic Partner",
        "soglia_rating": 85,
        "durata_mesi": 24,
        "benefici": [
            "Accordo quadro pluriennale",
            "Co-sviluppo nuovi prodotti",
            "Accesso dati forecast domanda",
            "Payment terms 90gg net",
        ],
        "impegni": [
            "Condivisione roadmap prodotti",
            "Partecipazione audit incrociati",
            "Formazione personale hotel",
        ],
        "colore": "#7c3aed",
    },
    "exclusive": {
        "label": "Exclusive Partner",
        "soglia_rating": 92,
        "durata_mesi": 36,
        "benefici": [
            "Esclusiva categoria per area geografica",
            "Investimenti co-marketing",
            "Revenue sharing su performance",
            "Integrazione EDI/API diretta",
        ],
        "impegni": [
            "SLA garantiti contrattualmente",
            "Certificazione ISO obbligatoria",
            "Business continuity plan condiviso",
        ],
        "colore": "#d97706",
    },
}


# ══════════════════════════════════════════════════════════════════
#  PYDANTIC MODELS
# ══════════════════════════════════════════════════════════════════

class VendorRatingManuale(BaseModel):
    fornitore_id: str
    periodo: str                     # "2026-03" o "2026-Q1"
    score_puntualita: float = Field(50, ge=0, le=100)
    score_qualita: float = Field(50, ge=0, le=100)
    score_prezzo: float = Field(50, ge=0, le=100)
    score_compliance: float = Field(50, ge=0, le=100)
    score_reattivita: float = Field(50, ge=0, le=100)
    note: Optional[str] = None


class VRKpiEventCreate(BaseModel):
    fornitore_id: str
    tipo_evento: str          # consegna | nc_aperta | nc_chiusa | prezzo_deviazione
    data_evento: Optional[str] = None
    ordine_id: Optional[str] = None
    valore: Optional[float] = None
    valore_atteso: Optional[float] = None
    conforme: bool = True
    note: Optional[str] = None


class SLAContractCreate(BaseModel):
    fornitore_id: str
    nome: str
    categoria: str
    data_inizio: str
    data_scadenza: str
    target_otd_pct: float = 95.0
    target_otif_pct: float = 92.0
    target_qualita_pct: float = 98.0
    target_prezzo_var_pct: float = 3.0
    target_risposta_ore: float = 24.0
    penale_ritardo_pct: float = 1.5
    penale_nc_pct: float = 3.0
    penale_max_mensile_pct: float = 10.0
    frequenza_review: str = "trimestrale"   # mensile | trimestrale | semestrale
    rinnovo_automatico: bool = True
    note_legali: Optional[str] = None
    note: Optional[str] = None


class SLAMeasurement(BaseModel):
    sla_id: str
    periodo: str
    n_ordini: int = 0
    n_ordini_puntuali: int = 0
    n_nc: int = 0
    otd_misurato_pct: Optional[float] = None
    otif_misurato_pct: Optional[float] = None
    qualita_misurata_pct: Optional[float] = None
    prezzo_var_misurata_pct: Optional[float] = None
    risposta_media_ore: Optional[float] = None
    note: Optional[str] = None


class SLAAlertUpdate(BaseModel):
    alert_id: str
    nuovo_stato: str    # in_gestione | chiuso
    note: Optional[str] = None


class PartnershipCreate(BaseModel):
    fornitore_id: str
    nome: str
    livello: str = "preferred"   # preferred | strategic | exclusive
    data_inizio: str
    data_scadenza: Optional[str] = None
    obiettivi: Optional[str] = None
    benefici_concordati: Optional[str] = None
    impegni_fornitore: Optional[str] = None
    note: Optional[str] = None


class PartnershipMeetingCreate(BaseModel):
    fornitore_id: str
    tipo: str = "review_trimestrale"
    data_pianificata: str
    ora: Optional[str] = None
    luogo: Optional[str] = None
    partecipanti_hotel: List[str] = []
    partecipanti_fornitore: List[str] = []
    agenda: Optional[str] = None
    note: Optional[str] = None


class PartnershipMeetingComplete(BaseModel):
    meeting_id: str
    esito: Optional[str] = "positivo"           # positivo | neutro | negativo
    action_items: List[str] = []
    verbale: Optional[str] = None
    score_al_momento: Optional[float] = None
    data_prossimo_meeting: Optional[str] = None


class ScorecardCompile(BaseModel):
    fornitore_id: str
    periodo: str
    direzione: str = "hotel_su_fornitore"       # hotel_su_fornitore | fornitore_su_hotel
    score_qualita: float = Field(50, ge=0, le=100)
    score_innovazione: float = Field(50, ge=0, le=100)
    score_sostenibilita: float = Field(50, ge=0, le=100)
    score_collaborazione: float = Field(50, ge=0, le=100)
    note: Optional[str] = None


# ══════════════════════════════════════════════════════════════════
#  FUNZIONI DI CALCOLO
# ══════════════════════════════════════════════════════════════════

def calcola_score_totale(
    puntualita: float,
    qualita: float,
    prezzo: float = 50.0,
    compliance: float = 50.0,
    reattivita: float = 50.0,
) -> float:
    """Formula ponderata Vendor Rating (Cribis/Ivalua best practice)"""
    score = (
        puntualita  * VR_PESI["puntualita"] +
        qualita     * VR_PESI["qualita"] +
        prezzo      * VR_PESI["prezzo"] +
        compliance  * VR_PESI["compliance"] +
        reattivita  * VR_PESI["reattivita"]
    )
    return round(score, 1)


def classifica_fornitore(score: float) -> Dict[str, str]:
    """Classifica il fornitore in A/B/C/D con azione raccomandata"""
    for classe, info in VR_CLASSI.items():
        lo, hi = info["range"]
        if lo <= score <= hi:
            return {
                "classe": classe,
                "label": info["label"],
                "colore": info["colore"],
                "azione": info["azione"],
            }
    return {"classe": "D", "label": "At Risk", "colore": "#dc2626", "azione": VR_AZIONI["D"]}


def calcola_score_compliance_cert(certificazioni: List[str]) -> float:
    """Calcola compliance score da elenco certificazioni del fornitore"""
    cert_pesi = {
        "ISO 22000": 30, "FSSC 22000": 30, "BRC": 25, "IFS": 25,
        "ISO 9001": 15,  "ISO 14001": 10,  "ISO 45001": 10,
        "HACCP": 20,     "Global GAP": 15, "UTZ": 5,
    }
    score = sum(cert_pesi.get(c, 5) for c in certificazioni)
    return min(round(score, 1), 100.0)


def calcola_sla_compliance(misurazione: Dict, targets: Dict) -> Dict:
    """
    Confronta misurazioni vs target SLA.
    Restituisce compliance_score, kpi_check, alerts e penali stimate.
    """
    kpi_check: Dict[str, Dict] = {}
    alerts: List[Dict] = []
    penali_basi = targets.get("penale_ritardo_pct", 1.5)
    penali_nc   = targets.get("penale_nc_pct", 3.0)
    penale_euro = 0.0

    # OTD
    otd = misurazione.get("otd_misurato_pct")
    target_otd = targets.get("target_otd_pct", 95)
    if otd is not None:
        ok = otd >= target_otd
        scost = round(otd - target_otd, 1)
        kpi_check["otd"] = {"misurato": otd, "target": target_otd, "ok": ok, "scostamento": scost}
        if not ok:
            sev = "critical" if scost < -5 else "warning"
            alerts.append({"kpi": "otd", "scostamento": scost, "severity": sev})
            penale_euro += abs(scost) * penali_basi

    # Qualità
    qualita = misurazione.get("qualita_misurata_pct")
    target_q = targets.get("target_qualita_pct", 98)
    if qualita is not None:
        ok = qualita >= target_q
        scost = round(qualita - target_q, 1)
        kpi_check["qualita"] = {"misurato": qualita, "target": target_q, "ok": ok, "scostamento": scost}
        if not ok:
            sev = "critical" if scost < -3 else "warning"
            alerts.append({"kpi": "qualita", "scostamento": scost, "severity": sev})
            penale_euro += abs(scost) * penali_nc

    # OTIF
    otif = misurazione.get("otif_misurato_pct")
    target_otif = targets.get("target_otif_pct", 92)
    if otif is not None:
        ok = otif >= target_otif
        scost = round(otif - target_otif, 1)
        kpi_check["otif"] = {"misurato": otif, "target": target_otif, "ok": ok, "scostamento": scost}
        if not ok:
            alerts.append({"kpi": "otif", "scostamento": scost, "severity": "warning"})

    # Prezzo variazione
    prezzo = misurazione.get("prezzo_var_misurata_pct")
    target_p = targets.get("target_prezzo_var_pct", 3)
    if prezzo is not None:
        ok = prezzo <= target_p
        scost = round(prezzo - target_p, 1)
        kpi_check["prezzo"] = {"misurato": prezzo, "target": target_p, "ok": ok, "scostamento": scost}
        if not ok:
            alerts.append({"kpi": "prezzo", "scostamento": scost, "severity": "warning"})

    # Risposta
    risposta = misurazione.get("risposta_media_ore")
    target_r = targets.get("target_risposta_ore", 24)
    if risposta is not None:
        ok = risposta <= target_r
        scost = round(risposta - target_r, 1)
        kpi_check["risposta"] = {"misurato": risposta, "target": target_r, "ok": ok, "scostamento": scost}
        if not ok:
            alerts.append({"kpi": "risposta", "scostamento": scost, "severity": "warning"})

    # Compliance score
    n_ok = sum(1 for v in kpi_check.values() if v.get("ok"))
    n_tot = len(kpi_check)
    compliance = round(n_ok / n_tot * 100, 1) if n_tot else 100.0

    valutazione = (
        "Eccellente" if compliance >= 95 else
        "Buona"      if compliance >= 80 else
        "Sufficiente" if compliance >= 60 else
        "Insufficiente"
    )

    penale_max = targets.get("penale_max_mensile_pct", 10.0)
    penali_stimate = min(round(penale_euro, 2), penale_max)

    return {
        "compliance_score": compliance,
        "valutazione": valutazione,
        "kpi_check": kpi_check,
        "alerts": alerts,
        "penali_stimate_euro": penali_stimate,
    }


def calcola_scorecard_aggregata(scorecard: Dict) -> float:
    """Calcola score aggregato scorecard strategica partner"""
    pesi = {
        "score_qualita": 0.30,
        "score_innovazione": 0.25,
        "score_sostenibilita": 0.25,
        "score_collaborazione": 0.20,
    }
    total = sum(scorecard.get(k, 50) * p for k, p in pesi.items())
    return round(total, 1)


def suggerisci_livello_partnership(score: float) -> str:
    """Suggerisce il livello di partnership più adatto al rating attuale"""
    if score >= 92:
        return "exclusive"
    if score >= 85:
        return "strategic"
    if score >= 70:
        return "preferred"
    return "nessuna_partnership"


def genera_agenda_review(
    livello: str,
    score_attuale: float,
    kpi_critici: List[str],
    nc_aperte: int,
) -> List[str]:
    """Genera agenda standard per meeting di review partnership"""
    agenda = [
        f"1. Apertura meeting e verifica verbale precedente",
        f"2. Review KPI periodo: score attuale {score_attuale}/100 (classe {classifica_fornitore(score_attuale)['classe']})",
    ]

    if kpi_critici:
        agenda.append(f"3. Analisi KPI critici: {', '.join(kpi_critici)}")
    else:
        agenda.append("3. Analisi andamento KPI — tutti nella norma")

    if nc_aperte > 0:
        agenda.append(f"4. Revisione {nc_aperte} Non Conformità aperte — azioni correttive")
    else:
        agenda.append("4. Non Conformità — nessuna aperta")

    cfg = PARTNERSHIP_LIVELLI.get(livello, PARTNERSHIP_LIVELLI["preferred"])
    agenda.append(f"5. Verifica rispetto impegni contrattuali ({cfg['label']})")
    agenda.append("6. Piano azioni miglioramento prossimo trimestre")
    agenda.append("7. Data prossimo meeting e conclusioni")

    return agenda
