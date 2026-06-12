"""
BAD360.ai — Bandi & Finanza Agevolata Hospitality v1.0
Modulo dedicato alla ricerca e al match dei bandi per Hotel, Ristoranti, Bar.
Integra la logica TF-IDF di BA.IA + database curato settore hospitality.
"""

import os, re, math, json
from datetime import date
from typing import Optional, List
from fastapi import APIRouter
import httpx

router = APIRouter(prefix="/api/bandi", tags=["Bandi Hospitality"])

# ── STOPWORDS ITALIANE (da BA.IA matcher) ────────────────────────────────────
_STOPWORDS = {
    "il","lo","la","i","gli","le","un","uno","una","e","è","in","di","a","da","con",
    "per","tra","fra","su","non","si","che","se","ma","ed","ad","dei","del","della",
    "delle","degli","nel","nella","nelle","nei","negli","al","ai","alla","alle",
    "agli","dal","dai","dalla","dalle","dagli","sul","sui","sulla","sulle","sugli",
    "col","coi","come","quando","dove","questo","questa","questi","queste",
    "sono","ha","ho","avere","essere","fare","the","and","or","of","to","in","for",
}

def _tokenize(text: str) -> list[str]:
    text = text.lower()
    text = re.sub(r'[^\w\s]', ' ', text)
    return [t for t in text.split() if len(t) > 2 and t not in _STOPWORDS and not t.isdigit()]

def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x*x for x in a))
    nb = math.sqrt(sum(x*x for x in b))
    return dot / (na * nb) if na and nb else 0.0

def _tfidf(tokens: list[str], vocab: dict[str, int]) -> list[float]:
    if not tokens:
        return [0.0] * len(vocab)
    tf: dict[str, float] = {}
    for t in tokens:
        tf[t] = tf.get(t, 0) + 1
    n = len(tokens)
    vec = [0.0] * len(vocab)
    for term, idx in vocab.items():
        if term in tf:
            vec[idx] = tf[term] / n
    return vec


# ── DATASET BANDI HOSPITALITY ────────────────────────────────────────────────
BANDI_HOSPITALITY = [
    {
        "id": "t5",
        "name": "Transizione 5.0 — Credito d'Imposta Efficienza Energetica",
        "ente": "MIMIT / GSE",
        "tipo": "credito_imposta",
        "settori": ["hotel", "ristorante", "bar", "resort", "agriturismo", "beb", "pizzeria", "pub"],
        "regioni": [],
        "ateco": ["55.10", "55.20", "55.30", "55.90", "56.10", "56.21", "56.30"],
        "importo_max": 50000000,
        "contributo_pct": 45,
        "scadenza": "2025-12-31",
        "obiettivi": ["energia", "digital"],
        "dim_ammesse": ["micro", "piccola", "media", "grande"],
        "desc": "Credito d'imposta fino al 45% per investimenti in beni strumentali che producono risparmio energetico >= 3% struttura o >= 10% processo. Cumulabile con Industria 4.0.",
        "requisiti": [
            "Riduzione consumi energetici >= 3% (struttura) o >= 10% (processo)",
            "Beni strumentali nuovi materiali e immateriali",
            "Perizia tecnica asseverata da ingegnere abilitato",
            "Comunicazione preventiva a GSE",
        ],
        "link": "https://www.mimit.gov.it/transizione-5",
        "note": "Cumulabile con Sabatini Verde e credito R&S.",
    },
    {
        "id": "ind4",
        "name": "Industria 4.0 — Credito d'Imposta Beni Strumentali",
        "ente": "MIMIT / Agenzia delle Entrate",
        "tipo": "credito_imposta",
        "settori": ["hotel", "ristorante", "bar", "resort", "agriturismo", "beb", "pizzeria", "pub"],
        "regioni": [],
        "ateco": ["55.10", "55.20", "55.30", "55.90", "56.10", "56.21", "56.30"],
        "importo_max": 20000000,
        "contributo_pct": 20,
        "scadenza": "aperto",
        "obiettivi": ["digital", "ristrutturazione"],
        "dim_ammesse": ["micro", "piccola", "media", "grande"],
        "desc": "Credito d'imposta per acquisto beni strumentali nuovi: macchinari cucina, impianti, attrezzature bar, POS, software gestionali PMS/RMS.",
        "requisiti": [
            "Beni strumentali nuovi destinati a strutture produttive in Italia",
            "Interconnessione al sistema aziendale (beni 4.0)",
            "Dichiarazione o perizia tecnica per beni > 300.000 EUR",
        ],
        "link": "https://www.mimit.gov.it/industria-4",
        "note": "Sportello sempre aperto, in dichiarazione dei redditi.",
    },
    {
        "id": "pnrr_tur",
        "name": "PNRR M1C3 — Turismo 4.0 & Digitalizzazione Ricettivo",
        "ente": "Ministero del Turismo / ENIT",
        "tipo": "pnrr",
        "settori": ["hotel", "resort", "agriturismo", "beb"],
        "regioni": [],
        "ateco": ["55.10", "55.20", "55.30", "55.90"],
        "importo_max": 500000,
        "contributo_pct": 80,
        "scadenza": "2026-06-30",
        "obiettivi": ["digital"],
        "dim_ammesse": ["piccola", "media"],
        "desc": "Finanziamenti a fondo perduto fino a 500.000 EUR per digitalizzazione strutture ricettive: PMS, channel manager, booking engine, CRM, revenue management.",
        "requisiti": [
            "Struttura ricettiva regolarmente classificata",
            "Almeno 5 camere o unità abitative",
            "Investimenti in tecnologie digitali certificate",
        ],
        "link": "https://www.turismo.gov.it/pnrr",
        "note": "Prossima apertura sportello prevista Q3 2026.",
    },
    {
        "id": "fnt",
        "name": "Fondo Nazionale Turismo — Contributi PMI Ricettive",
        "ente": "Ministero del Turismo",
        "tipo": "nazionale",
        "settori": ["hotel", "resort", "agriturismo", "beb"],
        "regioni": [],
        "ateco": ["55.10", "55.20", "55.30", "55.90"],
        "importo_max": 300000,
        "contributo_pct": 50,
        "scadenza": "2026-09-30",
        "obiettivi": ["ristrutturazione", "green", "formazione"],
        "dim_ammesse": ["micro", "piccola", "media"],
        "desc": "Contributi a fondo perduto per PMI del ricettivo: ammodernamento, efficienza energetica, accessibilità, sicurezza, formazione. Senza obbligo di co-investimento.",
        "requisiti": [
            "PMI classificata (< 250 dip, fatturato < 50 M EUR)",
            "Codice ATECO 55.xx",
            "Struttura attiva da almeno 24 mesi",
            "Piano di investimento con relazione tecnica",
        ],
        "link": "https://www.turismo.gov.it/fondi",
        "note": "Priorità assoluta a strutture del Mezzogiorno e isole.",
    },
    {
        "id": "sabatini_g",
        "name": "Nuova Sabatini Verde — Macchinari Green",
        "ente": "MIMIT / Mediocredito Centrale",
        "tipo": "nazionale",
        "settori": ["hotel", "ristorante", "bar", "resort", "agriturismo", "beb", "pizzeria", "pub"],
        "regioni": [],
        "ateco": ["55.10", "55.20", "55.30", "55.90", "56.10", "56.21", "56.30"],
        "importo_max": 4000000,
        "contributo_pct": 4,
        "scadenza": "aperto",
        "obiettivi": ["green", "energia", "ristrutturazione"],
        "dim_ammesse": ["micro", "piccola", "media"],
        "desc": "Contributo interessi su finanziamenti bancari per macchinari, attrezzature e impianti a basso impatto ambientale. Tasso agevolato 4,5% green.",
        "requisiti": [
            "Fatturato <= 250 M EUR",
            "Acquisto beni strumentali nuovi certificati green",
            "Finanziamento bancario >= 20% dell'investimento",
        ],
        "link": "https://www.mimit.gov.it/sabatini",
        "note": "Cumulabile con credito d'imposta Industria 4.0.",
    },
    {
        "id": "formazione4",
        "name": "Credito d'Imposta Formazione 4.0",
        "ente": "Agenzia delle Entrate / MIMIT",
        "tipo": "credito_imposta",
        "settori": ["hotel", "ristorante", "bar", "resort", "agriturismo", "beb", "pizzeria", "pub"],
        "regioni": [],
        "ateco": ["55.10", "55.20", "55.30", "55.90", "56.10", "56.21", "56.30"],
        "importo_max": 300000,
        "contributo_pct": 50,
        "scadenza": "aperto",
        "obiettivi": ["formazione", "digital"],
        "dim_ammesse": ["micro", "piccola", "media", "grande"],
        "desc": "Credito d'imposta fino al 70% per formazione dipendenti su digital, revenue management, POS, sostenibilità, HACCP avanzato, lingue straniere.",
        "requisiti": [
            "Dipendenti in attività digitali o turistico-ricettive",
            "Registro presenze e documentazione formazione",
            "Accordo sindacale o ETS per formazione > 300h",
        ],
        "link": "https://www.agenziaentrate.gov.it/formazione-4",
        "note": "Aliquota 50% piccole, 40% medie, 30% grandi imprese.",
    },
    {
        "id": "decontrib_sud",
        "name": "Decontribuzione Sud — Assunzioni Turismo",
        "ente": "INPS / Ministero Lavoro",
        "tipo": "nazionale",
        "settori": ["hotel", "ristorante", "bar", "resort", "agriturismo", "beb", "pizzeria", "pub"],
        "regioni": ["Campania", "Basilicata", "Calabria", "Puglia", "Sicilia", "Sardegna", "Abruzzo", "Molise"],
        "ateco": ["55.10", "55.20", "55.90", "56.10", "56.30"],
        "importo_max": 0,
        "contributo_pct": 30,
        "scadenza": "2029-12-31",
        "obiettivi": ["formazione", "liquidita"],
        "dim_ammesse": ["micro", "piccola", "media", "grande"],
        "desc": "Esonero contributivo 30% per nuove assunzioni in strutture del Mezzogiorno. Applicabile a contratti a tempo indeterminato e determinato >= 12 mesi.",
        "requisiti": [
            "Struttura nel Mezzogiorno",
            "DURC regolare",
            "Nessuna riduzione personale nei 6 mesi precedenti",
        ],
        "link": "https://www.inps.it/decontribuzione-sud",
        "note": "Valida fino al 2029. Cumulabile con altri incentivi assunzione.",
    },
    {
        "id": "zes_sud",
        "name": "ZES Unica Mezzogiorno — Credito Imposta Investimenti",
        "ente": "Struttura di Missione ZES / MIMIT",
        "tipo": "credito_imposta",
        "settori": ["hotel", "ristorante", "resort", "agriturismo"],
        "regioni": ["Campania", "Basilicata", "Calabria", "Puglia", "Sicilia", "Sardegna", "Abruzzo", "Molise"],
        "ateco": ["55.10", "55.20", "56.10"],
        "importo_max": 100000000,
        "contributo_pct": 60,
        "scadenza": "2025-12-31",
        "obiettivi": ["ristrutturazione", "digital", "energia"],
        "dim_ammesse": ["micro", "piccola", "media", "grande"],
        "desc": "Credito d'imposta per beni strumentali destinati a strutture turistiche nelle ZES del Mezzogiorno. Aliquota fino al 60% per micro-imprese.",
        "requisiti": [
            "Struttura produttiva in ZES Unica Mezzogiorno",
            "Acquisizione beni strumentali nuovi",
            "Mantenimento attività >= 5 anni",
        ],
        "link": "https://www.governo.it/zes",
        "note": "Cumulabile con altri incentivi entro massimale aiuti di Stato.",
    },
    {
        "id": "simest_export",
        "name": "SIMEST — Digitalizzazione Export Servizi Turistici",
        "ente": "SIMEST / CDP",
        "tipo": "nazionale",
        "settori": ["hotel", "resort", "agriturismo"],
        "regioni": [],
        "ateco": ["55.10", "55.20"],
        "importo_max": 300000,
        "contributo_pct": 40,
        "scadenza": "2026-12-31",
        "obiettivi": ["internazionalizzazione", "digital"],
        "dim_ammesse": ["piccola", "media", "grande"],
        "desc": "Co-finanziamento agevolato tasso 0% per PMI che sviluppano l'export di servizi turistici: OTA internazionali, certificazioni estere, fiere, portali multilingue.",
        "requisiti": [
            "PMI con fatturato export >= 10% o in sviluppo",
            "Struttura ricettiva classificata",
            "Piano export approvato",
        ],
        "link": "https://www.simest.it/turismo",
        "note": "Quota fondo perduto 25% per imprese femminili o Mezzogiorno.",
    },
    {
        "id": "ecobonus_hotel",
        "name": "Ecobonus & Sismabonus — Ristrutturazione Ricettivo",
        "ente": "Agenzia delle Entrate",
        "tipo": "credito_imposta",
        "settori": ["hotel", "resort", "agriturismo", "beb"],
        "regioni": [],
        "ateco": ["55.10", "55.20", "55.90"],
        "importo_max": 96000,
        "contributo_pct": 65,
        "scadenza": "2025-12-31",
        "obiettivi": ["energia", "ristrutturazione"],
        "dim_ammesse": ["micro", "piccola", "media", "grande"],
        "desc": "Detrazioni fiscali 65-85% per riqualificazione energetica e sismica di immobili ricettivi. Cessione del credito alle banche previo visto di conformità.",
        "requisiti": [
            "Immobile a uso ricettivo in Italia",
            "Interventi certificati efficienza energetica",
            "Documentazione ENEA entro 90 gg dalla fine lavori",
        ],
        "link": "https://www.agenziaentrate.gov.it/ecobonus",
        "note": "In attesa di proroga per il 2026.",
    },
    {
        "id": "fondo_garanzia",
        "name": "Fondo di Garanzia PMI — Hospitality",
        "ente": "MCC / Mediocredito Centrale",
        "tipo": "nazionale",
        "settori": ["hotel", "ristorante", "bar", "resort", "agriturismo", "beb", "pizzeria", "pub"],
        "regioni": [],
        "ateco": ["55.10", "55.20", "55.90", "56.10", "56.21", "56.30"],
        "importo_max": 5000000,
        "contributo_pct": 0,
        "scadenza": "aperto",
        "obiettivi": ["liquidita", "ristrutturazione", "nuova_apertura"],
        "dim_ammesse": ["micro", "piccola", "media"],
        "desc": "Garanzia pubblica gratuita (fino all'80%) su finanziamenti bancari alle PMI del turismo. Riduce il costo del denaro senza garanzie reali.",
        "requisiti": [
            "PMI con ATECO ammesso",
            "Richiesta tramite banca/intermediario",
            "Nessuna procedura concorsuale in corso",
        ],
        "link": "https://www.fondidigaranzia.it",
        "note": "Garanzia gratuita per micro-imprese nel Mezzogiorno.",
    },
    {
        "id": "haccp_form",
        "name": "Fondo Paritetico Turismo — Formazione HACCP",
        "ente": "For.Te / Confcommercio FIPE",
        "tipo": "nazionale",
        "settori": ["ristorante", "bar", "hotel", "pizzeria", "pub"],
        "regioni": [],
        "ateco": ["56.10", "56.30", "55.10", "56.21"],
        "importo_max": 20000,
        "contributo_pct": 100,
        "scadenza": "aperto",
        "obiettivi": ["formazione"],
        "dim_ammesse": ["micro", "piccola", "media"],
        "desc": "Formazione finanziata al 100% via fondi interprofessionali For.Te: HACCP obbligatorio, sicurezza D.Lgs. 81/2008, food allergy, gestionale F&B, soft skill.",
        "requisiti": [
            "Aderente a For.Te o For.Turismo (iscrizione gratuita)",
            "Dipendenti con CCNL Turismo",
            "Piano formativo annuale",
        ],
        "link": "https://www.forte.net/formazione-finanziata",
        "note": "Massimo 80h/dipendente/anno.",
    },
    {
        "id": "green_key",
        "name": "Green Key Hotel — Finanziamento Certificazione",
        "ente": "Legambiente / MASE",
        "tipo": "nazionale",
        "settori": ["hotel", "resort", "agriturismo", "beb"],
        "regioni": [],
        "ateco": ["55.10", "55.20", "55.90"],
        "importo_max": 15000,
        "contributo_pct": 50,
        "scadenza": "2026-06-30",
        "obiettivi": ["green"],
        "dim_ammesse": ["micro", "piccola", "media"],
        "desc": "Contributi per ottenimento e mantenimento certificazione Green Key (FEE Italia): audit ambientale, consulenza, formazione staff, comunicazione sostenibilità.",
        "requisiti": [
            "Struttura ricettiva con minimo 5 camere",
            "Programma risparmio idrico ed energetico",
            "Gestione dei rifiuti certificata",
        ],
        "link": "https://www.greenkeyitalia.it",
        "note": "Certificazione riconosciuta da GSTC e Booking.com.",
    },
]

# Aggiungi bandi FESR regionali
_FESR_REGIONALI = [
    ("Lombardia", "fesr_lom", 500000, 50, "2026-03-31", ["hotel","ristorante","resort","agriturismo"], ["Lombardia"]),
    ("Sicilia", "fesr_sic", 400000, 65, "2026-06-30", ["hotel","ristorante","resort","agriturismo","beb"], ["Sicilia"]),
    ("Sardegna", "fesr_sar", 600000, 60, "2026-04-30", ["hotel","resort","agriturismo","beb"], ["Sardegna"]),
    ("Campania", "fesr_cam", 400000, 60, "2026-05-31", ["hotel","ristorante","resort","agriturismo","pizzeria"], ["Campania"]),
    ("Veneto", "fesr_ven", 350000, 50, "2026-07-31", ["hotel","ristorante","resort","agriturismo","beb"], ["Veneto"]),
    ("Toscana", "fesr_tos", 300000, 55, "2026-08-31", ["hotel","ristorante","resort","agriturismo","beb","pizzeria"], ["Toscana"]),
    ("Lazio", "fesr_laz", 100000, 50, "2026-02-28", ["bar","ristorante","pub","pizzeria"], ["Lazio"]),
]

for reg, bid, imp, pct, scad, settori, regioni in _FESR_REGIONALI:
    BANDI_HOSPITALITY.append({
        "id": bid,
        "name": f"FESR 2021-2027 {reg} — Turismo & Ospitalità",
        "ente": f"Regione {reg}",
        "tipo": "fesr",
        "settori": settori,
        "regioni": regioni,
        "ateco": ["55.10", "55.20", "55.90", "56.10"],
        "importo_max": imp,
        "contributo_pct": pct,
        "scadenza": scad,
        "obiettivi": ["ristrutturazione", "green", "digital"],
        "dim_ammesse": ["micro", "piccola", "media"],
        "desc": f"Fondi europei FESR per strutture ricettive e ristorative in {reg}: sostenibilità, digitalizzazione, qualità servizi, accessibilità. Quota fondo perduto.",
        "requisiti": [
            f"Sede e attività in {reg}",
            "PMI settore turistico-ricettivo",
            "Investimento minimo EUR 10.000",
            "Iscrizione CCIAA regionale",
        ],
        "link": f"https://www.regione.{reg.lower().replace(' ','-')}.it/fesr",
        "note": f"Verifica apertura sportello sul portale ufficiale Regione {reg}.",
    })


# ── TF-IDF MATCHING (logica BA.IA adattata) ──────────────────────────────────

def _bando_text(b: dict) -> str:
    return " ".join([
        b.get("name", ""),
        b.get("ente", ""),
        b.get("desc", ""),
        " ".join(b.get("settori", [])),
        " ".join(b.get("obiettivi", [])),
        " ".join(b.get("ateco", [])),
        " ".join(b.get("regioni", [])),
    ])

def _profilo_text(p: dict) -> str:
    return " ".join([
        p.get("tipo", ""),
        p.get("regione", ""),
        p.get("ateco", ""),
        p.get("obiettivo", ""),
        p.get("dim", ""),
        p.get("note", ""),
    ])

def match_bandi_tfidf(profilo: dict, bandi: list[dict] | None = None) -> list[dict]:
    """
    Calcola match score TF-IDF tra profilo azienda e ogni bando.
    Restituisce lista ordinata per score decrescente.
    """
    if bandi is None:
        bandi = BANDI_HOSPITALITY

    az_text = _profilo_text(profilo)
    bandi_texts = [(_bando_text(b), b) for b in bandi]

    all_tokens = [_tokenize(az_text)] + [_tokenize(bt) for bt, _ in bandi_texts]
    vocab: dict[str, int] = {}
    for tokens in all_tokens:
        for t in tokens:
            if t not in vocab:
                vocab[t] = len(vocab)

    if not vocab:
        return [{**b, "score": 0, "method": "tfidf"} for b in bandi]

    az_vec = _tfidf(all_tokens[0], vocab)
    results = []

    for i, (bt, bando) in enumerate(bandi_texts):
        b_vec = _tfidf(all_tokens[i + 1], vocab)
        cos = _cosine(az_vec, b_vec)

        # Boost esplicito per match settore, ATECO, regione
        boost = 0.0
        if profilo.get("tipo") and profilo["tipo"] in bando.get("settori", []):
            boost += 0.15
        if profilo.get("ateco") and profilo["ateco"] in bando.get("ateco", []):
            boost += 0.12
        if profilo.get("regione") and (
            not bando["regioni"] or profilo["regione"] in bando["regioni"]
        ):
            boost += 0.08
        if profilo.get("obiettivo") and profilo["obiettivo"] in bando.get("obiettivi", []):
            boost += 0.10

        # Penalizza bandi scaduti
        scad = bando.get("scadenza", "")
        if scad and scad != "aperto":
            try:
                if date.fromisoformat(scad) < date.today():
                    cos *= 0.15
            except ValueError:
                pass

        score = min(100, int((cos + boost) * 110))
        matching = set(all_tokens[0]) & set(all_tokens[i + 1])
        key_terms = [t for t in matching if len(t) > 4][:4]
        reason = f"Termini in comune: {', '.join(key_terms)}" if key_terms else "Compatibilità strutturale"

        results.append({
            **bando,
            "score": max(0, score),
            "reason_tfidf": reason,
            "method": "tfidf",
        })

    results.sort(key=lambda x: x["score"], reverse=True)
    return results


# ── API ROUTES ────────────────────────────────────────────────────────────────

@router.get("/hospitality/list")
async def list_bandi_hospitality(
    tipo: Optional[str] = None,
    regione: Optional[str] = None,
    settore: Optional[str] = None,
    obiettivo: Optional[str] = None,
    solo_attivi: bool = True,
):
    """Lista tutti i bandi hospitality con filtri opzionali."""
    result = BANDI_HOSPITALITY.copy()

    if tipo:
        result = [b for b in result if b["tipo"] == tipo]
    if regione:
        result = [b for b in result if not b["regioni"] or regione in b["regioni"]]
    if settore:
        result = [b for b in result if settore in b["settori"]]
    if obiettivo:
        result = [b for b in result if obiettivo in b.get("obiettivi", [])]
    if solo_attivi:
        today = date.today().isoformat()
        result = [b for b in result if b["scadenza"] == "aperto" or b["scadenza"] >= today]

    return {
        "totale": len(result),
        "bandi": result,
        "aggiornamento": date.today().isoformat(),
    }


@router.post("/hospitality/match")
async def match_bandi_hospitality(
    tipo_struttura: str,
    regione: Optional[str] = None,
    ateco: Optional[str] = None,
    dim: Optional[str] = None,
    obiettivo: Optional[str] = None,
    note: Optional[str] = None,
    min_score: int = 20,
    limit: int = 20,
):
    """
    Match TF-IDF tra profilo struttura hospitality e database bandi.
    Porta la logica di BA.IA.matcher nel modulo BAD360.
    """
    profilo = {
        "tipo": tipo_struttura,
        "regione": regione or "",
        "ateco": ateco or "",
        "dim": dim or "",
        "obiettivo": obiettivo or "",
        "note": note or "",
    }

    matched = match_bandi_tfidf(profilo)
    filtered = [b for b in matched if b["score"] >= min_score][:limit]

    return {
        "profilo": profilo,
        "totale_match": len(filtered),
        "bandi": filtered,
        "score_medio": round(sum(b["score"] for b in filtered) / len(filtered), 1) if filtered else 0,
        "metodo": "tfidf-hospitality-v1",
        "timestamp": date.today().isoformat(),
    }


@router.get("/hospitality/stats")
async def bandi_stats():
    """Statistiche sul database bandi hospitality."""
    today = date.today().isoformat()
    attivi = [b for b in BANDI_HOSPITALITY if b["scadenza"] == "aperto" or b["scadenza"] >= today]
    scad_90 = [b for b in attivi if b["scadenza"] != "aperto" and b["scadenza"] <= (
        date.today().replace(day=min(date.today().day, 28))
    ).isoformat()]

    per_tipo: dict[str, int] = {}
    for b in BANDI_HOSPITALITY:
        per_tipo[b["tipo"]] = per_tipo.get(b["tipo"], 0) + 1

    regioni_coperte = set()
    for b in BANDI_HOSPITALITY:
        regioni_coperte.update(b["regioni"])

    return {
        "totale_bandi": len(BANDI_HOSPITALITY),
        "bandi_attivi": len(attivi),
        "scadono_90gg": len(scad_90),
        "per_tipo": per_tipo,
        "regioni_coperte": sorted(regioni_coperte),
        "plafond_max_accessibile": sum(
            b["importo_max"] for b in attivi if b["importo_max"] > 0
        ),
    }


# ── AI ADVISOR BANDI (endpoint per il frontend) ──────────────────────────────

class BandiAdvisorRequest:
    def __init__(self, query: str, context: Optional[str] = None):
        self.query = query
        self.context = context

from pydantic import BaseModel as _BM

class BandiAdvisorBody(_BM):
    query: str
    context: Optional[str] = None

@router.post("/ai-advisor")
async def bandi_ai_advisor(body: BandiAdvisorBody):
    """
    AI Advisor specializzato in finanza agevolata per l'hospitality italiana.
    Usa Claude claude-haiku-4-5-20251001 per massimizzare velocità e contenere i costi.
    """
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        return {
            "answer": (
                "L'AI Advisor non è attiva (ANTHROPIC_API_KEY mancante). "
                "Consulta i bandi nel database o contatta il supporto."
            ),
            "demo": True,
        }

    system = (
        "Sei l'AI Advisor BAD360.ai specializzato in finanza agevolata italiana per il settore hospitality "
        "(hotel, ristoranti, bar, agriturismo, resort, B&B). "
        "Rispondi sempre in italiano, in modo conciso e pratico. "
        "Hai profonda conoscenza di: PNRR turismo, fondi FESR 2021-2027, bandi Invitalia, SIMEST, "
        "Transizione 5.0, Industria 4.0, Nuova Sabatini, decontribuzione Sud, ZES Mezzogiorno, "
        "crediti d'imposta formazione, Ecobonus, Fondo di Garanzia PMI, For.Te formazione. "
        "Per ogni bando fornisci: importo, % contributo, scadenza, requisiti chiave. "
        "Concludi sempre con un consiglio operativo su come avviare la domanda."
    )

    query_full = body.query
    if body.context:
        query_full = f"[Profilo struttura: {body.context}]\n\n{body.query}"

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": "claude-haiku-4-5-20251001",
                    "max_tokens": 800,
                    "system": system,
                    "messages": [{"role": "user", "content": query_full}],
                },
            )
        if resp.status_code == 200:
            data = resp.json()
            text = "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")
            return {"answer": text, "demo": False}
    except Exception:
        pass

    return {
        "answer": (
            "Errore temporaneo nell'AI Advisor. "
            "Puoi comunque consultare il database bandi e utilizzare il match score locale."
        ),
        "demo": True,
    }
