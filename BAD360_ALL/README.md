# FBM SaaS B2C — BAD.S Unified Platform v2.0.0
### Hospitality Intelligence & F&B Management — SaaS B2C

> Piattaforma professionale per la gestione integrata di strutture ricettive italiane.  
> Supply Chain Management · HACCP & Safety · ESG/CSR · Food & Beverage Cost · Operations · Academy

---

## Struttura del Progetto

```
FBM_SAAS_B2C/
├── FBM_SaaS_B2C.html            # Frontend SPA (tutto-in-uno, ~1.1MB)
├── main.py                       # Backend FastAPI v2.0.0
├── requirements.txt              # Dipendenze Python
├── supabase_setup.sql            # Schema database base (hotels, fornitori, HACCP, ESG...)
├── supabase_fb_cost.sql          # Schema modulo F&B Cost (ricette, ingredienti, vendite...)
├── .env.example                  # Template variabili d'ambiente
├── avvia.bat                     # Script avvio rapido (Windows)
├── primo avvio.txt               # Istruzioni installazione reportlab
├── README.md                     # Questo file
└── backend/
    ├── __init__.py
    ├── database.py               # Client Supabase + helpers query
    ├── fb_cost.py                # Router F&B Cost (ingredienti, ricette, BCG, analisi)
    └── haccp_report.py           # Generatore PDF Registro HACCP mensile (ReportLab)
```

---

## Installazione Rapida (Windows)

```
1. Doppio clic su avvia.bat
2. Alla prima esecuzione: apri .env e inserisci ANTHROPIC_API_KEY
3. Installa reportlab (una sola volta):
      venv\Scripts\pip.exe install "reportlab>=4.0.0"
4. Il browser si apre automaticamente su http://localhost:8000
```

## Installazione Manuale

```bash
python -m venv venv
source venv/bin/activate          # Linux/Mac
venv\Scripts\activate.bat         # Windows

pip install -r requirements.txt

cp .env.example .env
# Modifica .env → inserisci ANTHROPIC_API_KEY

# Configura Supabase (opzionale ma consigliato)
# 1. Crea progetto su https://supabase.com
# 2. SQL Editor → esegui supabase_setup.sql
# 3. SQL Editor → esegui supabase_fb_cost.sql
# 4. Copia URL e service_role key nel .env

uvicorn main:app --reload --port 8000
```

---

## Requisiti di Sistema

| Componente | Versione minima |
|-----------|----------------|
| Python | 3.11+ |
| Browser | Chrome 120+, Firefox 120+, Safari 17+ |
| RAM | 512 MB (1 GB consigliato) |
| Connessione | Internet (per API Anthropic + Supabase) |

---

## Novità v2.0 — Moduli Aggiunti

### 🍸 F&B Cost Management (NUOVO)
Modulo completo per la gestione dei costi Food & Beverage:
- **Anagrafica ingredienti** con costo acquisto e allergeni (Reg. UE 1169/2011)
- **Ricette con distinta base** — food cost % calcolato automaticamente
- **BCG Matrix** — classificazione Star / Cash Cow / Question Mark / Dog
- **Analisi periodica** food cost e beverage cost reale vs benchmark
- **Report AI** con analisi e suggerimenti correttivi

### 📋 Registro HACCP PDF (NUOVO)
Generazione automatica del Registro HACCP Mensile Digitale conforme Reg. CE 852/2004:
- Cover con KPI riepilogativi (conformi, warning, critici)
- Checklist 7 principi HACCP (CCP 1–7)
- Log completo temperature IoT per zona
- Sezione Non Conformità con azioni correttive
- Firma responsabile HACCP
- Esportabile via `GET /api/haccp/export-registro`

### 🌿 Hotellerie — SCM & ESG (NUOVO)
Ispirato alla tesi *"Supply Chain Management applicato al settore alberghiero"* (Serra, 2025/2026):
- **🔗 Supply Chain** — Matrice fornitori ABC, KPI SCM, Lean (JIT/Kanban/VSM), Risk Matrix
- **🌱 ESG & CSR** — GSTC, LECS luxury, KPI GRI (E/S/G), SDGs ONU
- **💻 Sistemi IT** — ERP/PMS/CRM/IMS, IoT, Blockchain, flussi integrazione

---

## API Endpoints

### AI Advisor
| Metodo | Endpoint | Descrizione |
|--------|---------|-------------|
| POST | `/api/ai/query` | Query generica (moduli: general, scm, haccp, esg, beverage) |
| POST | `/api/ai/scm-advisor` | Consulente SCM specializzato |
| POST | `/api/ai/haccp-advisor` | Consulente HACCP |
| POST | `/api/ai/esg-advisor` | Consulente ESG/Certificazioni |
| POST | `/api/ai/fb-advisor` | Consulente F&B Cost & Menu Engineering |

### Food & Beverage Cost
| Metodo | Endpoint | Descrizione |
|--------|---------|-------------|
| POST | `/api/fb/ingrediente` | Crea/aggiorna ingrediente |
| GET | `/api/fb/ingredienti` | Lista ingredienti hotel |
| POST | `/api/fb/ricetta` | Crea ricetta con distinta base |
| GET | `/api/fb/ricette` | Lista ricette con food cost % |
| GET | `/api/fb/ricetta/{id}/cost` | Dettaglio costi ricetta |
| POST | `/api/fb/vendita` | Registra vendita |
| GET | `/api/fb/analysis` | Analisi food/bev cost periodica |
| GET | `/api/fb/bcg-matrix` | Matrice BCG menu |
| POST | `/api/fb/report` | Report periodico con AI |

### HACCP & Sicurezza
| Metodo | Endpoint | Descrizione |
|--------|---------|-------------|
| POST | `/api/haccp/temperature-log` | Log temperatura IoT |
| GET | `/api/haccp/ccp-checklist` | Checklist 7 principi HACCP |
| GET | `/api/haccp/export-registro` | **Esporta Registro HACCP PDF** |
| GET | `/api/haccp/monthly-summary` | Riepilogo statistico mensile |

### Supply Chain
| Metodo | Endpoint | Descrizione |
|--------|---------|-------------|
| POST | `/api/scm/supplier-eval` | Valutazione AI fornitore |
| GET | `/api/scm/par-level-calculator` | Calcolo par level ottimale |

### ESG & Bandi
| Metodo | Endpoint | Descrizione |
|--------|---------|-------------|
| POST | `/api/esg/report-generate` | Genera report ESG automatico |
| GET | `/api/esg/gstc-criteria` | Criteri GSTC turismo sostenibile |
| POST | `/api/bandi/search` | Ricerca bandi PNRR/FESR/Regionali AI |

### Analytics
| Metodo | Endpoint | Descrizione |
|--------|---------|-------------|
| GET | `/api/analytics/kpi-benchmark` | Benchmark KPI per stelle |
| GET | `/api/health` | Health check servizi |

**Docs interattive:** `http://localhost:8000/api/docs`

---

## Esempio Export Registro HACCP PDF

```
GET http://localhost:8000/api/haccp/export-registro
    ?hotel_id=<uuid-dal-db>
    &anno=2026
    &mese=3
    &responsabile=Mario+Rossi
    &note=Calibrazione+termometri+01%2F03%2F2026
```
> Senza Supabase configurato viene generato un documento demo con dati realistici.

---

## Stack Tecnologico

| Layer | Tecnologia |
|-------|-----------|
| Frontend | HTML5 + CSS3 + Vanilla JS (SPA) |
| Backend | Python 3.11 + FastAPI |
| Database | PostgreSQL (Supabase) |
| AI | Anthropic Claude (claude-sonnet-4) |
| PDF | ReportLab 4.x |
| Auth | Supabase Auth (JWT) |

---

## Setup Chiave API Anthropic

1. Vai su [console.anthropic.com](https://console.anthropic.com)
2. API Keys → Create Key
3. Copia e incolla in `.env`:
   ```
   ANTHROPIC_API_KEY=sk-ant-api03-...
   ```

---

## Riferimenti Normativi

- Serra, S. (2025/2026). *Supply Chain Management applicato al settore alberghiero*. Università eCampus.
- Reg. CE 852/2004 — Igiene prodotti alimentari (HACCP)
- Reg. CE 178/2002 — Legge generale alimentare (rintracciabilità)
- Reg. UE 1169/2011 — Informazioni sugli alimenti (allergeni)
- ISO 9001/14001/45001/22000/22005 — Sistemi di gestione integrati
- GSTC Hospitality Criteria v3.0 — Turismo sostenibile
- GRI Standards 2021 — ESG Reporting

---

*© 2025-2026 BAD.S Platform — SkillSolutions*
