-- ═══════════════════════════════════════════════════════════════════
--  BAD.S Unified Platform — Schema Database Supabase (PostgreSQL)
--  Esegui su: Supabase Dashboard → SQL Editor → Run
--  Versione: 2.0.0 | Aggiornato: 2026
-- ═══════════════════════════════════════════════════════════════════

-- Abilita estensioni necessarie
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ═══════════════════════════════════════════════════════════════════
--  TABELLA: hotels
--  Strutture ricettive registrate alla piattaforma
-- ═══════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS hotels (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    nome            TEXT NOT NULL,
    stelle          INTEGER CHECK (stelle BETWEEN 1 AND 5),
    tipo            TEXT DEFAULT 'hotel',  -- hotel | b&b | resort | agriturismo
    indirizzo       TEXT,
    citta           TEXT,
    regione         TEXT,
    cap             TEXT,
    piva            TEXT UNIQUE,
    email           TEXT,
    telefono        TEXT,
    pms_software    TEXT,  -- Opera | Mews | Protel | Zucchetti
    erp_software    TEXT,
    n_camere        INTEGER,
    n_dipendenti    INTEGER,
    piano_tariff    TEXT DEFAULT 'free',  -- free | starter | pro | enterprise
    attivo          BOOLEAN DEFAULT TRUE,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

-- ═══════════════════════════════════════════════════════════════════
--  TABELLA: fornitori
--  Registro fornitori qualificati (SCM Best Practice)
-- ═══════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS fornitori (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    hotel_id        UUID REFERENCES hotels(id) ON DELETE CASCADE,
    ragione_sociale TEXT NOT NULL,
    piva            TEXT,
    categoria       TEXT NOT NULL,  -- food_fresh | beverage | chimici | tessile | manutenzione | tech
    classe_abc      CHAR(1) DEFAULT 'C' CHECK (classe_abc IN ('A','B','C')),
    indirizzo       TEXT,
    referente       TEXT,
    email           TEXT,
    telefono        TEXT,
    -- Certificazioni
    cert_haccp      BOOLEAN DEFAULT FALSE,
    cert_iso22000   BOOLEAN DEFAULT FALSE,
    cert_iso14001   BOOLEAN DEFAULT FALSE,
    cert_iso9001    BOOLEAN DEFAULT FALSE,
    cert_iso22005   BOOLEAN DEFAULT FALSE,  -- Rintracciabilità
    altre_cert      TEXT[],
    -- Dich. HACCP (Reg. CE 852/2004)
    dich_haccp_presente BOOLEAN DEFAULT FALSE,
    dich_haccp_data     DATE,
    dich_haccp_scadenza DATE,
    -- Gestione
    stato           TEXT DEFAULT 'attivo',  -- attivo | sospeso | blacklist
    punteggio       INTEGER DEFAULT 0 CHECK (punteggio BETWEEN 0 AND 100),
    ultimo_audit    DATE,
    prossimo_audit  DATE,
    note            TEXT,
    -- Locale/km0
    km0             BOOLEAN DEFAULT FALSE,
    distanza_km     INTEGER,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

-- ═══════════════════════════════════════════════════════════════════
--  TABELLA: ordini_fornitori
--  Registro ordini a fornitori per SCM e tracciabilità
-- ═══════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS ordini_fornitori (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    hotel_id        UUID REFERENCES hotels(id) ON DELETE CASCADE,
    fornitore_id    UUID REFERENCES fornitori(id),
    numero_ordine   TEXT,
    data_ordine     DATE NOT NULL DEFAULT CURRENT_DATE,
    data_consegna   DATE,
    stato           TEXT DEFAULT 'inviato',  -- bozza | inviato | confermato | consegnato | NC
    importo_totale  NUMERIC(12,2),
    valuta          TEXT DEFAULT 'EUR',
    note            TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS ordini_righe (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    ordine_id       UUID REFERENCES ordini_fornitori(id) ON DELETE CASCADE,
    articolo        TEXT NOT NULL,
    categoria       TEXT,
    quantita        NUMERIC(10,3) NOT NULL,
    unita_misura    TEXT DEFAULT 'kg',
    prezzo_unitario NUMERIC(10,4),
    importo         NUMERIC(12,2),
    lotto           TEXT,      -- Per tracciabilità ISO 22005
    scadenza        DATE,
    note_qualita    TEXT
);

-- ═══════════════════════════════════════════════════════════════════
--  TABELLA: haccp_temperature
--  Log temperature sensori IoT (Reg. CE 852/2004)
-- ═══════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS haccp_temperature (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    hotel_id        UUID REFERENCES hotels(id) ON DELETE CASCADE,
    sensor_id       TEXT NOT NULL,
    zona            TEXT NOT NULL,  -- cella_frigo | surgelati | zona_calda | cantina | frigo_bar
    temperatura     NUMERIC(6,2) NOT NULL,
    temp_min_norm   NUMERIC(6,2),
    temp_max_norm   NUMERIC(6,2),
    alert           BOOLEAN DEFAULT FALSE,
    severity        TEXT DEFAULT 'ok',  -- ok | warning | critical
    messaggio       TEXT,
    conforme_reg    BOOLEAN DEFAULT TRUE,
    rilevato_da     TEXT DEFAULT 'iot',  -- iot | manuale
    timestamp       TIMESTAMPTZ DEFAULT NOW()
);

-- Index per query temporali frequenti
CREATE INDEX IF NOT EXISTS idx_haccp_temp_hotel_ts 
    ON haccp_temperature(hotel_id, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_haccp_temp_alert 
    ON haccp_temperature(hotel_id, alert) WHERE alert = TRUE;

-- ═══════════════════════════════════════════════════════════════════
--  TABELLA: inventario
--  Gestione scorte magazzino con par level
-- ═══════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS inventario (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    hotel_id        UUID REFERENCES hotels(id) ON DELETE CASCADE,
    articolo        TEXT NOT NULL,
    categoria       TEXT,
    unita_misura    TEXT DEFAULT 'kg',
    giacenza_attuale NUMERIC(12,3) DEFAULT 0,
    par_level       NUMERIC(12,3),
    punto_riordino  NUMERIC(12,3),
    scorta_minima   NUMERIC(12,3),
    fornitore_id    UUID REFERENCES fornitori(id),
    prezzo_acquisto NUMERIC(10,4),
    lotto_attivo    TEXT,
    scadenza_lotto  DATE,
    posizione       TEXT,  -- cella_A1, scaffale_B3...
    metodo_rotazione TEXT DEFAULT 'FIFO',  -- FIFO | FEFO
    note            TEXT,
    ultimo_aggiornamento TIMESTAMPTZ DEFAULT NOW(),
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- ═══════════════════════════════════════════════════════════════════
--  TABELLA: esg_reports
--  Report ESG annuali per struttura
-- ═══════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS esg_reports (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    hotel_id        UUID REFERENCES hotels(id) ON DELETE CASCADE,
    anno            INTEGER NOT NULL,
    -- Environmental KPIs
    co2_kg_camera   NUMERIC(8,2),       -- kgCO2eq/camera/anno
    energia_kwh_camera NUMERIC(8,2),    -- kWh/camera/anno
    acqua_litri_ospite NUMERIC(8,2),    -- L/ospite/giorno
    rifiuti_riciclo_pct NUMERIC(5,2),   -- % rifiuti riciclati
    acquisti_locali_pct NUMERIC(5,2),   -- % acquisti km0
    energia_rinnovabile_pct NUMERIC(5,2),
    -- Social KPIs
    dipendenti_tot  INTEGER,
    turnover_pct    NUMERIC(5,2),
    ore_formazione  NUMERIC(6,1),       -- ore/dipendente/anno
    infortuni_n     INTEGER DEFAULT 0,
    -- Governance KPIs
    audit_interni_n INTEGER DEFAULT 0,
    nc_aperte       INTEGER DEFAULT 0,
    fornitori_codice_etico_pct NUMERIC(5,2),
    -- Certificazioni attive
    cert_iso14001   BOOLEAN DEFAULT FALSE,
    cert_iso50001   BOOLEAN DEFAULT FALSE,
    cert_ecolabel   BOOLEAN DEFAULT FALSE,
    cert_greenkey   BOOLEAN DEFAULT FALSE,
    cert_emas       BOOLEAN DEFAULT FALSE,
    cert_gstc       BOOLEAN DEFAULT FALSE,
    -- Report generato
    report_testo    TEXT,
    report_ai       BOOLEAN DEFAULT FALSE,
    stato           TEXT DEFAULT 'bozza',  -- bozza | approvato | pubblicato
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(hotel_id, anno)
);

-- ═══════════════════════════════════════════════════════════════════
--  TABELLA: ai_queries
--  Log query AI per analytics e rate limiting
-- ═══════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS ai_queries (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    hotel_id        UUID REFERENCES hotels(id),
    modulo          TEXT,  -- general | scm | haccp | esg | beverage
    query_text      TEXT,
    risposta_tokens INTEGER,
    latency_ms      INTEGER,
    timestamp       TIMESTAMPTZ DEFAULT NOW()
);

-- ═══════════════════════════════════════════════════════════════════
--  TABELLA: bandi_salvati
--  Bandi di finanziamento individuati tramite AI
-- ═══════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS bandi_salvati (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    hotel_id        UUID REFERENCES hotels(id) ON DELETE CASCADE,
    nome            TEXT NOT NULL,
    ente_erogatore  TEXT,
    tipo            TEXT,  -- PNRR | FESR | Nazionale | Regionale | Comunale
    regione         TEXT,
    settore         TEXT DEFAULT 'hospitality',
    importo_max     NUMERIC(14,2),
    contributo_pct  NUMERIC(5,2),
    scadenza        DATE,
    stato           TEXT DEFAULT 'da_valutare',  -- da_valutare | interesse | candidato | ottenuto | scartato
    link_ufficiale  TEXT,
    note            TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- ═══════════════════════════════════════════════════════════════════
--  ROW LEVEL SECURITY (RLS) — Ogni hotel vede solo i propri dati
-- ═══════════════════════════════════════════════════════════════════
ALTER TABLE fornitori         ENABLE ROW LEVEL SECURITY;
ALTER TABLE ordini_fornitori  ENABLE ROW LEVEL SECURITY;
ALTER TABLE haccp_temperature ENABLE ROW LEVEL SECURITY;
ALTER TABLE inventario        ENABLE ROW LEVEL SECURITY;
ALTER TABLE esg_reports       ENABLE ROW LEVEL SECURITY;
ALTER TABLE bandi_salvati     ENABLE ROW LEVEL SECURITY;

-- ═══════════════════════════════════════════════════════════════════
--  FUNZIONE: aggiorna updated_at automaticamente
-- ═══════════════════════════════════════════════════════════════════
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_hotels_updated
    BEFORE UPDATE ON hotels
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER trg_fornitori_updated
    BEFORE UPDATE ON fornitori
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER trg_esg_updated
    BEFORE UPDATE ON esg_reports
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- ═══════════════════════════════════════════════════════════════════
--  DATI DI TEST (opzionale — commenta in produzione)
-- ═══════════════════════════════════════════════════════════════════
INSERT INTO hotels (nome, stelle, tipo, citta, regione, n_camere, n_dipendenti, piano_tariff)
VALUES
    ('Hotel BAD.S Demo', 4, 'hotel', 'Cagliari', 'Sardegna', 45, 28, 'pro'),
    ('Resort Costa Smeralda', 5, 'resort', 'Arzachena', 'Sardegna', 120, 85, 'enterprise')
ON CONFLICT DO NOTHING;

-- Fine script setup Supabase
SELECT 'BAD.S Database schema v2.0.0 creato con successo! 🚀' AS risultato;
