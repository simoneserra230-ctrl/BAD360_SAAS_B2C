-- ═══════════════════════════════════════════════════════════════════
--  BAD.S — Vendor Rating Automatico + SLA Manager + Partnership
--  Esegui su: Supabase Dashboard → SQL Editor → Run
--  Versione: 1.0.0
--  Fonti:
--    Vendor Rating: Cribis, Ivalua, OnlineProcurement, Gallo (Unibo)
--    SLA: Deepser, EENA, Mainsim, DigitalWorldItalia
--    Partnership: Marenzi (UniPD), Teamwork Hospitality, SCIRJ
-- ═══════════════════════════════════════════════════════════════════

-- ═══════════════════════════════════════════════════════════════════
--  MODULO 1 — VENDOR RATING AUTOMATICO
--
--  Formula ponderata (Cribis / Ivalua best practice):
--   - Puntualità consegna (OTD)    30%
--   - Qualità / tasso NC           25%
--   - Conformità prezzo            20%
--   - Certificazioni & compliance  15%
--   - Reattività / servizio        10%
-- ═══════════════════════════════════════════════════════════════════

-- Tabella storico punteggi — permette trend e confronti nel tempo
CREATE TABLE IF NOT EXISTS vendor_rating_history (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    hotel_id        UUID REFERENCES hotels(id) ON DELETE CASCADE,
    fornitore_id    UUID REFERENCES fornitori(id) ON DELETE CASCADE,
    periodo         TEXT NOT NULL,              -- "2026-03" (YYYY-MM) o "2026-Q1"
    tipo_periodo    TEXT DEFAULT 'mensile',     -- mensile | trimestrale | annuale

    -- Score globale (0-100) e breakdown per dimensione
    score_totale        NUMERIC(5,1) NOT NULL,
    score_puntualita    NUMERIC(5,1),           -- OTD %
    score_qualita       NUMERIC(5,1),           -- basato su NC rate
    score_prezzo        NUMERIC(5,1),           -- conformità prezzi listino
    score_compliance    NUMERIC(5,1),           -- certificazioni attive
    score_reattivita    NUMERIC(5,1),           -- tempo risposta medio

    -- Dati grezzi usati nel calcolo
    ordini_totali       INTEGER DEFAULT 0,
    consegne_puntuali   INTEGER DEFAULT 0,
    nc_aperte           INTEGER DEFAULT 0,
    nc_chiuse           INTEGER DEFAULT 0,
    scostamento_prezzo_pct NUMERIC(6,2),        -- % deviazione da listino

    -- Classificazione risultante
    classe_rating   CHAR(1) CHECK (classe_rating IN ('A','B','C','D')),
    -- A=90-100 (Strategic), B=70-89 (Preferred), C=50-69 (Approved), D<50 (At Risk)
    variazione_vs_periodo_prec NUMERIC(5,1),    -- delta rispetto al periodo precedente
    flag_miglioramento  BOOLEAN DEFAULT FALSE,
    flag_peggioramento  BOOLEAN DEFAULT FALSE,

    calcolato_da    TEXT DEFAULT 'sistema',     -- sistema | manuale
    note            TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(hotel_id, fornitore_id, periodo)
);

CREATE INDEX IF NOT EXISTS idx_vr_history_fornitore ON vendor_rating_history(fornitore_id, periodo DESC);
CREATE INDEX IF NOT EXISTS idx_vr_history_hotel ON vendor_rating_history(hotel_id, periodo DESC);

-- KPI log per singolo ordine/evento — granularità massima per il calcolo
CREATE TABLE IF NOT EXISTS vendor_kpi_events (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    hotel_id        UUID REFERENCES hotels(id) ON DELETE CASCADE,
    fornitore_id    UUID REFERENCES fornitori(id) ON DELETE CASCADE,
    ordine_id       UUID REFERENCES ordini_fornitori(id),
    tipo_evento     TEXT NOT NULL,              -- consegna | nc_aperta | nc_chiusa | prezzo_deviazione | risposta_richiesta
    -- Valori misurati
    data_evento     DATE NOT NULL DEFAULT CURRENT_DATE,
    valore          NUMERIC(10,3),             -- es. ore ritardo, % scostamento, 0/1
    valore_atteso   NUMERIC(10,3),             -- benchmark / target contratto
    conforme        BOOLEAN DEFAULT TRUE,
    penale_applicata BOOLEAN DEFAULT FALSE,
    impatto_score   NUMERIC(5,2),              -- quanto influisce sul rating (calcolato)
    note            TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_vkpi_fornitore_data ON vendor_kpi_events(fornitore_id, data_evento DESC);


-- ═══════════════════════════════════════════════════════════════════
--  MODULO 2 — SLA MANAGER CON VENDOR KPI
--
--  Fonti: Deepser (guida SLA), EENA (best practice contrattuale),
--         Mainsim (SLA facility hotel), DigitalWorldItalia
-- ═══════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS sla_contracts (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    hotel_id        UUID REFERENCES hotels(id) ON DELETE CASCADE,
    fornitore_id    UUID REFERENCES fornitori(id) ON DELETE CASCADE,
    nome            TEXT NOT NULL,              -- es. "SLA Forniture Alimentari Fresco 2026"
    categoria       TEXT NOT NULL,              -- food_fresh | beverage | chimici | tessile | manutenzione | tech
    -- Validità
    data_inizio     DATE NOT NULL,
    data_scadenza   DATE NOT NULL,
    rinnovo_automatico BOOLEAN DEFAULT FALSE,
    preavviso_rinnovo_gg INTEGER DEFAULT 60,
    -- KPI target (soglie minime accettabili)
    target_otd_pct          NUMERIC(5,2) DEFAULT 95.0,   -- On Time Delivery %
    target_otif_pct         NUMERIC(5,2) DEFAULT 92.0,   -- On Time In Full %
    target_qualita_pct      NUMERIC(5,2) DEFAULT 98.0,   -- % ordini senza NC
    target_prezzo_var_pct   NUMERIC(5,2) DEFAULT 3.0,    -- max % scostamento prezzo
    target_risposta_ore     INTEGER DEFAULT 24,            -- max ore risposta reclami
    -- Penali contrattuali
    penale_ritardo_pct      NUMERIC(5,2) DEFAULT 0.5,    -- % valore ordine per giorno ritardo
    penale_nc_pct           NUMERIC(5,2) DEFAULT 2.0,    -- % valore NC per prodotto difettoso
    penale_max_mensile_pct  NUMERIC(5,2) DEFAULT 10.0,   -- cap mensile penali
    -- Revisione periodica
    frequenza_review        TEXT DEFAULT 'trimestrale',  -- mensile | trimestrale | semestrale
    prossima_review         DATE,
    -- Stato
    stato           TEXT DEFAULT 'attivo',      -- bozza | attivo | sospeso | scaduto | terminato
    approvato_da    TEXT,
    note_legali     TEXT,
    note            TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_sla_hotel_stato ON sla_contracts(hotel_id, stato);
CREATE INDEX IF NOT EXISTS idx_sla_fornitore ON sla_contracts(fornitore_id, stato);

-- Misurazioni periodiche KPI vs target SLA
CREATE TABLE IF NOT EXISTS sla_kpi_measurements (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    sla_id          UUID REFERENCES sla_contracts(id) ON DELETE CASCADE,
    hotel_id        UUID REFERENCES hotels(id) ON DELETE CASCADE,
    fornitore_id    UUID REFERENCES fornitori(id) ON DELETE CASCADE,
    periodo         TEXT NOT NULL,              -- "2026-03"
    -- Valori misurati nel periodo
    otd_misurato_pct        NUMERIC(5,2),
    otif_misurato_pct       NUMERIC(5,2),
    qualita_misurata_pct    NUMERIC(5,2),
    prezzo_var_misurata_pct NUMERIC(5,2),
    risposta_media_ore      NUMERIC(6,1),
    -- Conformità (target superato / non superato)
    otd_ok          BOOLEAN,
    otif_ok         BOOLEAN,
    qualita_ok      BOOLEAN,
    prezzo_ok       BOOLEAN,
    risposta_ok     BOOLEAN,
    -- Penali calcolate
    penali_euro     NUMERIC(10,2) DEFAULT 0,
    penali_applicate BOOLEAN DEFAULT FALSE,
    -- Compliance score aggregato
    compliance_score NUMERIC(5,1),             -- % KPI rispettati nel periodo
    -- Dati base calcolo
    n_ordini        INTEGER DEFAULT 0,
    n_ordini_puntuali INTEGER DEFAULT 0,
    n_nc            INTEGER DEFAULT 0,
    -- Azioni
    azione_richiesta TEXT,                     -- es. "piano di miglioramento entro 30gg"
    azione_scadenza DATE,
    note            TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(sla_id, periodo)
);

CREATE INDEX IF NOT EXISTS idx_sla_kpi_periodo ON sla_kpi_measurements(sla_id, periodo DESC);

-- Alert automatici SLA (generati quando KPI scende sotto soglia)
CREATE TABLE IF NOT EXISTS sla_alerts (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    sla_id          UUID REFERENCES sla_contracts(id) ON DELETE CASCADE,
    hotel_id        UUID REFERENCES hotels(id) ON DELETE CASCADE,
    fornitore_id    UUID REFERENCES fornitori(id) ON DELETE CASCADE,
    kpi_nome        TEXT NOT NULL,              -- otd | otif | qualita | prezzo | risposta
    valore_rilevato NUMERIC(8,2),
    soglia_target   NUMERIC(8,2),
    scostamento     NUMERIC(8,2),              -- valore - soglia
    severity        TEXT DEFAULT 'warning',    -- info | warning | critical
    -- Gestione
    stato           TEXT DEFAULT 'aperto',     -- aperto | in_gestione | chiuso
    assegnato_a     TEXT,
    azione_intrapresa TEXT,
    data_chiusura   DATE,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_sla_alerts_stato ON sla_alerts(hotel_id, stato, created_at DESC);


-- ═══════════════════════════════════════════════════════════════════
--  MODULO 3 — PARTNERSHIP FORNITORE LUNGO PERIODO
--
--  Fonti: Marenzi (UniPD) — relazioni cooperative e SCM,
--         Teamwork Hospitality — best practice,
--         SCIRJ — benefici partnership alberghiera
-- ═══════════════════════════════════════════════════════════════════

-- Accordo di partnership strategica (livello superiore all'SLA)
CREATE TABLE IF NOT EXISTS partnership_agreements (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    hotel_id        UUID REFERENCES hotels(id) ON DELETE CASCADE,
    fornitore_id    UUID REFERENCES fornitori(id) ON DELETE CASCADE,
    nome            TEXT NOT NULL,              -- es. "Partnership Strategica Carni Sarde 2025-2027"
    livello         TEXT DEFAULT 'preferred',   -- preferred | strategic | exclusive
    -- Livelli:
    --   preferred  = fornitore privilegiato, no esclusiva, sconti volumetrici
    --   strategic  = co-sviluppo prodotto, roadmap condivisa, info riservate
    --   exclusive  = esclusiva categoria, investimenti congiunti
    -- Validità
    data_inizio     DATE NOT NULL,
    data_scadenza   DATE,                       -- NULL = tempo indeterminato
    durata_anni     INTEGER,
    rinnovo_automatico BOOLEAN DEFAULT FALSE,
    -- Benefici fornitore → hotel
    sconto_volume_pct       NUMERIC(5,2),       -- % sconto su volumi concordati
    priorita_consegna       BOOLEAN DEFAULT FALSE, -- garanzia priorità in caso shortage
    lock_in_prezzo_mesi     INTEGER,            -- mesi blocco prezzi
    formazione_condivisa    BOOLEAN DEFAULT FALSE,
    accesso_novita_prodotto BOOLEAN DEFAULT FALSE,
    -- Impegni hotel → fornitore
    volume_minimo_annuo_euro NUMERIC(12,2),
    quota_categoria_pct      NUMERIC(5,2),      -- % acquisti categoria assegnata
    condivisione_previsioni  BOOLEAN DEFAULT FALSE, -- piano ordini condiviso
    -- Scorecard condivisa
    kpi_condivisi           JSONB DEFAULT '[]', -- [{nome, target, peso}]
    frequenza_review        TEXT DEFAULT 'semestrale',
    -- Stato
    stato           TEXT DEFAULT 'attivo',      -- proposta | attivo | sospeso | terminato
    approvato_da    TEXT,
    motivo_termine  TEXT,
    note            TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_partner_hotel_stato ON partnership_agreements(hotel_id, stato);

-- Meeting di review partnership (pianificati e storico)
CREATE TABLE IF NOT EXISTS partnership_meetings (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    partnership_id  UUID REFERENCES partnership_agreements(id) ON DELETE CASCADE,
    hotel_id        UUID REFERENCES hotels(id) ON DELETE CASCADE,
    fornitore_id    UUID REFERENCES fornitori(id) ON DELETE CASCADE,
    tipo            TEXT DEFAULT 'review',      -- review | strategico | emergenza | onboarding
    data_pianificata DATE NOT NULL,
    ora             TIME,
    luogo           TEXT,
    -- Partecipanti
    partecipanti_hotel    TEXT[],
    partecipanti_fornitore TEXT[],
    -- Contenuto
    agenda          TEXT,
    verbale         TEXT,
    -- KPI discussi (snapshot al momento del meeting)
    score_al_momento NUMERIC(5,1),
    kpi_snapshot    JSONB DEFAULT '{}',
    -- Azioni deliberate
    action_items    JSONB DEFAULT '[]',         -- [{azione, responsabile, scadenza, chiusa}]
    -- Esito
    stato           TEXT DEFAULT 'pianificato', -- pianificato | svolto | annullato | rimandato
    esito           TEXT,                       -- positivo | neutro | critico
    data_prossimo_meeting DATE,
    note            TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_pmeetings_partnership ON partnership_meetings(partnership_id, data_pianificata DESC);

-- Scorecard condivisa — valutazioni reciproche (hotel → fornitore E fornitore → hotel)
CREATE TABLE IF NOT EXISTS partnership_scorecard (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    partnership_id  UUID REFERENCES partnership_agreements(id) ON DELETE CASCADE,
    hotel_id        UUID REFERENCES hotels(id) ON DELETE CASCADE,
    fornitore_id    UUID REFERENCES fornitori(id) ON DELETE CASCADE,
    periodo         TEXT NOT NULL,              -- "2026-Q1"
    direzione       TEXT NOT NULL,              -- hotel_su_fornitore | fornitore_su_hotel
    -- Dimensioni valutazione (1-5)
    qualita_prodotto        INTEGER CHECK (qualita_prodotto BETWEEN 1 AND 5),
    puntualita              INTEGER CHECK (puntualita BETWEEN 1 AND 5),
    comunicazione           INTEGER CHECK (comunicazione BETWEEN 1 AND 5),
    flessibilita            INTEGER CHECK (flessibilita BETWEEN 1 AND 5),
    innovazione             INTEGER CHECK (innovazione BETWEEN 1 AND 5),
    rapporto_qualita_prezzo INTEGER CHECK (rapporto_qualita_prezzo BETWEEN 1 AND 5),
    -- Score aggregato (0-100)
    score_aggregato NUMERIC(5,1),
    -- Testo libero
    punti_forza     TEXT,
    aree_miglioramento TEXT,
    commento        TEXT,
    compilato_da    TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(partnership_id, periodo, direzione)
);


-- ═══════════════════════════════════════════════════════════════════
--  FUNZIONE: calcola_vendor_rating
--  Calcola il rating automatico da dati esistenti (ordini, NC)
-- ═══════════════════════════════════════════════════════════════════
CREATE OR REPLACE FUNCTION calcola_vendor_rating(
    p_hotel_id UUID,
    p_fornitore_id UUID,
    p_periodo_inizio DATE,
    p_periodo_fine DATE
) RETURNS TABLE(
    score_puntualita  NUMERIC,
    score_qualita     NUMERIC,
    score_compliance  NUMERIC,
    score_totale      NUMERIC,
    classe_rating     CHAR,
    ordini_analizzati INTEGER,
    nc_trovate        INTEGER
) AS $$
DECLARE
    v_ordini_totali      INTEGER;
    v_ordini_puntuali    INTEGER;
    v_nc_count           INTEGER;
    v_cert_count         INTEGER;
    v_s_puntualita       NUMERIC;
    v_s_qualita          NUMERIC;
    v_s_compliance       NUMERIC;
    v_s_totale           NUMERIC;
    v_classe             CHAR;
BEGIN
    -- Ordini e puntualità nel periodo
    SELECT
        COUNT(*),
        COUNT(*) FILTER (WHERE data_consegna IS NOT NULL AND data_consegna <= data_ordine + INTERVAL '3 days')
    INTO v_ordini_totali, v_ordini_puntuali
    FROM ordini_fornitori
    WHERE hotel_id = p_hotel_id
      AND fornitore_id = p_fornitore_id
      AND data_ordine BETWEEN p_periodo_inizio AND p_periodo_fine;

    -- NC aperte nel periodo (tabella non_conformita se esiste)
    BEGIN
        SELECT COUNT(*) INTO v_nc_count
        FROM non_conformita
        WHERE hotel_id = p_hotel_id
          AND fornitore_id = p_fornitore_id
          AND created_at::DATE BETWEEN p_periodo_inizio AND p_periodo_fine;
    EXCEPTION WHEN undefined_table THEN
        v_nc_count := 0;
    END;

    -- Certificazioni attive
    SELECT (
        CASE WHEN cert_haccp    THEN 1 ELSE 0 END +
        CASE WHEN cert_iso22000 THEN 1 ELSE 0 END +
        CASE WHEN cert_iso14001 THEN 1 ELSE 0 END +
        CASE WHEN cert_iso9001  THEN 1 ELSE 0 END +
        CASE WHEN cert_iso22005 THEN 1 ELSE 0 END
    ) INTO v_cert_count
    FROM fornitori WHERE id = p_fornitore_id;

    -- Calcolo score puntualità (0-100)
    v_s_puntualita := CASE
        WHEN v_ordini_totali = 0 THEN 50
        ELSE ROUND((v_ordini_puntuali::NUMERIC / v_ordini_totali) * 100, 1)
    END;

    -- Calcolo score qualità basato su NC rate
    v_s_qualita := CASE
        WHEN v_ordini_totali = 0 THEN 50
        WHEN v_nc_count = 0 THEN 100
        ELSE GREATEST(0, ROUND(100 - (v_nc_count::NUMERIC / v_ordini_totali) * 100 * 5, 1))
    END;

    -- Calcolo score compliance certificazioni
    v_s_compliance := LEAST(100, v_cert_count * 20);

    -- Score totale ponderato (Cribis / Ivalua weights)
    -- puntualità 30% + qualità 25% + compliance 15% + reattività 10% + prezzo 20%
    -- (prezzo e reattività non automatizzabili senza dati aggiuntivi → pesati a 50 default)
    v_s_totale := ROUND(
        v_s_puntualita * 0.30 +
        v_s_qualita    * 0.25 +
        50             * 0.20 +   -- prezzo: neutro se non configurato
        v_s_compliance * 0.15 +
        50             * 0.10,    -- reattività: neutro se non configurato
    1);

    -- Classificazione
    v_classe := CASE
        WHEN v_s_totale >= 90 THEN 'A'  -- Strategic Partner
        WHEN v_s_totale >= 70 THEN 'B'  -- Preferred Supplier
        WHEN v_s_totale >= 50 THEN 'C'  -- Approved Supplier
        ELSE 'D'                         -- At Risk
    END;

    RETURN QUERY SELECT
        v_s_puntualita, v_s_qualita, v_s_compliance::NUMERIC,
        v_s_totale, v_classe,
        v_ordini_totali, v_nc_count;
END;
$$ LANGUAGE plpgsql;


-- ═══════════════════════════════════════════════════════════════════
--  TRIGGER: auto-aggiorna updated_at
-- ═══════════════════════════════════════════════════════════════════
CREATE TRIGGER trg_sla_contracts_updated
    BEFORE UPDATE ON sla_contracts
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER trg_sla_alerts_updated
    BEFORE UPDATE ON sla_alerts
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER trg_partnership_updated
    BEFORE UPDATE ON partnership_agreements
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER trg_pmeetings_updated
    BEFORE UPDATE ON partnership_meetings
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();


-- ═══════════════════════════════════════════════════════════════════
--  ROW LEVEL SECURITY
-- ═══════════════════════════════════════════════════════════════════
ALTER TABLE vendor_rating_history   ENABLE ROW LEVEL SECURITY;
ALTER TABLE vendor_kpi_events       ENABLE ROW LEVEL SECURITY;
ALTER TABLE sla_contracts           ENABLE ROW LEVEL SECURITY;
ALTER TABLE sla_kpi_measurements    ENABLE ROW LEVEL SECURITY;
ALTER TABLE sla_alerts              ENABLE ROW LEVEL SECURITY;
ALTER TABLE partnership_agreements  ENABLE ROW LEVEL SECURITY;
ALTER TABLE partnership_meetings    ENABLE ROW LEVEL SECURITY;
ALTER TABLE partnership_scorecard   ENABLE ROW LEVEL SECURITY;


-- ═══════════════════════════════════════════════════════════════════
--  DATI DI TEST
-- ═══════════════════════════════════════════════════════════════════
DO $$
DECLARE
    v_hotel_id UUID;
    v_forn_id  UUID;
    v_sla_id   UUID;
    v_part_id  UUID;
BEGIN
    SELECT id INTO v_hotel_id FROM hotels WHERE nome = 'Hotel BAD.S Demo' LIMIT 1;
    SELECT id INTO v_forn_id  FROM fornitori WHERE hotel_id = v_hotel_id LIMIT 1;
    IF v_hotel_id IS NULL OR v_forn_id IS NULL THEN RETURN; END IF;

    -- Rating storico demo
    INSERT INTO vendor_rating_history (hotel_id, fornitore_id, periodo, score_totale,
        score_puntualita, score_qualita, score_prezzo, score_compliance, score_reattivita,
        classe_rating, ordini_totali, nc_aperte)
    VALUES
        (v_hotel_id, v_forn_id, '2026-01', 82.5, 88.0, 79.0, 80.0, 80.0, 75.0, 'B', 22, 1),
        (v_hotel_id, v_forn_id, '2026-02', 85.0, 91.0, 83.0, 82.0, 80.0, 78.0, 'B', 19, 0),
        (v_hotel_id, v_forn_id, '2026-03', 88.5, 94.0, 86.0, 85.0, 80.0, 82.0, 'B', 24, 0)
    ON CONFLICT (hotel_id, fornitore_id, periodo) DO NOTHING;

    -- SLA demo
    INSERT INTO sla_contracts (hotel_id, fornitore_id, nome, categoria,
        data_inizio, data_scadenza, target_otd_pct, target_qualita_pct, stato, prossima_review)
    VALUES (v_hotel_id, v_forn_id, 'SLA Forniture Alimentari Fresco 2026',
        'food_fresh', '2026-01-01', '2026-12-31', 95.0, 98.0, 'attivo', '2026-06-30')
    ON CONFLICT DO NOTHING
    RETURNING id INTO v_sla_id;

    -- Partnership demo
    INSERT INTO partnership_agreements (hotel_id, fornitore_id, nome, livello,
        data_inizio, sconto_volume_pct, quota_categoria_pct, frequenza_review, stato)
    VALUES (v_hotel_id, v_forn_id, 'Partnership Strategica Fornitore Principale 2025-2027',
        'preferred', '2025-01-01', 5.0, 70.0, 'semestrale', 'attivo')
    ON CONFLICT DO NOTHING;
END;
$$;

SELECT 'BAD.S Vendor Rating + SLA Manager + Partnership schema v1.0.0 ✅' AS risultato;
