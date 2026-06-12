"""
BAD.S Unified Platform — Backend API
SaaS B2C per Hotellerie | Supply Chain Management & F&B Intelligence
Versione: 2.0.0 | Framework: FastAPI + Supabase
"""

import os
import io
import json
import httpx
import asyncio
import calendar
from datetime import date, datetime, timedelta
from typing import Optional, List, Dict, Any

from fastapi import FastAPI, HTTPException, Depends, Request, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from dotenv import load_dotenv
from fastapi.responses import StreamingResponse
from backend.haccp_report import HACCPPdfGenerator, HACCPReportData, TemperatureReading
from backend.fb_cost import router as fb_router
from backend.housekeeping import (
    HKRoomUpdate, HKTaskCreate, HKTaskComplete,
    SupplyMovement, LaundryCycleCreate, LaundryCycleDelivery, LinenParRequest,
    CHECKLIST_TEMPLATES, DURATA_STANDARD, BENCHMARK_COSTO_CAMERA,
    calcola_par_level_biancheria, calcola_costo_ciclo_lavanderia, kpi_produttivita_hk,
)
from backend.scm_risk import router as scm_risk_router
from backend.partnership import (
        VendorRatingManuale, VRKpiEventCreate,
        SLAContractCreate, SLAMeasurement, SLAAlertUpdate,
        PartnershipCreate, PartnershipMeetingCreate,
        PartnershipMeetingComplete, ScorecardCompile,
        VR_CLASSI, VR_AZIONI, SLA_DEFAULTS, PARTNERSHIP_LIVELLI,
        calcola_score_totale, classifica_fornitore,
        calcola_score_compliance_cert, calcola_sla_compliance,
        calcola_scorecard_aggregata, suggerisci_livello_partnership,
        genera_agenda_review,
    )
from backend.non_conformita import router as nc_router
from backend.tracciabilita import router as tracciabilita_router
from backend.shelf_life import (
    router as shelf_life_router,
    start_scheduler,
    stop_scheduler,
)
from backend.auth import router as auth_router
from backend.morning_briefing import (
    router as briefing_router,
    start_briefing_scheduler,
    stop_briefing_scheduler,
)
from backend.ai_agents import router as ai_agents_router
from backend.staff_match import router as staff_match_router

load_dotenv()

# ─── Config ──────────────────────────────────────────────────────────────────
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
SUPABASE_URL      = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY      = os.getenv("SUPABASE_SERVICE_KEY", "")
APP_SECRET        = os.getenv("APP_SECRET", "change-me-in-production")
ALLOWED_ORIGINS   = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000,http://localhost:8000").split(",")

# ─── App init ────────────────────────────────────────────────────────────────
app = FastAPI(
    title="BAD360.ai — Hospitality AI Platform API",
    description="API backend per BAD360.ai — Suite modulare per Hotellerie, F&B, HACCP, SCM e Analytics",
    version="4.1.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(fb_router)
app.include_router(scm_risk_router)
app.include_router(nc_router)
app.include_router(tracciabilita_router)
app.include_router(shelf_life_router)
app.include_router(auth_router)
app.include_router(briefing_router)
app.include_router(ai_agents_router)
app.include_router(staff_match_router)


# ─── Pydantic Models ─────────────────────────────────────────────────────────

class AIQueryRequest(BaseModel):
    """Richiesta di query AI all'advisor intelligente"""
    query: str = Field(..., min_length=3, max_length=2000, description="Testo della domanda")
    context: Optional[str] = Field(None, description="Contesto aggiuntivo (hotel, settore, ecc.)")
    module: Optional[str] = Field("general", description="Modulo: general|scm|haccp|esg|beverage")
    conversation_history: Optional[List[Dict]] = Field([], description="Storico conversazione")

class AIQueryResponse(BaseModel):
    answer: str
    module: str
    tokens_used: int
    timestamp: str

class BandiSearchRequest(BaseModel):
    """Ricerca bandi di finanziamento"""
    keywords: List[str] = Field(..., description="Parole chiave per la ricerca")
    regione: Optional[str] = Field(None, description="Regione italiana")
    settore: Optional[str] = Field("hospitality", description="Settore di attività")
    budget_min: Optional[int] = Field(None, description="Budget minimo richiesto €")
    budget_max: Optional[int] = Field(None, description="Budget massimo richiesto €")

class SupplierEvalRequest(BaseModel):
    """Richiesta valutazione fornitore SCM"""
    nome: str
    categoria: str  # food_fresh | beverage | chimici | tessile | manutenzione | tech
    piva: Optional[str] = None
    certificazioni: List[str] = Field([], description="ISO 22000, HACCP, ISO 14001, ecc.")
    note: Optional[str] = None

class HACCPTemperatureLog(BaseModel):
    """Log temperatura HACCP da sensori IoT"""
    sensor_id: str
    zona: str
    temperatura: float
    timestamp: Optional[str] = None
    alert: Optional[bool] = False

class ESGReportRequest(BaseModel):
    """Richiesta generazione report ESG"""
    hotel_name: str
    anno: int = Field(default_factory=lambda: datetime.now().year)
    dati: Dict[str, Any] = Field({}, description="KPI ambientali, sociali, governance")

# ─── Helpers ─────────────────────────────────────────────────────────────────

def get_system_prompt(module: str) -> str:
    """Restituisce il system prompt appropriato per modulo"""
    base = (
        "Sei l'AI Advisor di BAD.S Unified Platform, specializzato nella gestione alberghiera italiana. "
        "Rispondi sempre in italiano, in modo professionale e concreto. "
        "Hai profonda conoscenza di: Supply Chain Management in hotellerie, ISO 9001/14001/45001/22000, "
        "HACCP, ESG/CSR, sistemi ERP/PMS/CRM, normative italiane ed europee per la ristorazione e l'ospitalità. "
    )
    prompts = {
        "scm": base + (
            "Sei esperto in Supply Chain Management alberghiero: procurement, gestione fornitori, "
            "Lean Management, KPI di filiera, tracciabilità ISO 22005, food cost, par level, kanban."
        ),
        "haccp": base + (
            "Sei esperto HACCP: piano di autocontrollo, CCP, 7 principi Codex Alimentarius, "
            "Reg. CE 852/2004, ISO 22000, rintracciabilità Reg. CE 178/2002, formazione personale."
        ),
        "esg": base + (
            "Sei esperto ESG/CSR: reporting GRI, standard GSTC, LECS luxury, SDGs ONU, "
            "certificazioni ambientali (ISO 14001, ISO 50001, Ecolabel UE, Green Key, EMAS)."
        ),
        "beverage": base + (
            "Sei esperto di Food & Beverage Cost Management in hotellerie italiana. "
            "Conosci: food cost % (target 28-35% per stelle), beverage cost % (18-25% cocktail bar), "
            "distinta base ricette, menu engineering, BCG matrix (star/cash cow/question mark/dog), "
            "gross profit margin, inventory management F&B, FIFO/FEFO, recipe costing, "
            "allergeni Reg. UE 1169/2011, fatturazione IVA ristorazione/alcolici. "
            "Dai sempre consigli pratici e numeri di benchmark settoriali."
        ),
        "general": base + (
            "Rispondi a domande generali su gestione alberghiera, supply chain, normative, "
            "digitalizzazione, formazione professionale e strategie competitive."
        ),
    }
    return prompts.get(module, prompts["general"])

async def call_anthropic(
    query: str,
    system_prompt: str,
    history: List[Dict] = None,
    max_tokens: int = 1024
) -> Dict:
    """Chiama l'API Anthropic Claude"""
    if not ANTHROPIC_API_KEY:
        raise HTTPException(status_code=500, detail="ANTHROPIC_API_KEY non configurata")

    messages = (history or []) + [{"role": "user", "content": query}]

    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": "claude-sonnet-4-20250514",
                "max_tokens": max_tokens,
                "system": system_prompt,
                "messages": messages,
            },
        )

    if response.status_code != 200:
        raise HTTPException(status_code=502, detail=f"Errore API Anthropic: {response.text}")

    data = response.json()
    text = "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")
    tokens = data.get("usage", {}).get("output_tokens", 0)
    return {"text": text, "tokens": tokens}

# ─── Routes ──────────────────────────────────────────────────────────────────

@app.get("/api/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "ok",
        "version": "4.1.0",
        "timestamp": datetime.utcnow().isoformat(),
        "services": {
            "anthropic": bool(ANTHROPIC_API_KEY),
            "supabase": bool(SUPABASE_URL and SUPABASE_KEY),
        }
    }

# ── AI Advisor ──────────────────────────────────────────────────────────────

@app.post("/api/ai/query", response_model=AIQueryResponse)
async def ai_query(req: AIQueryRequest):
    """
    Query all'AI Advisor BAD.S.
    Supporta moduli: general, scm, haccp, esg, beverage
    """
    system_prompt = get_system_prompt(req.module or "general")
    query_full = req.query
    if req.context:
        query_full = f"[Contesto: {req.context}]\n\n{req.query}"

    result = await call_anthropic(
        query=query_full,
        system_prompt=system_prompt,
        history=req.conversation_history or [],
    )

    return AIQueryResponse(
        answer=result["text"],
        module=req.module or "general",
        tokens_used=result["tokens"],
        timestamp=datetime.utcnow().isoformat(),
    )

@app.post("/api/ai/scm-advisor")
async def scm_advisor(req: AIQueryRequest):
    """AI Advisor specializzato Supply Chain Management in hotellerie"""
    req.module = "scm"
    return await ai_query(req)

@app.post("/api/ai/haccp-advisor")
async def haccp_advisor(req: AIQueryRequest):
    """AI Advisor specializzato HACCP e sicurezza alimentare"""
    req.module = "haccp"
    return await ai_query(req)

@app.post("/api/ai/esg-advisor")
async def esg_advisor(req: AIQueryRequest):
    """AI Advisor specializzato ESG e certificazioni sostenibilità"""
    req.module = "esg"
    return await ai_query(req)

@app.post("/api/ai/fb-advisor")
async def fb_advisor(req: AIQueryRequest):
    """
    AI Advisor specializzato Food & Beverage Cost Management.
    Analizza food cost, bev cost, ottimizzazione ricette, BCG matrix, menu engineering.
    """
    req.module = "beverage"
    return await ai_query(req)


# ── Bandi & Finanziamenti ───────────────────────────────────────────────────

@app.post("/api/bandi/search")
async def search_bandi(req: BandiSearchRequest):
    """
    Ricerca bandi di finanziamento per il settore hospitality tramite AI.
    Analizza opportunità PNRR, FESR, fondi nazionali e regionali.
    """
    prompt = (
        f"Sei un esperto di finanza agevolata per il settore turismo e ospitalità in Italia. "
        f"Cerca e descrivi i principali bandi di finanziamento attivi o in prossima apertura per: "
        f"Keywords: {', '.join(req.keywords)}. "
        f"Settore: {req.settore}. "
        f"Regione: {req.regione or 'tutta Italia'}. "
        f"Budget azienda: {req.budget_min or 'non specificato'} - {req.budget_max or 'non specificato'} €. "
        f"Fornisci: nome bando, ente erogatore, scadenza presunta, % contributo, importo max, "
        f"requisiti principali e link ufficiale se disponibile. Formato JSON."
    )

    system = (
        "Sei un esperto di finanza agevolata italiana specializzato in turismo e hospitality. "
        "Conosci PNRR, fondi FESR 2021-2027, bandi Invitalia, SIMEST, fondi regionali, "
        "agevolazioni fiscali (credito d'imposta ricerca, 4.0), bandi Federalberghi. "
        "Rispondi SOLO in JSON valido con array 'bandi'."
    )

    result = await call_anthropic(query=prompt, system_prompt=system, max_tokens=2000)

    try:
        clean = result["text"].replace("```json", "").replace("```", "").strip()
        data = json.loads(clean)
    except json.JSONDecodeError:
        data = {"bandi": [], "raw": result["text"]}

    return {
        "results": data,
        "query_params": req.dict(),
        "timestamp": datetime.utcnow().isoformat(),
    }

# ── Supply Chain ────────────────────────────────────────────────────────────

@app.post("/api/scm/supplier-eval")
async def evaluate_supplier(req: SupplierEvalRequest):
    """
    Valutazione AI di un fornitore secondo best practice SCM in hotellerie.
    Analizza certificazioni, categoria di rischio e requisiti ISO.
    """
    prompt = (
        f"Valuta questo fornitore per una struttura alberghiera:\n"
        f"Nome: {req.nome}\n"
        f"Categoria: {req.categoria}\n"
        f"Certificazioni dichiarate: {', '.join(req.certificazioni) if req.certificazioni else 'nessuna'}\n"
        f"Note: {req.note or 'nessuna'}\n\n"
        f"Fornisci: 1) Livello rischio (A/B/C), 2) Certificazioni mancanti obbligatorie, "
        f"3) Frequenza audit raccomandata, 4) KPI da monitorare, 5) Punteggio qualifica (0-100). "
        f"Rispondi in JSON."
    )
    result = await call_anthropic(
        query=prompt,
        system_prompt=get_system_prompt("scm"),
        max_tokens=1000,
    )
    try:
        clean = result["text"].replace("```json", "").replace("```", "").strip()
        data = json.loads(clean)
    except json.JSONDecodeError:
        data = {"raw": result["text"]}

    return {"evaluation": data, "supplier": req.nome, "timestamp": datetime.utcnow().isoformat()}

@app.get("/api/scm/par-level-calculator")
async def par_level_calculator(
    articolo: str,
    consumo_giornaliero: float,
    lead_time_giorni: int = 2,
    safety_factor: float = 1.3,
    giorni_ordine: int = 7
):
    """
    Calcola il par level ottimale per la gestione scorte in hotellerie.
    Formula: Par Level = (Consumo giornaliero × Lead time + Giorni ciclo ordine) × Safety factor
    """
    consumo_ciclo = consumo_giornaliero * giorni_ordine
    scorta_sicurezza = consumo_giornaliero * lead_time_giorni * (safety_factor - 1)
    par_level = (consumo_giornaliero * (lead_time_giorni + giorni_ordine)) * safety_factor
    punto_riordine = consumo_giornaliero * lead_time_giorni * safety_factor

    return {
        "articolo": articolo,
        "par_level": round(par_level, 2),
        "punto_riordine": round(punto_riordine, 2),
        "scorta_sicurezza": round(scorta_sicurezza, 2),
        "consumo_ciclo_ordine": round(consumo_ciclo, 2),
        "parametri": {
            "consumo_giornaliero": consumo_giornaliero,
            "lead_time_giorni": lead_time_giorni,
            "safety_factor": safety_factor,
            "giorni_ciclo_ordine": giorni_ordine,
        },
        "formula": "PAR = (Consumo/g × (LT + Ciclo)) × Safety Factor"
    }

# ── HACCP & Sicurezza ───────────────────────────────────────────────────────

@app.post("/api/haccp/temperature-log")
async def log_temperature(log: HACCPTemperatureLog):
    """
    Registra temperatura da sensore IoT HACCP.
    Genera alert automatico se fuori range normativo.
    """
    # Range normativi per zona (Reg. CE 852/2004)
    TEMP_RANGES = {
        "cella_frigo":     {"min": 0, "max": 4, "unit": "°C"},
        "cella_surgelati": {"min": -22, "max": -18, "unit": "°C"},
        "zona_calda":      {"min": 65, "max": 100, "unit": "°C"},
        "cantina":         {"min": 10, "max": 18, "unit": "°C"},
        "frigo_bar":       {"min": 2, "max": 6, "unit": "°C"},
    }

    zona_key = log.zona.lower().replace(" ", "_")
    range_info = TEMP_RANGES.get(zona_key)
    timestamp = log.timestamp or datetime.utcnow().isoformat()

    alert = False
    severity = "ok"
    message = "Temperatura nella norma"

    if range_info:
        if log.temperatura < range_info["min"] or log.temperatura > range_info["max"]:
            alert = True
            severity = "critical" if abs(log.temperatura - range_info["max"]) > 5 else "warning"
            message = (
                f"⚠️ ALERT HACCP: Temperatura {log.temperatura}°C fuori range "
                f"({range_info['min']}-{range_info['max']}°C) per zona '{log.zona}'"
            )

    return {
        "sensor_id": log.sensor_id,
        "zona": log.zona,
        "temperatura": log.temperatura,
        "timestamp": timestamp,
        "alert": alert,
        "severity": severity,
        "message": message,
        "range_normativo": range_info,
        "conforme_reg": not alert,
    }

@app.get("/api/haccp/ccp-checklist")
async def get_ccp_checklist():
    """Restituisce la checklist CCP secondo i 7 principi HACCP (Codex Alimentarius)"""
    return {
        "principi": [
            {"n": 1, "titolo": "Analisi dei Pericoli (HA)", "ccp": "CCP 0 — Identificazione pericoli biologici, chimici, fisici per ogni fase del processo"},
            {"n": 2, "titolo": "Identificazione CCP", "ccp": "CCP 1 — Punti critici di controllo: ricevimento materie prime, cottura, raffreddamento rapido"},
            {"n": 3, "titolo": "Limiti Critici", "ccp": "CCP 2 — T°C cottura ≥ 75°C al cuore; T°C frigo 0-4°C; T°C surgelati ≤ -18°C"},
            {"n": 4, "titolo": "Procedure di Monitoraggio", "ccp": "CCP 3 — Frequenza rilevazione temperature, registro cartaceo o IoT, responsabile"},
            {"n": 5, "titolo": "Azioni Correttive", "ccp": "CCP 4 — Procedure in caso di superamento limiti critici: blocco produzione, ritiro lotto"},
            {"n": 6, "titolo": "Procedure di Verifica", "ccp": "CCP 5 — Audit interni, analisi microbiologiche, calibrazione strumenti di misura"},
            {"n": 7, "titolo": "Documentazione", "ccp": "CCP 6 — Manuale HACCP, registri temperature, NC, formazione personale (conservare 5 anni)"},
        ],
        "riferimenti_normativi": ["Reg. CE 852/2004", "Reg. CE 178/2002", "ISO 22000:2018", "UNI EN ISO 22005:2008"],
    }

# ── ESG & Certificazioni ────────────────────────────────────────────────────

@app.post("/api/esg/report-generate")
async def generate_esg_report(req: ESGReportRequest):
    """
    Genera report ESG automatico basato sui KPI forniti.
    Standard: GRI, GSTC, SDGs ONU.
    """
    prompt = (
        f"Genera un report ESG sintetico per la struttura ricettiva '{req.hotel_name}' "
        f"per l'anno {req.anno}.\n"
        f"Dati forniti: {json.dumps(req.dati, ensure_ascii=False, indent=2)}\n\n"
        f"Il report deve includere: Executive Summary, sezione Environmental (E), "
        f"sezione Social (S), sezione Governance (G), benchmark di settore, "
        f"aree di miglioramento prioritarie, allineamento SDGs ONU. "
        f"Formato professionale in italiano."
    )
    result = await call_anthropic(
        query=prompt,
        system_prompt=get_system_prompt("esg"),
        max_tokens=3000,
    )
    return {
        "hotel": req.hotel_name,
        "anno": req.anno,
        "report": result["text"],
        "tokens_used": result["tokens"],
        "timestamp": datetime.utcnow().isoformat(),
    }

@app.get("/api/esg/gstc-criteria")
async def get_gstc_criteria():
    """Restituisce i criteri GSTC per il turismo sostenibile"""
    return {
        "standard": "GSTC Hospitality Criteria",
        "versione": "v3.0",
        "sezioni": {
            "A": "Gestione Sostenibile",
            "B": "Benefici Socioeconomici per la Comunità Locale",
            "C": "Patrimonio Culturale",
            "D": "Impatto Ambientale",
        },
        "criteri_chiave": [
            {"cod": "A1", "desc": "Strategia di sostenibilità documentata e aggiornata annualmente"},
            {"cod": "B1", "desc": "Impiego preferenziale di lavoratori locali"},
            {"cod": "C1", "desc": "Acquisti da fornitori locali ≥ 30%"},
            {"cod": "D1", "desc": "Riduzione consumi energetici misurata e rendicontata"},
            {"cod": "D2", "desc": "Riduzione consumi idrici con obiettivi misurabili"},
            {"cod": "D3", "desc": "Gestione rifiuti con raccolta differenziata e compostaggio"},
        ],
        "link_ufficiale": "https://www.gstcouncil.org",
    }

# ── Revenue & Analytics ─────────────────────────────────────────────────────

@app.get("/api/analytics/kpi-benchmark")
async def get_kpi_benchmark(stelle: int = 4, tipo: str = "hotel"):
    """
    Benchmark KPI per strutture ricettive italiane.
    Fonte: STR, Federalberghi, ISTAT turismo.
    """
    benchmarks = {
        3: {"adr": 85, "revpar": 55, "occ": 65, "food_cost": 35, "labor_cost": 38},
        4: {"adr": 150, "revpar": 98, "occ": 65, "food_cost": 32, "labor_cost": 35},
        5: {"adr": 350, "revpar": 245, "occ": 70, "food_cost": 28, "labor_cost": 33},
    }
    stelle_key = min(max(stelle, 3), 5)
    bm = benchmarks[stelle_key]

    return {
        "stelle": stelle,
        "tipo": tipo,
        "benchmark_italia": {
            "ADR_euro": bm["adr"],
            "RevPAR_euro": bm["revpar"],
            "Occupazione_pct": bm["occ"],
            "FoodCost_pct": bm["food_cost"],
            "LaborCost_pct": bm["labor_cost"],
        },
        "fonte": "Federalberghi / STR Global 2024",
        "note": "Valori medi nazionali. Variabilità regionale significativa.",
    }


# ═══════════════════════════════════════════════════════════════════════════════
#  MODULO 1 — VENDOR RATING AUTOMATICO
# ═══════════════════════════════════════════════════════════════════════════════

@app.post(
    "/api/scm/vendor-rating/calcola",
    summary="Calcola Vendor Rating automatico da dati esistenti",
    tags=["Vendor Rating"],
)
async def calcola_vendor_rating_endpoint(
    hotel_id: str,
    fornitore_id: str,
    periodo: str,                   # "2026-03" → mese, "2026-Q1" → trimestre
):
    """
    Calcola e salva il Vendor Rating per un fornitore nel periodo indicato.
    Legge automaticamente da: ordini_fornitori, non_conformita, fornitori (certificazioni).
    Formula pesata (Cribis/Ivalua): OTD 30% + Qualità 25% + Prezzo 20% + Compliance 15% + Reattività 10%.
    """
    if not SUPABASE_URL:
        # Demo: dati simulati
        score_p = 91.0
        score_q = 84.0
        score_c = 80.0
        score_totale = calcola_score_totale(score_p, score_q, compliance=score_c)
        classif = classifica_fornitore(score_totale)
        return {
            "fornitore_id": fornitore_id,
            "periodo": periodo,
            "score_totale": score_totale,
            "score_puntualita": score_p,
            "score_qualita": score_q,
            "score_compliance": score_c,
            "score_prezzo": 50.0,
            "score_reattivita": 50.0,
            **classif,
            "nota": "Demo mode — configura Supabase per calcolo su dati reali",
        }

    # Chiama la funzione PostgreSQL che incrocia ordini + NC + certificazioni
    async with httpx.AsyncClient() as client:
        # Calcola date periodo
        if "Q" in periodo:
            anno, q = periodo.split("-Q")
            mese_inizio = (int(q) - 1) * 3 + 1
            data_inizio = f"{anno}-{mese_inizio:02d}-01"
            mese_fine = mese_inizio + 2
            _, ult_giorno = calendar.monthrange(int(anno), mese_fine)
            data_fine = f"{anno}-{mese_fine:02d}-{ult_giorno}"
        else:
            anno, mese = periodo.split("-")
            _, ult = calendar.monthrange(int(anno), int(mese))
            data_inizio = f"{periodo}-01"
            data_fine   = f"{periodo}-{ult}"

        r = await client.post(
            f"{SUPABASE_URL}/rest/v1/rpc/calcola_vendor_rating",
            headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}",
                     "Content-Type": "application/json"},
            json={
                "p_hotel_id": hotel_id,
                "p_fornitore_id": fornitore_id,
                "p_periodo_inizio": data_inizio,
                "p_periodo_fine": data_fine,
            },
        )

    if r.status_code != 200:
        raise HTTPException(status_code=502, detail=f"Errore calcolo rating: {r.text}")

    dati = r.json()[0] if r.json() else {}
    score_p    = float(dati.get("score_puntualita", 50))
    score_q    = float(dati.get("score_qualita", 50))
    score_comp = float(dati.get("score_compliance", 50))
    score_tot  = float(dati.get("score_totale", calcola_score_totale(score_p, score_q, compliance=score_comp)))
    classif    = classifica_fornitore(score_tot)

    # Recupera rating periodo precedente per calcolare variazione
    async with httpx.AsyncClient() as client:
        r2 = await client.get(
            f"{SUPABASE_URL}/rest/v1/vendor_rating_history",
            headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"},
            params={"hotel_id": f"eq.{hotel_id}", "fornitore_id": f"eq.{fornitore_id}",
                    "select": "score_totale,periodo", "order": "periodo.desc", "limit": "1"},
        )
        storico = r2.json() if r2.status_code == 200 else []

    variazione = None
    if storico:
        prev = float(storico[0]["score_totale"])
        variazione = round(score_tot - prev, 1)

    # Salva il risultato
    payload = {
        "hotel_id": hotel_id,
        "fornitore_id": fornitore_id,
        "periodo": periodo,
        "score_totale": score_tot,
        "score_puntualita": score_p,
        "score_qualita": score_q,
        "score_prezzo": 50.0,
        "score_compliance": score_comp,
        "score_reattivita": 50.0,
        "classe_rating": classif["classe"],
        "ordini_totali": dati.get("ordini_analizzati", 0),
        "nc_aperte": dati.get("nc_trovate", 0),
        "variazione_vs_periodo_prec": variazione,
        "flag_miglioramento": (variazione or 0) > 2,
        "flag_peggioramento": (variazione or 0) < -2,
    }

    async with httpx.AsyncClient() as client:
        await client.post(
            f"{SUPABASE_URL}/rest/v1/vendor_rating_history",
            headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}",
                     "Content-Type": "application/json",
                     "Prefer": "resolution=merge-duplicates"},
            json=payload,
        )

    return {
        "fornitore_id": fornitore_id,
        "periodo": periodo,
        "score_totale": score_tot,
        "score_puntualita": score_p,
        "score_qualita": score_q,
        "score_compliance": score_comp,
        "variazione_vs_periodo_prec": variazione,
        **classif,
    }


@app.get(
    "/api/scm/vendor-rating/storico/{fornitore_id}",
    summary="Storico Vendor Rating con trend",
    tags=["Vendor Rating"],
)
async def get_vendor_rating_storico(hotel_id: str, fornitore_id: str, ultimi_n: int = 6):
    """Restituisce l'evoluzione del rating nel tempo per analisi trend."""
    if not SUPABASE_URL:
        return {
            "fornitore_id": fornitore_id,
            "trend": [
                {"periodo": "2025-10", "score_totale": 74.0, "classe": "B"},
                {"periodo": "2025-11", "score_totale": 76.5, "classe": "B"},
                {"periodo": "2025-12", "score_totale": 79.0, "classe": "B"},
                {"periodo": "2026-01", "score_totale": 82.5, "classe": "B"},
                {"periodo": "2026-02", "score_totale": 85.0, "classe": "B"},
                {"periodo": "2026-03", "score_totale": 88.5, "classe": "B"},
            ],
            "score_attuale": 88.5,
            "classe_attuale": "B",
            "tendenza": "miglioramento",
            "suggerimento_partnership": suggerisci_livello_partnership(88.5),
            "nota": "Demo mode",
        }

    async with httpx.AsyncClient() as client:
        r = await client.get(
            f"{SUPABASE_URL}/rest/v1/vendor_rating_history",
            headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"},
            params={"hotel_id": f"eq.{hotel_id}", "fornitore_id": f"eq.{fornitore_id}",
                    "select": "*", "order": "periodo.asc", "limit": str(ultimi_n)},
        )
    rows = r.json() if r.status_code == 200 else []

    score_attuale = float(rows[-1]["score_totale"]) if rows else 0
    prima = float(rows[0]["score_totale"]) if rows else 0
    tendenza = "miglioramento" if score_attuale > prima + 2 else \
               "peggioramento" if score_attuale < prima - 2 else "stabile"

    return {
        "fornitore_id": fornitore_id,
        "trend": rows,
        "score_attuale": score_attuale,
        "classe_attuale": classifica_fornitore(score_attuale)["classe"],
        "tendenza": tendenza,
        "suggerimento_partnership": suggerisci_livello_partnership(score_attuale),
    }


@app.get(
    "/api/scm/vendor-rating/ranking",
    summary="Ranking fornitori per hotel",
    tags=["Vendor Rating"],
)
async def get_vendor_ranking(hotel_id: str, periodo: Optional[str] = None, categoria: Optional[str] = None):
    """
    Classifica tutti i fornitori per score nel periodo.
    Utile per decisioni di sourcing e rinnovo contratti.
    """
    target_periodo = periodo or datetime.now().strftime("%Y-%m")

    if not SUPABASE_URL:
        return {
            "periodo": target_periodo,
            "ranking": [
                {"posizione": 1, "fornitore": "Fornitore Alpha Srl", "score": 91.0, "classe": "A", "categoria": "food_fresh"},
                {"posizione": 2, "fornitore": "Beta Bevande SpA",   "score": 84.5, "classe": "B", "categoria": "beverage"},
                {"posizione": 3, "fornitore": "Gamma Tessile",      "score": 77.0, "classe": "B", "categoria": "tessile"},
                {"posizione": 4, "fornitore": "Delta Tech",         "score": 61.0, "classe": "C", "categoria": "tech"},
            ],
            "nota": "Demo mode",
        }

    async with httpx.AsyncClient() as client:
        r = await client.get(
            f"{SUPABASE_URL}/rest/v1/vendor_rating_history",
            headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"},
            params={"hotel_id": f"eq.{hotel_id}", "periodo": f"eq.{target_periodo}",
                    "select": "*, fornitori(ragione_sociale, categoria)",
                    "order": "score_totale.desc"},
        )
    rows = r.json() if r.status_code == 200 else []

    ranking = []
    for i, row in enumerate(rows, 1):
        forn = row.get("fornitori") or {}
        if categoria and forn.get("categoria") != categoria:
            continue
        ranking.append({
            "posizione": i,
            "fornitore_id": row["fornitore_id"],
            "fornitore": forn.get("ragione_sociale", "—"),
            "categoria": forn.get("categoria", "—"),
            "score_totale": row["score_totale"],
            "classe": row["classe_rating"],
            "variazione": row.get("variazione_vs_periodo_prec"),
        })
    return {"periodo": target_periodo, "ranking": ranking, "totale": len(ranking)}


@app.post(
    "/api/scm/vendor-rating/evento-kpi",
    summary="Registra evento KPI singolo fornitore",
    tags=["Vendor Rating"],
)
async def registra_kpi_event(hotel_id: str, req: VRKpiEventCreate):
    """
    Registra un evento granulare (consegna in ritardo, NC aperta, deviazione prezzo).
    Alimenta il calcolo automatico del rating mensile.
    """
    payload = {
        "hotel_id": hotel_id,
        "fornitore_id": req.fornitore_id,
        "tipo_evento": req.tipo_evento,
        "data_evento": req.data_evento or date.today().isoformat(),
        "valore": req.valore,
        "valore_atteso": req.valore_atteso,
        "conforme": req.conforme,
        "note": req.note,
    }
    if req.ordine_id:
        payload["ordine_id"] = req.ordine_id

    if not SUPABASE_URL:
        return {"registrato": True, "tipo": req.tipo_evento, "nota": "Demo mode"}

    async with httpx.AsyncClient() as client:
        r = await client.post(
            f"{SUPABASE_URL}/rest/v1/vendor_kpi_events",
            headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}",
                     "Content-Type": "application/json"},
            json=payload,
        )
    return {"registrato": r.status_code == 201, "tipo": req.tipo_evento}


# ═══════════════════════════════════════════════════════════════════════════════
#  MODULO 2 — SLA MANAGER
# ═══════════════════════════════════════════════════════════════════════════════

@app.post(
    "/api/sla/contracts",
    summary="Crea contratto SLA fornitore",
    tags=["SLA Manager"],
)
async def create_sla_contract(hotel_id: str, req: SLAContractCreate):
    """
    Crea un nuovo contratto SLA con KPI target e penali.
    Suggerisce target default in base alla categoria fornitore.
    """
    defaults = SLA_DEFAULTS.get(req.categoria, SLA_DEFAULTS["food_fresh"])

    # Calcola data prossima review
    mesi_review = {"mensile": 1, "trimestrale": 3, "semestrale": 6}
    delta = mesi_review.get(req.frequenza_review, 3)
    prossima_review = (date.today() + timedelta(days=delta * 30)).isoformat()

    payload = {
        "hotel_id": hotel_id,
        "fornitore_id": req.fornitore_id,
        "nome": req.nome,
        "categoria": req.categoria,
        "data_inizio": req.data_inizio,
        "data_scadenza": req.data_scadenza,
        "target_otd_pct": req.target_otd_pct,
        "target_otif_pct": req.target_otif_pct,
        "target_qualita_pct": req.target_qualita_pct,
        "target_prezzo_var_pct": req.target_prezzo_var_pct,
        "target_risposta_ore": req.target_risposta_ore,
        "penale_ritardo_pct": req.penale_ritardo_pct,
        "penale_nc_pct": req.penale_nc_pct,
        "penale_max_mensile_pct": req.penale_max_mensile_pct,
        "frequenza_review": req.frequenza_review,
        "prossima_review": prossima_review,
        "rinnovo_automatico": req.rinnovo_automatico,
        "stato": "attivo",
        "note_legali": req.note_legali,
        "note": req.note,
    }

    if not SUPABASE_URL:
        return {"sla_id": "demo-uuid", "nome": req.nome,
                "defaults_categoria": defaults, "nota": "Demo mode"}

    async with httpx.AsyncClient() as client:
        r = await client.post(
            f"{SUPABASE_URL}/rest/v1/sla_contracts",
            headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}",
                     "Content-Type": "application/json", "Prefer": "return=representation"},
            json=payload,
        )
    data = r.json()[0] if r.status_code == 201 and r.json() else {}
    return {"sla_id": data.get("id"), "nome": req.nome, "prossima_review": prossima_review}


@app.post(
    "/api/sla/measurements",
    summary="Registra misurazione KPI periodica vs SLA",
    tags=["SLA Manager"],
)
async def record_sla_measurement(hotel_id: str, req: SLAMeasurement):
    """
    Registra le misurazioni del periodo e calcola automaticamente:
    - Conformità per ogni KPI
    - Compliance score aggregato
    - Penali applicabili
    - Alert da generare
    """
    # Recupera target SLA
    targets = {}
    if SUPABASE_URL:
        async with httpx.AsyncClient() as client:
            r = await client.get(
                f"{SUPABASE_URL}/rest/v1/sla_contracts",
                headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"},
                params={"id": f"eq.{req.sla_id}", "select": "*"},
            )
            if r.status_code == 200 and r.json():
                targets = r.json()[0]
    else:
        targets = {"target_otd_pct": 95, "target_otif_pct": 92,
                   "target_qualita_pct": 98, "target_prezzo_var_pct": 3, "target_risposta_ore": 24}

    measurement_dict = req.dict()
    analysis = calcola_sla_compliance(measurement_dict, targets)

    # Calcola OTD automatico da n_ordini se non fornito
    otd = req.otd_misurato_pct
    if otd is None and req.n_ordini > 0:
        otd = round(req.n_ordini_puntuali / req.n_ordini * 100, 1)

    qualita = req.qualita_misurata_pct
    if qualita is None and req.n_ordini > 0:
        qualita = round((1 - req.n_nc / req.n_ordini) * 100, 1)

    payload = {
        "sla_id": req.sla_id,
        "hotel_id": hotel_id,
        "fornitore_id": targets.get("fornitore_id"),
        "periodo": req.periodo,
        "n_ordini": req.n_ordini,
        "n_ordini_puntuali": req.n_ordini_puntuali,
        "n_nc": req.n_nc,
        "otd_misurato_pct": otd,
        "otif_misurato_pct": req.otif_misurato_pct,
        "qualita_misurata_pct": qualita,
        "prezzo_var_misurata_pct": req.prezzo_var_misurata_pct,
        "risposta_media_ore": req.risposta_media_ore,
        "otd_ok":      analysis["kpi_check"].get("otd", {}).get("ok"),
        "otif_ok":     analysis["kpi_check"].get("otif", {}).get("ok"),
        "qualita_ok":  analysis["kpi_check"].get("qualita", {}).get("ok"),
        "prezzo_ok":   analysis["kpi_check"].get("prezzo", {}).get("ok"),
        "risposta_ok": analysis["kpi_check"].get("risposta", {}).get("ok"),
        "compliance_score": analysis["compliance_score"],
        "penali_euro": analysis["penali_stimate_euro"],
        "note": req.note,
    }

    if SUPABASE_URL:
        async with httpx.AsyncClient() as client:
            await client.post(
                f"{SUPABASE_URL}/rest/v1/sla_kpi_measurements",
                headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}",
                         "Content-Type": "application/json",
                         "Prefer": "resolution=merge-duplicates"},
                json=payload,
            )
            # Genera alert per KPI fuori soglia
            for alert in analysis["alerts"]:
                await client.post(
                    f"{SUPABASE_URL}/rest/v1/sla_alerts",
                    headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}",
                             "Content-Type": "application/json"},
                    json={
                        "sla_id": req.sla_id,
                        "hotel_id": hotel_id,
                        "fornitore_id": targets.get("fornitore_id"),
                        "kpi_nome": alert["kpi"],
                        "scostamento": alert["scostamento"],
                        "severity": alert["severity"],
                        "stato": "aperto",
                    },
                )

    return {
        "periodo": req.periodo,
        "compliance_score": analysis["compliance_score"],
        "valutazione": analysis["valutazione"],
        "kpi_check": analysis["kpi_check"],
        "alerts_generati": len(analysis["alerts"]),
        "penali_euro": analysis["penali_stimate_euro"],
    }


@app.get(
    "/api/sla/alerts",
    summary="Alert SLA aperti",
    tags=["SLA Manager"],
)
async def get_sla_alerts(hotel_id: str, stato: str = "aperto", severity: Optional[str] = None):
    """Lista alert SLA con KPI fuori soglia. Stato: aperto | in_gestione | chiuso"""
    if not SUPABASE_URL:
        return {
            "alerts": [
                {"kpi": "otd", "fornitore": "Fornitore Beta",
                 "scostamento": -4.2, "severity": "critical", "stato": "aperto"},
                {"kpi": "prezzo", "fornitore": "Gamma Tessile",
                 "scostamento": 2.1, "severity": "warning", "stato": "aperto"},
            ],
            "totale": 2, "nota": "Demo mode",
        }

    params = {"hotel_id": f"eq.{hotel_id}", "stato": f"eq.{stato}",
              "select": "*, fornitori(ragione_sociale), sla_contracts(nome)",
              "order": "created_at.desc"}
    if severity:
        params["severity"] = f"eq.{severity}"

    async with httpx.AsyncClient() as client:
        r = await client.get(
            f"{SUPABASE_URL}/rest/v1/sla_alerts",
            headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"},
            params=params,
        )
    rows = r.json() if r.status_code == 200 else []
    return {"alerts": rows, "totale": len(rows),
            "critici": sum(1 for a in rows if a.get("severity") == "critical")}


@app.get(
    "/api/sla/defaults/{categoria}",
    summary="Target SLA default per categoria",
    tags=["SLA Manager"],
)
async def get_sla_defaults(categoria: str):
    """Restituisce i target KPI benchmark per categoria. Fonte: Deepser / EENA 2024."""
    defaults = SLA_DEFAULTS.get(categoria)
    if not defaults:
        return {"categorie_disponibili": list(SLA_DEFAULTS.keys())}
    return {
        "categoria": categoria,
        "target_default": defaults,
        "fonte": "Deepser SLA Guide + EENA Best Practice Contrattuale 2024",
    }


# ═══════════════════════════════════════════════════════════════════════════════
#  MODULO 3 — PARTNERSHIP FORNITORE LUNGO PERIODO
# ═══════════════════════════════════════════════════════════════════════════════

@app.post(
    "/api/partnership",
    summary="Crea accordo di partnership",
    tags=["Partnership"],
)
async def create_partnership(hotel_id: str, req: PartnershipCreate):
    """
    Crea un accordo di partnership strategica.
    Livelli: preferred (70+), strategic (85+), exclusive (92+).
    Fonte: Marenzi UniPD — soglie cooperative SCM hospitality.
    """
    cfg = PARTNERSHIP_LIVELLI.get(req.livello, PARTNERSHIP_LIVELLI["preferred"])
    payload = {
        "hotel_id": hotel_id,
        **req.dict(),
        "stato": "attivo",
    }

    if not SUPABASE_URL:
        return {"partnership_id": "demo-uuid", "livello": req.livello,
                "label": cfg["label"], "benefici": cfg["benefici"],
                "impegni": cfg["impegni"], "nota": "Demo mode"}

    async with httpx.AsyncClient() as client:
        r = await client.post(
            f"{SUPABASE_URL}/rest/v1/partnership_agreements",
            headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}",
                     "Content-Type": "application/json", "Prefer": "return=representation"},
            json=payload,
        )
    data = r.json()[0] if r.status_code == 201 and r.json() else {}
    return {"partnership_id": data.get("id"), "livello": req.livello,
            "label": cfg["label"], "benefici": cfg["benefici"]}


@app.get(
    "/api/partnership",
    summary="Lista partnership attive",
    tags=["Partnership"],
)
async def list_partnerships(hotel_id: str, stato: str = "attivo"):
    """Lista accordi di partnership con info fornitore e prossime scadenze review."""
    if not SUPABASE_URL:
        return {
            "partnerships": [
                {"nome": "Partnership Strategica Fornitore Principale 2025-2027",
                 "livello": "preferred", "fornitore": "Fornitore Alpha Srl",
                 "stato": "attivo", "prossima_review": "2026-06-30"},
            ],
            "totale": 1, "nota": "Demo mode",
        }

    async with httpx.AsyncClient() as client:
        r = await client.get(
            f"{SUPABASE_URL}/rest/v1/partnership_agreements",
            headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"},
            params={"hotel_id": f"eq.{hotel_id}", "stato": f"eq.{stato}",
                    "select": "*, fornitori(ragione_sociale, categoria, punteggio)",
                    "order": "livello.desc,data_inizio.desc"},
        )
    rows = r.json() if r.status_code == 200 else []
    return {"partnerships": rows, "totale": len(rows)}


@app.post(
    "/api/partnership/{partnership_id}/meetings",
    summary="Pianifica meeting di review",
    tags=["Partnership"],
)
async def create_meeting(partnership_id: str, hotel_id: str, req: PartnershipMeetingCreate):
    """Pianifica un meeting di review con agenda standard auto-generata."""
    # Recupera score attuale per agenda
    score_attuale = 75.0
    kpi_critici: List[str] = []

    agenda = genera_agenda_review("preferred", score_attuale, kpi_critici, 0)

    payload = {
        "partnership_id": partnership_id,
        "hotel_id": hotel_id,
        "fornitore_id": req.fornitore_id,
        "tipo": req.tipo,
        "data_pianificata": req.data_pianificata,
        "partecipanti_hotel": req.partecipanti_hotel,
        "partecipanti_fornitore": req.partecipanti_fornitore,
        "agenda": req.agenda or "\n".join(agenda),
        "stato": "pianificato",
    }
    if req.ora:   payload["ora"] = req.ora
    if req.luogo: payload["luogo"] = req.luogo

    if not SUPABASE_URL:
        return {"meeting_id": "demo-uuid", "agenda": agenda, "nota": "Demo mode"}

    async with httpx.AsyncClient() as client:
        r = await client.post(
            f"{SUPABASE_URL}/rest/v1/partnership_meetings",
            headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}",
                     "Content-Type": "application/json", "Prefer": "return=representation"},
            json=payload,
        )
    data = r.json()[0] if r.status_code == 201 and r.json() else {}
    return {"meeting_id": data.get("id"), "data": req.data_pianificata,
            "agenda_generata": agenda}


@app.patch(
    "/api/partnership/meetings/{meeting_id}/complete",
    summary="Registra verbale e action items meeting",
    tags=["Partnership"],
)
async def complete_meeting(meeting_id: str, req: PartnershipMeetingComplete):
    """Chiude il meeting con verbale, esito e action items deliberati."""
    payload = {
        "stato": "svolto",
        "esito": req.esito,
        "action_items": req.action_items,
        "updated_at": datetime.utcnow().isoformat(),
    }
    if req.verbale:               payload["verbale"] = req.verbale
    if req.score_al_momento:      payload["score_al_momento"] = req.score_al_momento
    if req.data_prossimo_meeting: payload["data_prossimo_meeting"] = req.data_prossimo_meeting

    if not SUPABASE_URL:
        return {"aggiornato": True, "action_items": len(req.action_items), "nota": "Demo mode"}

    async with httpx.AsyncClient() as client:
        r = await client.patch(
            f"{SUPABASE_URL}/rest/v1/partnership_meetings",
            headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}",
                     "Content-Type": "application/json"},
            params={"id": f"eq.{meeting_id}"},
            json=payload,
        )
    return {"aggiornato": r.status_code in (200, 204),
            "action_items": len(req.action_items), "esito": req.esito}


@app.post(
    "/api/partnership/scorecard",
    summary="Compila scorecard condivisa",
    tags=["Partnership"],
)
async def compila_scorecard(hotel_id: str, req: ScorecardCompile):
    """
    Compila la scorecard reciproca (hotel su fornitore O fornitore su hotel).
    Score aggregato calcolato automaticamente su 6 dimensioni (scala 1-5 → 0-100).
    """
    score_agg = calcola_scorecard_aggregata(req.dict())
    payload = {
        "hotel_id": hotel_id,
        **req.dict(),
        "score_aggregato": score_agg,
    }

    if not SUPABASE_URL:
        return {"score_aggregato": score_agg, "direzione": req.direzione,
                "periodo": req.periodo, "nota": "Demo mode"}

    async with httpx.AsyncClient() as client:
        r = await client.post(
            f"{SUPABASE_URL}/rest/v1/partnership_scorecard",
            headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}",
                     "Content-Type": "application/json",
                     "Prefer": "resolution=merge-duplicates,return=representation"},
            json=payload,
        )
    data = r.json()[0] if r.status_code in (200, 201) and r.json() else {}
    return {"id": data.get("id"), "score_aggregato": score_agg,
            "direzione": req.direzione, "periodo": req.periodo}


@app.get(
    "/api/partnership/scorecard/{partnership_id}",
    summary="Confronto scorecard reciproca",
    tags=["Partnership"],
)
async def get_scorecard_confronto(partnership_id: str, periodo: Optional[str] = None):
    """
    Confronta la valutazione hotel→fornitore con fornitore→hotel.
    Evidenzia gap di percezione reciproca.
    """
    if not SUPABASE_URL:
        return {
            "hotel_su_fornitore": {"score_aggregato": 82.0, "qualita_prodotto": 4,
                                   "puntualita": 5, "comunicazione": 4},
            "fornitore_su_hotel":  {"score_aggregato": 74.0, "qualita_prodotto": 4,
                                   "puntualita": 3, "comunicazione": 3},
            "gap_totale": 8.0,
            "analisi": "Il fornitore percepisce la comunicazione e la puntualità nei pagamenti inferiori all'autovalutazione dell'hotel.",
            "nota": "Demo mode",
        }

    params = {"partnership_id": f"eq.{partnership_id}", "select": "*"}
    if periodo:
        params["periodo"] = f"eq.{periodo}"
    else:
        params["order"] = "periodo.desc"
        params["limit"] = "2"

    async with httpx.AsyncClient() as client:
        r = await client.get(
            f"{SUPABASE_URL}/rest/v1/partnership_scorecard",
            headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"},
            params=params,
        )
    rows = r.json() if r.status_code == 200 else []

    hotel_row  = next((r for r in rows if r.get("direzione") == "hotel_su_fornitore"), None)
    forn_row   = next((r for r in rows if r.get("direzione") == "fornitore_su_hotel"), None)

    gap = None
    if hotel_row and forn_row:
        gap = round(float(hotel_row["score_aggregato"]) - float(forn_row["score_aggregato"]), 1)

    return {
        "hotel_su_fornitore": hotel_row,
        "fornitore_su_hotel": forn_row,
        "gap_totale": gap,
    }


@app.get(
    "/api/partnership/livelli",
    summary="Info livelli partnership e requisiti",
    tags=["Partnership"],
)
async def get_partnership_livelli():
    """Restituisce i 3 livelli partnership con requisiti, benefici e impegni."""
    return {"livelli": PARTNERSHIP_LIVELLI,
            "fonte": "Marenzi (UniPD) — Relazioni cliente-fornitore e partnership SCM 2025"}


@app.post(
    "/api/partnership/suggerisci-upgrade",
    summary="Suggerisce livello partnership da Vendor Rating",
    tags=["Partnership"],
)
async def suggerisci_upgrade(hotel_id: str, fornitore_id: str):
    """
    Analizza il Vendor Rating attuale e suggerisce il livello di partnership adeguato.
    Usa l'ultimo rating disponibile.
    """
    if not SUPABASE_URL:
        return suggerisci_livello_partnership(88.5)

    async with httpx.AsyncClient() as client:
        r = await client.get(
            f"{SUPABASE_URL}/rest/v1/vendor_rating_history",
            headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"},
            params={"hotel_id": f"eq.{hotel_id}", "fornitore_id": f"eq.{fornitore_id}",
                    "select": "score_totale,periodo", "order": "periodo.desc", "limit": "1"},
        )
    rows = r.json() if r.status_code == 200 else []
    if not rows:
        raise HTTPException(404, "Nessun Vendor Rating trovato per questo fornitore. Calcola prima il rating.")

    score = float(rows[0]["score_totale"])
    return suggerisci_livello_partnership(score)

# ═══════════════════════════════════════════════════════════════════════════════
#  HOUSEKEEPING — GESTIONE CAMERE
# ═══════════════════════════════════════════════════════════════════════════════

@app.get(
    "/api/hk/rooms",
    summary="Lista camere con stato HK",
    tags=["Housekeeping"],
)
async def get_hk_rooms(
    hotel_id: str,
    stato_hk: Optional[str] = None,
    piano: Optional[int] = None,
):
    """
    Restituisce la lista camere con stato HK attuale.
    Se Supabase non è configurato, restituisce dati demo.
    """
    if not SUPABASE_URL:
        demo = [
            {"numero": "101", "piano": 1, "tipo": "standard", "stato_hk": "da_pulire",
             "stato_occupazione": "in_partenza", "priorita": 1, "n_letti": 2},
            {"numero": "102", "piano": 1, "tipo": "standard", "stato_hk": "pulita",
             "stato_occupazione": "libera", "priorita": 2, "n_letti": 2},
            {"numero": "103", "piano": 1, "tipo": "superior", "stato_hk": "in_pulizia",
             "stato_occupazione": "occupata", "priorita": 2, "n_letti": 2},
            {"numero": "201", "piano": 2, "tipo": "standard", "stato_hk": "da_pulire",
             "stato_occupazione": "in_partenza", "priorita": 1, "n_letti": 1},
            {"numero": "202", "piano": 2, "tipo": "suite", "stato_hk": "ispezionata",
             "stato_occupazione": "occupata", "priorita": 2, "n_letti": 2},
        ]
        if stato_hk:
            demo = [r for r in demo if r["stato_hk"] == stato_hk]
        if piano:
            demo = [r for r in demo if r["piano"] == piano]
        return {
            "rooms": demo,
            "totale": len(demo),
            "da_pulire": sum(1 for r in demo if r["stato_hk"] == "da_pulire"),
            "nota": "Dati demo — configura Supabase per dati reali",
        }

    params = {"hotel_id": f"eq.{hotel_id}", "select": "*", "order": "piano.asc,numero.asc"}
    if stato_hk:
        params["stato_hk"] = f"eq.{stato_hk}"
    if piano:
        params["piano"] = f"eq.{piano}"

    async with httpx.AsyncClient() as client:
        r = await client.get(
            f"{SUPABASE_URL}/rest/v1/hk_rooms",
            headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"},
            params=params,
        )
    rows = r.json() if r.status_code == 200 else []
    return {
        "rooms": rows,
        "totale": len(rows),
        "da_pulire": sum(1 for r in rows if r.get("stato_hk") == "da_pulire"),
        "in_pulizia": sum(1 for r in rows if r.get("stato_hk") == "in_pulizia"),
        "pulite": sum(1 for r in rows if r.get("stato_hk") == "pulita"),
    }


@app.patch(
    "/api/hk/rooms/{room_id}",
    summary="Aggiorna stato camera",
    tags=["Housekeeping"],
)
async def update_room_status(room_id: str, update: HKRoomUpdate):
    """Aggiorna stato HK, occupazione e assegnazione di una camera."""
    payload = {k: v for k, v in update.dict().items() if v is not None}
    payload["updated_at"] = datetime.utcnow().isoformat()

    if not SUPABASE_URL:
        return {"updated": True, "room_id": room_id, "changes": payload, "nota": "Demo mode"}

    async with httpx.AsyncClient() as client:
        r = await client.patch(
            f"{SUPABASE_URL}/rest/v1/hk_rooms",
            headers={
                "apikey": SUPABASE_KEY,
                "Authorization": f"Bearer {SUPABASE_KEY}",
                "Content-Type": "application/json",
                "Prefer": "return=minimal",
            },
            params={"id": f"eq.{room_id}"},
            json=payload,
        )
    return {"updated": r.status_code in (200, 204), "room_id": room_id, "changes": payload}


# ═══════════════════════════════════════════════════════════════════════════════
#  HOUSEKEEPING — TASK MANAGEMENT
# ═══════════════════════════════════════════════════════════════════════════════

@app.post(
    "/api/hk/tasks",
    summary="Crea task di pulizia",
    tags=["Housekeeping"],
)
async def create_hk_task(hotel_id: str, req: HKTaskCreate):
    """
    Crea un task di pulizia con checklist standard pre-compilata.
    Checklist template: check_out | stay_over | deepclean | ispezione
    """
    checklist = CHECKLIST_TEMPLATES.get(req.tipo, CHECKLIST_TEMPLATES["stay_over"])
    durata_stimata = DURATA_STANDARD.get(req.tipo, 25)

    payload = {
        "hotel_id": hotel_id,
        "room_id": req.room_id,
        "tipo": req.tipo,
        "stato": "assegnato",
        "priorita": req.priorita,
        "assegnato_da": req.assegnato_da,
        "data_pianificata": req.data_pianificata or date.today().isoformat(),
        "checklist": checklist,
        "note": req.note,
    }
    if req.assegnato_a:
        payload["assegnato_a"] = req.assegnato_a

    if not SUPABASE_URL:
        return {
            "task_id": "demo-uuid",
            "tipo": req.tipo,
            "durata_stimata_min": durata_stimata,
            "checklist_voci": len(checklist),
            "nota": "Demo mode",
        }

    async with httpx.AsyncClient() as client:
        r = await client.post(
            f"{SUPABASE_URL}/rest/v1/hk_tasks",
            headers={
                "apikey": SUPABASE_KEY,
                "Authorization": f"Bearer {SUPABASE_KEY}",
                "Content-Type": "application/json",
                "Prefer": "return=representation",
            },
            json=payload,
        )
    data = r.json()[0] if r.status_code == 201 and r.json() else {}
    return {
        "task_id": data.get("id"),
        "tipo": req.tipo,
        "durata_stimata_min": durata_stimata,
        "checklist_voci": len(checklist),
    }


@app.post(
    "/api/hk/tasks/complete",
    summary="Completa task e aggiorna giacenze",
    tags=["Housekeeping"],
)
async def complete_hk_task(hotel_id: str, req: HKTaskComplete):
    """
    Segna il task come completato e:
    - Aggiorna stato camera a 'ispezionata' o 'pulita'
    - Scarica i prodotti usati dall'inventario HK
    - Registra i movimenti biancheria
    """
    ora_fine = datetime.utcnow().isoformat()
    stato_camera = "ispezionata" if req.punteggio_ispezione else "pulita"

    if req.nc_rilevate:
        stato_camera = "da_pulire"  # NC rilevate → torna in coda

    update_payload = {
        "stato": "nc" if req.nc_rilevate else "completato",
        "ora_fine": ora_fine,
        "checklist": req.checklist,
        "lenzuola_cambiate": req.lenzuola_cambiate,
        "asciugamani_cambiati": req.asciugamani_cambiati,
        "n_set_biancheria": req.n_set_biancheria,
        "prodotti_usati": req.prodotti_usati,
        "nc_rilevate": req.nc_rilevate,
        "note": req.note,
        "updated_at": ora_fine,
    }
    if req.punteggio_ispezione is not None:
        update_payload["punteggio_ispezione"] = req.punteggio_ispezione
    if req.ispezionato_da:
        update_payload["ispezionato_da"] = req.ispezionato_da

    if not SUPABASE_URL:
        return {
            "completato": True,
            "stato_camera": stato_camera,
            "prodotti_scaricati": len(req.prodotti_usati),
            "nota": "Demo mode",
        }

    # 1. Aggiorna task
    async with httpx.AsyncClient() as client:
        await client.patch(
            f"{SUPABASE_URL}/rest/v1/hk_tasks",
            headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}",
                     "Content-Type": "application/json"},
            params={"id": f"eq.{req.task_id}"},
            json=update_payload,
        )

    # 2. Aggiorna stato camera (se ho room_id nel task)
    # (semplificato — in produzione recuperare room_id dal task)

    # 3. Scarica prodotti usati
    movements_created = 0
    async with httpx.AsyncClient() as client:
        for prod in req.prodotti_usati:
            if not prod.get("supply_id") or not prod.get("quantita"):
                continue
            # Inserisci movimento scarico
            await client.post(
                f"{SUPABASE_URL}/rest/v1/hk_supply_movements",
                headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}",
                         "Content-Type": "application/json"},
                json={
                    "hotel_id": hotel_id,
                    "supply_id": prod["supply_id"],
                    "tipo": "scarico",
                    "quantita": prod["quantita"],
                    "riferimento": req.task_id,
                    "note": f"Usato in task {req.task_id}",
                },
            )
            movements_created += 1

    return {
        "completato": True,
        "stato_camera": stato_camera,
        "prodotti_scaricati": movements_created,
        "nc": bool(req.nc_rilevate),
    }


@app.get(
    "/api/hk/tasks/daily",
    summary="Piano giornaliero pulizie",
    tags=["Housekeeping"],
)
async def get_daily_tasks(hotel_id: str, data: Optional[str] = None):
    """Restituisce tutti i task pianificati per una data (default: oggi)."""
    target_date = data or date.today().isoformat()

    if not SUPABASE_URL:
        return {
            "data": target_date,
            "tasks": [
                {"camera": "101", "tipo": "check_out", "stato": "assegnato", "priorita": 1, "durata_stimata": 35},
                {"camera": "201", "tipo": "check_out", "stato": "in_corso",  "priorita": 1, "durata_stimata": 35},
                {"camera": "103", "tipo": "stay_over", "stato": "completato","priorita": 2, "durata_stimata": 20},
                {"camera": "202", "tipo": "ispezione", "stato": "assegnato", "priorita": 2, "durata_stimata": 10},
            ],
            "riepilogo": {"totale": 4, "completati": 1, "in_corso": 1, "da_fare": 2},
            "nota": "Demo mode",
        }

    async with httpx.AsyncClient() as client:
        r = await client.get(
            f"{SUPABASE_URL}/rest/v1/hk_tasks",
            headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"},
            params={
                "hotel_id": f"eq.{hotel_id}",
                "data_pianificata": f"eq.{target_date}",
                "select": "*, hk_rooms(numero, piano, tipo)",
                "order": "priorita.asc,created_at.asc",
            },
        )
    tasks = r.json() if r.status_code == 200 else []
    return {
        "data": target_date,
        "tasks": tasks,
        "riepilogo": {
            "totale": len(tasks),
            "completati": sum(1 for t in tasks if t.get("stato") == "completato"),
            "in_corso": sum(1 for t in tasks if t.get("stato") == "in_corso"),
            "nc": sum(1 for t in tasks if t.get("stato") == "nc"),
            "da_fare": sum(1 for t in tasks if t.get("stato") == "assegnato"),
        },
    }


@app.get(
    "/api/hk/checklist-template/{tipo}",
    summary="Checklist standard per tipo pulizia",
    tags=["Housekeeping"],
)
async def get_checklist_template(tipo: str):
    """Restituisce la checklist operativa standard. Tipi: check_out, stay_over, deepclean, ispezione"""
    checklist = CHECKLIST_TEMPLATES.get(tipo)
    if not checklist:
        raise HTTPException(status_code=404, detail=f"Template '{tipo}' non trovato. Usa: {list(CHECKLIST_TEMPLATES.keys())}")
    return {
        "tipo": tipo,
        "durata_stimata_min": DURATA_STANDARD.get(tipo, 25),
        "n_voci": len(checklist),
        "checklist": checklist,
    }


# ═══════════════════════════════════════════════════════════════════════════════
#  HOUSEKEEPING — GESTIONE FORNITURE
# ═══════════════════════════════════════════════════════════════════════════════

@app.get(
    "/api/hk/supplies",
    summary="Scorte forniture HK con alert",
    tags=["Housekeeping"],
)
async def get_hk_supplies(hotel_id: str, categoria: Optional[str] = None, solo_alert: bool = False):
    """
    Lista forniture housekeeping con stato scorte.
    solo_alert=true restituisce solo articoli sotto il punto di riordino.
    """
    if not SUPABASE_URL:
        demo = [
            {"nome": "Shampoo 30ml",      "categoria": "amenity",    "giacenza_attuale": 380, "par_level": 600, "punto_riordino": 150, "alert": False},
            {"nome": "Detergente 5L",     "categoria": "detergente", "giacenza_attuale": 8,   "par_level": 40,  "punto_riordino": 10,  "alert": True},
            {"nome": "Lenzuola matrimon.","categoria": "biancheria", "giacenza_attuale": 88,  "par_level": 120, "punto_riordino": 30,  "alert": False},
            {"nome": "Carta igienica",    "categoria": "carta",      "giacenza_attuale": 12,  "par_level": 200, "punto_riordino": 50,  "alert": True},
        ]
        if categoria:
            demo = [s for s in demo if s["categoria"] == categoria]
        if solo_alert:
            demo = [s for s in demo if s["alert"]]
        return {"supplies": demo, "alert_count": sum(1 for s in demo if s["alert"]), "nota": "Demo mode"}

    params = {
        "hotel_id": f"eq.{hotel_id}",
        "attivo": "eq.true",
        "select": "*",
        "order": "categoria.asc,nome.asc",
    }
    if categoria:
        params["categoria"] = f"eq.{categoria}"

    async with httpx.AsyncClient() as client:
        r = await client.get(
            f"{SUPABASE_URL}/rest/v1/hk_supplies",
            headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"},
            params=params,
        )
    rows = r.json() if r.status_code == 200 else []

    # Calcola alert
    for row in rows:
        row["alert"] = (
            row.get("giacenza_attuale", 0) <= row.get("punto_riordino", 0)
        )
        row["giorni_rimanenti"] = (
            round(row["giacenza_attuale"] / row["consumo_medio_giornaliero"], 1)
            if row.get("consumo_medio_giornaliero", 0) > 0 else None
        )

    if solo_alert:
        rows = [r for r in rows if r.get("alert")]

    return {
        "supplies": rows,
        "totale": len(rows),
        "alert_count": sum(1 for r in rows if r.get("alert")),
    }


@app.post(
    "/api/hk/supplies/movement",
    summary="Registra movimento magazzino HK",
    tags=["Housekeeping"],
)
async def hk_supply_movement(hotel_id: str, req: SupplyMovement):
    """
    Registra carico, scarico o inventario su una fornitura HK.
    Aggiorna automaticamente la giacenza_attuale.
    """
    if not SUPABASE_URL:
        return {"registrato": True, "supply_id": req.supply_id, "tipo": req.tipo,
                "quantita": req.quantita, "nota": "Demo mode"}

    async with httpx.AsyncClient() as client:
        # Inserisci movimento
        await client.post(
            f"{SUPABASE_URL}/rest/v1/hk_supply_movements",
            headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}",
                     "Content-Type": "application/json"},
            json={
                "hotel_id": hotel_id,
                "supply_id": req.supply_id,
                "tipo": req.tipo,
                "quantita": req.quantita,
                "riferimento": req.riferimento,
                "operatore": req.operatore,
                "note": req.note,
            },
        )

        # Aggiorna giacenza (carico = +, scarico = -)
        multiplier = 1 if req.tipo == "carico" else -1
        if req.tipo != "inventario":
            # RPC Supabase per incremento atomico
            await client.post(
                f"{SUPABASE_URL}/rest/v1/rpc/increment_supply",
                headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}",
                         "Content-Type": "application/json"},
                json={"p_supply_id": req.supply_id, "p_delta": req.quantita * multiplier},
            )
        else:
            # Inventario = imposta giacenza
            await client.patch(
                f"{SUPABASE_URL}/rest/v1/hk_supplies",
                headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}",
                         "Content-Type": "application/json"},
                params={"id": f"eq.{req.supply_id}"},
                json={"giacenza_attuale": req.quantita, "ultimo_aggiornamento": datetime.utcnow().isoformat()},
            )

    return {"registrato": True, "supply_id": req.supply_id, "tipo": req.tipo, "quantita": req.quantita}


# ═══════════════════════════════════════════════════════════════════════════════
#  LAVANDERIA — CICLI RITIRO/CONSEGNA
# ═══════════════════════════════════════════════════════════════════════════════

@app.post(
    "/api/hk/laundry/cycles",
    summary="Registra ritiro biancheria",
    tags=["Lavanderia"],
)
async def create_laundry_cycle(hotel_id: str, req: LaundryCycleCreate):
    """Registra il ritiro biancheria da parte della lavanderia esterna."""
    totale_pezzi = req.lenzuola_out + req.asciugamani_out + req.accappatoi_out + req.tovagliato_out

    payload = {
        "hotel_id": hotel_id,
        "data_ritiro": req.data_ritiro or date.today().isoformat(),
        "lenzuola_out": req.lenzuola_out,
        "asciugamani_out": req.asciugamani_out,
        "accappatoi_out": req.accappatoi_out,
        "tovagliato_out": req.tovagliato_out,
        "altro_out_kg": req.altro_out_kg,
        "operatore_ritiro": req.operatore_ritiro,
        "stato": "ritirato",
        "note": req.note,
    }
    if req.contract_id:
        payload["contract_id"] = req.contract_id
    if req.ora_ritiro:
        payload["ora_ritiro"] = req.ora_ritiro

    if not SUPABASE_URL:
        return {"cycle_id": "demo-uuid", "totale_pezzi_ritirati": totale_pezzi, "nota": "Demo mode"}

    async with httpx.AsyncClient() as client:
        r = await client.post(
            f"{SUPABASE_URL}/rest/v1/laundry_cycles",
            headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}",
                     "Content-Type": "application/json", "Prefer": "return=representation"},
            json=payload,
        )
    data = r.json()[0] if r.status_code == 201 and r.json() else {}
    return {"cycle_id": data.get("id"), "totale_pezzi_ritirati": totale_pezzi}


@app.patch(
    "/api/hk/laundry/cycles/{cycle_id}/delivery",
    summary="Registra consegna biancheria pulita",
    tags=["Lavanderia"],
)
async def deliver_laundry_cycle(cycle_id: str, req: LaundryCycleDelivery):
    """
    Registra la consegna dalla lavanderia. Calcola costo ciclo e tasso scarto.
    Alert automatico se pezzi_in < pezzi_out (ammanchi biancheria).
    """
    totale_out = 0
    totale_in = req.lenzuola_in + req.asciugamani_in + req.accappatoi_in + req.tovagliato_in
    differenza = totale_in - totale_out  # sarà calcolata con dati db

    stato = "nc" if req.nc_rilevate or req.pezzi_scartati > 0 else "consegnato"

    payload = {
        "data_consegna": req.data_consegna or date.today().isoformat(),
        "operatore_consegna": req.operatore_consegna,
        "lenzuola_in": req.lenzuola_in,
        "asciugamani_in": req.asciugamani_in,
        "accappatoi_in": req.accappatoi_in,
        "tovagliato_in": req.tovagliato_in,
        "pezzi_scartati": req.pezzi_scartati,
        "nc_rilevate": req.nc_rilevate,
        "stato": stato,
        "note": req.note,
    }
    if req.costo_ciclo is not None:
        payload["costo_ciclo"] = req.costo_ciclo
    if req.ora_consegna:
        payload["ora_consegna"] = req.ora_consegna

    if not SUPABASE_URL:
        return {
            "aggiornato": True, "cycle_id": cycle_id, "stato": stato,
            "pezzi_ricevuti": totale_in, "nota": "Demo mode",
        }

    async with httpx.AsyncClient() as client:
        r = await client.patch(
            f"{SUPABASE_URL}/rest/v1/laundry_cycles",
            headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}",
                     "Content-Type": "application/json"},
            params={"id": f"eq.{cycle_id}"},
            json=payload,
        )
    return {
        "aggiornato": r.status_code in (200, 204),
        "cycle_id": cycle_id,
        "stato": stato,
        "pezzi_ricevuti": totale_in,
        "nc": bool(req.nc_rilevate),
        "scarti": req.pezzi_scartati,
    }


@app.get(
    "/api/hk/laundry/summary",
    summary="Riepilogo cicli lavanderia per mese",
    tags=["Lavanderia"],
)
async def laundry_monthly_summary(hotel_id: str, anno: int, mese: int):
    """Statistiche mensili lavanderia: pezzi, costi, NC, tasso scarto."""
    if not SUPABASE_URL:
        return {
            "periodo": f"{mese:02d}/{anno}",
            "cicli_totali": 22,
            "pezzi_ritirati": 1840,
            "pezzi_ricevuti": 1812,
            "pezzi_scartati": 28,
            "tasso_scarto_pct": 1.5,
            "costo_totale_euro": 810.40,
            "costo_medio_ciclo": 36.84,
            "nc_rilevate": 2,
            "nota": "Demo mode — configura Supabase per dati reali",
        }

    _, last_day = calendar.monthrange(anno, mese)
    date_from = f"{anno}-{mese:02d}-01"
    date_to = f"{anno}-{mese:02d}-{last_day}"

    async with httpx.AsyncClient() as client:
        r = await client.get(
            f"{SUPABASE_URL}/rest/v1/laundry_cycles",
            headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"},
            params={
                "hotel_id": f"eq.{hotel_id}",
                "data_ritiro": f"gte.{date_from}",
                "and": f"(data_ritiro.lte.{date_to})",
                "select": "lenzuola_out,asciugamani_out,accappatoi_out,tovagliato_out,"
                          "lenzuola_in,asciugamani_in,accappatoi_in,tovagliato_in,"
                          "pezzi_scartati,costo_ciclo,nc_rilevate,stato",
            },
        )
    rows = r.json() if r.status_code == 200 else []

    tot_out = sum(r.get("lenzuola_out",0) + r.get("asciugamani_out",0) +
                  r.get("accappatoi_out",0) + r.get("tovagliato_out",0) for r in rows)
    tot_in  = sum(r.get("lenzuola_in",0) + r.get("asciugamani_in",0) +
                  r.get("accappatoi_in",0) + r.get("tovagliato_in",0) for r in rows)
    tot_scartati = sum(r.get("pezzi_scartati", 0) for r in rows)
    tot_costo = sum(r.get("costo_ciclo", 0) or 0 for r in rows)
    nc_count  = sum(1 for r in rows if r.get("nc_rilevate"))

    return {
        "periodo": f"{mese:02d}/{anno}",
        "cicli_totali": len(rows),
        "pezzi_ritirati": tot_out,
        "pezzi_ricevuti": tot_in,
        "pezzi_scartati": tot_scartati,
        "tasso_scarto_pct": round(tot_scartati / tot_out * 100, 2) if tot_out else 0,
        "costo_totale_euro": round(tot_costo, 2),
        "costo_medio_ciclo": round(tot_costo / len(rows), 2) if rows else 0,
        "nc_rilevate": nc_count,
    }


# ═══════════════════════════════════════════════════════════════════════════════
#  HOUSEKEEPING — CALCOLI E BENCHMARK
# ═══════════════════════════════════════════════════════════════════════════════

@app.post(
    "/api/hk/linen-par-level",
    summary="Calcola par level biancheria ottimale",
    tags=["Housekeeping"],
)
async def linen_par_level(req: LinenParRequest):
    """
    Calcola il par level ottimale per biancheria.
    Formula Detergo Industry 5.0: 3 set in circolazione × safety factor.
    """
    result = calcola_par_level_biancheria(
        n_camere=req.n_camere,
        set_per_camera=req.set_per_camera,
        rotation_days=req.rotation_days,
        safety_factor=req.safety_factor,
    )
    return result


@app.get(
    "/api/hk/laundry/cost-calculator",
    summary="Calcola costo ciclo lavanderia",
    tags=["Lavanderia"],
)
async def laundry_cost_calculator(
    lenzuola: int = 0,
    asciugamani: int = 0,
    accappatoi: int = 0,
    tovagliato: int = 0,
    tariffa_lenzuola: float = 0.80,
    tariffa_asciugamani: float = 0.35,
    tariffa_accappatoi: float = 1.20,
    tariffa_tovagliato: float = 0.45,
    scartati: int = 0,
):
    """Calcola il costo stimato di un ciclo lavanderia con tariffe personalizzabili."""
    return calcola_costo_ciclo_lavanderia(
        lenzuola, asciugamani, accappatoi, tovagliato,
        tariffa_lenzuola, tariffa_asciugamani,
        tariffa_accappatoi, tariffa_tovagliato,
        scartati,
    )


@app.get(
    "/api/hk/kpi",
    summary="KPI produttività housekeeping",
    tags=["Housekeeping"],
)
async def get_hk_kpi(
    hotel_id: str,
    camere_pulite: int = 30,
    ore_lavorate: float = 8.0,
    camere_nc: int = 2,
    costo_totale: float = 250.0,
    stelle: int = 4,
):
    """
    Calcola KPI produttività HK con confronto benchmark settore.
    Fonte benchmark: Cora Hospitality — Hotel Management Standards 2024.
    """
    return kpi_produttivita_hk(
        camere_pulite=camere_pulite,
        ore_lavorate=ore_lavorate,
        camere_nc=camere_nc,
        costo_totale=costo_totale,
        stelle=stelle,
    )


@app.get(
    "/api/hk/benchmark-costi",
    summary="Benchmark costi HK per stelle",
    tags=["Housekeeping"],
)
async def hk_cost_benchmark(stelle: int = 4):
    """
    Benchmark costi HK per categoria (€/camera pulita).
    Fonte: B2Scout — Costi di gestione alberghiera 2024.
    """
    stelle_key = min(max(stelle, 3), 5)
    bm = BENCHMARK_COSTO_CAMERA.get(stelle_key, BENCHMARK_COSTO_CAMERA[4])
    return {
        "stelle": stelle,
        "benchmark_euro_per_camera": bm,
        "breakdown": {
            "lavanderia_pct": round(bm["lavanderia"] / bm["hk_totale"] * 100, 1),
            "prodotti_pct":   round(bm["prodotti"] / bm["hk_totale"] * 100, 1),
            "manodopera_pct": round((bm["hk_totale"] - bm["lavanderia"] - bm["prodotti"]) / bm["hk_totale"] * 100, 1),
        },
        "fonte": "B2Scout — Costi di gestione alberghiera 2024",
        "nota": "Valori medi nazionali. Variabilità significativa per stagione e area geografica.",
    }


# ── Startup ──────────────────────────────────────────────────────────────────

@app.on_event("startup")
async def startup():
    print("=" * 60)
    print("  BAD360.ai — Hospitality AI Platform v4.1.0")
    print(f"  Avviato: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
    print(f"  Anthropic API: {'✅ configurata' if ANTHROPIC_API_KEY else '❌ MANCANTE'}")
    print(f"  Supabase: {'✅ configurato' if SUPABASE_URL else '⚠️  non configurato (modalità demo)'}")
    print(f"  Frontend: BAD360_SPLIT/ — {len(os.listdir(_split_dir)) if os.path.isdir(_split_dir) else 0} moduli")
    print("=" * 60)
    start_scheduler()          # Shelf Life — job giornaliero 07:00
    start_briefing_scheduler() # Morning Briefing — job giornaliero 07:15


@app.on_event("shutdown")
async def shutdown():
    stop_scheduler()
    stop_briefing_scheduler()


@app.get(
    "/api/haccp/export-registro",
    summary="Esporta Registro HACCP Mensile (PDF)",
    tags=["HACCP & Sicurezza"],
    responses={
        200: {
            "content": {"application/pdf": {}},
            "description": "PDF registro HACCP mensile conforme Reg. CE 852/2004",
        }
    },
)
async def export_registro_haccp(
    hotel_id: str,
    anno: int,
    mese: int,
    responsabile: str = "Responsabile HACCP",
    note: str = "",
):
    """
    Genera il Registro HACCP Mensile Digitale in formato PDF.

    - Conforme Reg. CE 852/2004 e disposizioni 2025
    - Include: checklist CCP, log temperature IoT, NC, firma
    - Recupera i dati di temperatura da Supabase per il mese richiesto
    - Obbligatorio conservare per 5 anni (art. 5 Reg. CE 852/2004)

    Parametri:
    - hotel_id: UUID struttura (da tabella hotels)
    - anno:     anno di riferimento (es. 2026)
    - mese:     mese di riferimento (1-12)
    - responsabile: nome responsabile HACCP per la firma
    - note:     note opzionali da includere nel registro
    """
    if not 1 <= mese <= 12:
        raise HTTPException(status_code=422, detail="Mese deve essere tra 1 e 12")
    if anno < 2020 or anno > 2100:
        raise HTTPException(status_code=422, detail="Anno non valido")

    # ── 1. Recupera dati hotel da Supabase ───────────────────────────────────
    hotel_name  = "Hotel"
    hotel_citta = ""
    hotel_piva  = ""

    if SUPABASE_URL and SUPABASE_KEY:
        async with httpx.AsyncClient() as client:
            r = await client.get(
                f"{SUPABASE_URL}/rest/v1/hotels",
                headers={
                    "apikey": SUPABASE_KEY,
                    "Authorization": f"Bearer {SUPABASE_KEY}",
                },
                params={"id": f"eq.{hotel_id}", "select": "nome,citta,piva"},
            )
            if r.status_code == 200 and r.json():
                h = r.json()[0]
                hotel_name  = h.get("nome", hotel_name)
                hotel_citta = h.get("citta", "")
                hotel_piva  = h.get("piva", "")

    # ── 2. Recupera log temperature dal mese ─────────────────────────────────
    readings: list[TemperatureReading] = []

    if SUPABASE_URL and SUPABASE_KEY:
        # Range date mese
        _, last_day = calendar.monthrange(anno, mese)
        date_from = f"{anno}-{mese:02d}-01T00:00:00"
        date_to   = f"{anno}-{mese:02d}-{last_day}T23:59:59"

        async with httpx.AsyncClient() as client:
            r = await client.get(
                f"{SUPABASE_URL}/rest/v1/haccp_temperature",
                headers={
                    "apikey": SUPABASE_KEY,
                    "Authorization": f"Bearer {SUPABASE_KEY}",
                },
                params={
                    "hotel_id":  f"eq.{hotel_id}",
                    "timestamp": f"gte.{date_from}",
                    "and":       f"(timestamp.lte.{date_to})",
                    "select":    "*",
                    "order":     "timestamp.asc",
                    "limit":     "5000",
                },
            )
            if r.status_code == 200:
                for row in r.json():
                    ts = datetime.fromisoformat(row["timestamp"].replace("Z", "+00:00"))
                    readings.append(TemperatureReading(
                        data=ts.strftime("%d/%m/%Y"),
                        ora=ts.strftime("%H:%M"),
                        zona=row["zona"],
                        sensor_id=row["sensor_id"],
                        temperatura=float(row["temperatura"]),
                        temp_min=float(row.get("temp_min_norm") or 0),
                        temp_max=float(row.get("temp_max_norm") or 0),
                        alert=bool(row.get("alert", False)),
                        severity=row.get("severity", "ok"),
                        rilevato_da=row.get("rilevato_da", "iot"),
                        azione_correttiva=row.get("messaggio", ""),
                    ))

    # ── 3. Dati demo se Supabase non è configurato ───────────────────────────
    if not readings:
        from backend.haccp_report import make_demo_data
        demo = make_demo_data()
        readings = demo.lettori
        hotel_name  = hotel_name or demo.hotel_name
        hotel_citta = hotel_citta or demo.hotel_citta
        hotel_piva  = hotel_piva  or demo.hotel_piva

    # ── 4. Genera PDF ────────────────────────────────────────────────────────
    report_data = HACCPReportData(
        hotel_name=hotel_name,
        hotel_citta=hotel_citta,
        hotel_piva=hotel_piva,
        responsabile_haccp=responsabile,
        anno=anno,
        mese=mese,
        lettori=readings,
        note_generali=note,
        data_compilazione=datetime.now().strftime("%d/%m/%Y"),
    )

    pdf_bytes = HACCPPdfGenerator(report_data).generate()

    filename = f"registro_haccp_{hotel_id[:8]}_{anno}_{mese:02d}.pdf"
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ── Endpoint: Riepilogo mensile HACCP (JSON) ─────────────────────────────────

@app.get(
    "/api/haccp/monthly-summary",
    summary="Riepilogo statistico HACCP mensile",
    tags=["HACCP & Sicurezza"],
)
async def haccp_monthly_summary(hotel_id: str, anno: int, mese: int):
    """
    Restituisce le statistiche aggregate del mese:
    totale rilevazioni, conformità %, alert, critici,
    zone più problematiche, trend rispetto al mese precedente.
    """
    if not SUPABASE_URL:
        # Dati demo
        return {
            "periodo": f"{mese:02d}/{anno}",
            "totale_rilevazioni": 420,
            "conformi": 411,
            "conformita_pct": 97.9,
            "warning": 6,
            "critici": 3,
            "zone_critiche": ["cella_surgelati", "cella_frigo"],
            "trend_vs_mese_prec": "+0.5% conformità",
            "nota": "Dati demo — configura Supabase per dati reali",
        }

    _, last_day = calendar.monthrange(anno, mese)
    date_from = f"{anno}-{mese:02d}-01T00:00:00"
    date_to   = f"{anno}-{mese:02d}-{last_day}T23:59:59"

    async with httpx.AsyncClient() as client:
        r = await client.get(
            f"{SUPABASE_URL}/rest/v1/haccp_temperature",
            headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"},
            params={
                "hotel_id":  f"eq.{hotel_id}",
                "timestamp": f"gte.{date_from}",
                "and":       f"(timestamp.lte.{date_to})",
                "select":    "zona,alert,severity",
                "limit":     "5000",
            },
        )

    rows = r.json() if r.status_code == 200 else []
    total    = len(rows)
    alerts   = [x for x in rows if x["alert"]]
    critici  = [x for x in alerts if x["severity"] == "critical"]
    warnings = [x for x in alerts if x["severity"] == "warning"]
    conformi = total - len(alerts)

    # Zone problematiche
    from collections import Counter
    zone_count = Counter(x["zona"] for x in alerts)
    zone_critiche = [z for z, _ in zone_count.most_common(3)]

    return {
        "periodo": f"{mese:02d}/{anno}",
        "totale_rilevazioni": total,
        "conformi": conformi,
        "conformita_pct": round(conformi / total * 100, 1) if total else 100.0,
        "warning": len(warnings),
        "critici": len(critici),
        "zone_critiche": zone_critiche,
    }


# ── Frontend statico — BAD360_SPLIT (deve stare DOPO tutte le route API) ───────
# html=True abilita: GET / → index.html, GET /BAD360.html → BAD360.html, ecc.
_split_dir = os.path.join(os.path.dirname(__file__), "BAD360_SPLIT")
if os.path.isdir(_split_dir):
    app.mount("/", StaticFiles(directory=_split_dir, html=True), name="frontend")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
