-- ═══════════════════════════════════════════════════════════════════
--  BAD.S Unified Platform — Migration: Vendor Rating · SLA · Partnership
--  Eseguire su Supabase SQL Editor dopo supabase_setup.sql
--  Dipendenze: hotels, fornitori (da supabase_setup.sql)
-- ═══════════════════════════════════════════════════════════════════

-- ───────────────────────────────────────────────────────────────────
--  1. VENDOR RATING HISTORY
--     Storico rating mensile/trimestrale per fornitore
--     Formula pesata: OTD 30% · Qualità 25% · Prezzo 20% · Compliance 15% · Reattività 10%
--     Fonte metodologica: Cribis D&B / Ivalua SCM Benchmark 2024
-- ───────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS vendor_rating_history (
    id                          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    hotel_id                    UUID NOT NULL REFERENCES hotels(id) ON DELETE CASCADE,
    fornitore_id                UUID NOT NULL REFERENCES fornitori(id) ON DELETE CASCADE,
    periodo                     TEXT NOT NULL,          -- "2026-03" (mese) o "2026-Q1" (trimestre)
    -- Score aggregato e componenti (0-100)
    score_totale                NUMERIC(5,2) NOT NULL,
    score_puntualita            NUMERIC(5,2),           -- OTD/OTIF
    score_qualita               NUMERIC(5,2),           -- % ordini senza NC
    score_prezzo                NUMERIC(5,2),           -- stabilità e competitività prezzo
    score_compliance            NUMERIC(5,2),           -- certificazioni + requisiti normativi
    score_reattivita            NUMERIC(5,2),           -- tempo risposta reclami/urgenze
    -- Classificazione
    classe_rating               TEXT CHECK (classe_rating IN ('A','B','C','D')),
    -- Dati grezzi aggregati del periodo
    ordini_totali               INTEGER DEFAULT 0,
    nc_aperte                   INTEGER DEFAULT 0,
    -- Trend vs periodo precedente
    variazione_vs_periodo_prec  NUMERIC(5,2),           -- positivo = miglioramento
    flag_miglioramento          BOOLEAN DEFAULT FALSE,
    flag_peggioramento          BOOLEAN DEFAULT FALSE,
    -- Override manuale (es. audit straordinario)
    override_manuale            BOOLEAN DEFAULT FALSE,
    motivo_override             TEXT,
    operatore_override          TEXT,
    -- Metadati
    created_at                  TIMESTAMPTZ DEFAULT NOW(),
    updated_at                  TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (hotel_id, fornitore_id, periodo)            -- un rating per fornitore per periodo
);

CREATE INDEX IF NOT EXISTS idx_vr_hotel_periodo
    ON vendor_rating_history (hotel_id, periodo DESC);
CREATE INDEX IF NOT EXISTS idx_vr_fornitore
    ON vendor_rating_history (fornitore_id, periodo DESC);
CREATE INDEX IF NOT EXISTS idx_vr_classe
    ON vendor_rating_history (classe_rating, hotel_id);

COMMENT ON TABLE vendor_rating_history IS
    'Storico Vendor Rating mensile/trimestrale. Formula: OTD 30%+Qualità 25%+Prezzo 20%+Compliance 15%+Reattività 10%. Fonte: Cribis/Ivalua 2024.';


-- ───────────────────────────────────────────────────────────────────
--  2. VENDOR KPI EVENTS
--     Evento granulare singolo (consegna, NC, variazione prezzo…)
--     Alimenta il calcolo automatico del rating mensile
-- ───────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS vendor_kpi_events (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    hotel_id        UUID NOT NULL REFERENCES hotels(id) ON DELETE CASCADE,
    fornitore_id    UUID NOT NULL REFERENCES fornitori(id) ON DELETE CASCADE,
    ordine_id       UUID REFERENCES ordini_fornitori(id) ON DELETE SET NULL,
    tipo_evento     TEXT NOT NULL,          -- consegna_puntuale | consegna_ritardo | nc_aperta |
                                            -- nc_chiusa | deviazione_prezzo | risposta_rapida |
                                            -- risposta_lenta | scarto_merce
    data_evento     DATE NOT NULL DEFAULT CURRENT_DATE,
    valore          NUMERIC(10,4) DEFAULT 0,   -- es. ore ritardo, % scostamento prezzo
    valore_atteso   NUMERIC(10,4) DEFAULT 0,   -- valore target SLA
    conforme        BOOLEAN DEFAULT TRUE,
    note            TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_vke_hotel_forn
    ON vendor_kpi_events (hotel_id, fornitore_id, data_evento DESC);
CREATE INDEX IF NOT EXISTS idx_vke_tipo
    ON vendor_kpi_events (tipo_evento, data_evento DESC);


-- ───────────────────────────────────────────────────────────────────
--  3. SLA CONTRACTS
--     Contratto SLA con KPI target e penali per fornitore
--     Fonte: Deepser SLA Guide + EENA Best Practice Contrattuale 2024
-- ───────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS sla_contracts (
    id                      UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    hotel_id                UUID NOT NULL REFERENCES hotels(id) ON DELETE CASCADE,
    fornitore_id            UUID NOT NULL REFERENCES fornitori(id) ON DELETE CASCADE,
    nome                    TEXT NOT NULL,
    categoria               TEXT NOT NULL,      -- food_fresh | beverage | chimici | tessile | manutenzione | tech
    data_inizio             DATE NOT NULL,
    data_scadenza           DATE,
    -- Target KPI
    target_otd_pct          NUMERIC(5,2) DEFAULT 95.0,
    target_otif_pct         NUMERIC(5,2) DEFAULT 93.0,
    target_qualita_pct      NUMERIC(5,2) DEFAULT 98.0,
    target_prezzo_var_pct   NUMERIC(5,2) DEFAULT 3.0,
    target_risposta_ore     NUMERIC(6,2) DEFAULT 24.0,
    -- Penali
    penale_ritardo_pct      NUMERIC(5,2) DEFAULT 0.5,
    penale_nc_pct           NUMERIC(5,2) DEFAULT 3.0,
    penale_max_mensile_pct  NUMERIC(5,2) DEFAULT 10.0,
    -- Governance
    frequenza_review        TEXT DEFAULT 'trimestrale'
                            CHECK (frequenza_review IN ('mensile','trimestrale','semestrale')),
    prossima_review         DATE,
    rinnovo_automatico      BOOLEAN DEFAULT TRUE,
    stato                   TEXT DEFAULT 'attivo'
                            CHECK (stato IN ('attivo','scaduto','sospeso','rescisso')),
    note_legali             TEXT,
    note                    TEXT,
    created_at              TIMESTAMPTZ DEFAULT NOW(),
    updated_at              TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_sla_hotel_stato
    ON sla_contracts (hotel_id, stato);
CREATE INDEX IF NOT EXISTS idx_sla_fornitore
    ON sla_contracts (fornitore_id);
CREATE INDEX IF NOT EXISTS idx_sla_review
    ON sla_contracts (prossima_review ASC) WHERE stato = 'attivo';


-- ───────────────────────────────────────────────────────────────────
--  4. SLA KPI MEASUREMENTS
--     Misurazioni periodiche vs target SLA
-- ───────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS sla_kpi_measurements (
    id                      UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    sla_id                  UUID NOT NULL REFERENCES sla_contracts(id) ON DELETE CASCADE,
    hotel_id                UUID NOT NULL REFERENCES hotels(id) ON DELETE CASCADE,
    fornitore_id            UUID REFERENCES fornitori(id) ON DELETE SET NULL,
    periodo                 TEXT NOT NULL,              -- "2026-03"
    -- Dati grezzi
    n_ordini                INTEGER DEFAULT 0,
    n_ordini_puntuali       INTEGER DEFAULT 0,
    n_nc                    INTEGER DEFAULT 0,
    -- KPI misurati
    otd_misurato_pct        NUMERIC(5,2),
    otif_misurato_pct       NUMERIC(5,2),
    qualita_misurata_pct    NUMERIC(5,2),
    prezzo_var_misurata_pct NUMERIC(5,2),
    risposta_media_ore      NUMERIC(6,2),
    -- Esito conformità per KPI
    otd_ok                  BOOLEAN,
    otif_ok                 BOOLEAN,
    qualita_ok              BOOLEAN,
    prezzo_ok               BOOLEAN,
    risposta_ok             BOOLEAN,
    -- Score aggregato
    compliance_score        NUMERIC(5,2),               -- % KPI conformi (0-100)
    penali_euro             NUMERIC(10,2) DEFAULT 0,
    note                    TEXT,
    created_at              TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (sla_id, periodo)
);

CREATE INDEX IF NOT EXISTS idx_slakpi_hotel_periodo
    ON sla_kpi_measurements (hotel_id, periodo DESC);


-- ───────────────────────────────────────────────────────────────────
--  5. SLA ALERTS
--     Alert KPI fuori soglia generati automaticamente
-- ───────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS sla_alerts (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    sla_id          UUID NOT NULL REFERENCES sla_contracts(id) ON DELETE CASCADE,
    hotel_id        UUID NOT NULL REFERENCES hotels(id) ON DELETE CASCADE,
    fornitore_id    UUID REFERENCES fornitori(id) ON DELETE SET NULL,
    kpi_nome        TEXT NOT NULL,              -- otd | otif | qualita | prezzo | risposta
    scostamento     NUMERIC(8,3),               -- negativo = sotto target
    severity        TEXT NOT NULL DEFAULT 'warning'
                    CHECK (severity IN ('warning','critical')),
    stato           TEXT NOT NULL DEFAULT 'aperto'
                    CHECK (stato IN ('aperto','in_gestione','chiuso')),
    note            TEXT,
    operatore       TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_slaalert_hotel_stato
    ON sla_alerts (hotel_id, stato, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_slaalert_severity
    ON sla_alerts (severity, stato);


-- ───────────────────────────────────────────────────────────────────
--  6. PARTNERSHIP AGREEMENTS
--     Accordi di partnership strategica hotel ↔ fornitore
--     Fonte: Marenzi (UniPD) — SCM hospitality 2025
--     Livelli: preferred (≥70) · strategic (≥85) · exclusive (≥92)
-- ───────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS partnership_agreements (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    hotel_id            UUID NOT NULL REFERENCES hotels(id) ON DELETE CASCADE,
    fornitore_id        UUID NOT NULL REFERENCES fornitori(id) ON DELETE CASCADE,
    nome                TEXT NOT NULL,
    livello             TEXT NOT NULL
                        CHECK (livello IN ('preferred','strategic','exclusive')),
    stato               TEXT NOT NULL DEFAULT 'attivo'
                        CHECK (stato IN ('attivo','sospeso','rescisso','scaduto')),
    data_inizio         DATE NOT NULL,
    data_scadenza       DATE,
    prossima_review     DATE,
    valore_contratto    NUMERIC(12,2),              -- € annui stimati
    categorie_coperte   TEXT[],                     -- es. ['food_fresh','beverage']
    note                TEXT,
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    updated_at          TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_part_hotel_stato
    ON partnership_agreements (hotel_id, stato);
CREATE INDEX IF NOT EXISTS idx_part_fornitore
    ON partnership_agreements (fornitore_id);
CREATE INDEX IF NOT EXISTS idx_part_review
    ON partnership_agreements (prossima_review ASC) WHERE stato = 'attivo';


-- ───────────────────────────────────────────────────────────────────
--  7. PARTNERSHIP MEETINGS
--     Meeting di review con agenda, verbale e action items
-- ───────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS partnership_meetings (
    id                      UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    partnership_id          UUID NOT NULL REFERENCES partnership_agreements(id) ON DELETE CASCADE,
    hotel_id                UUID NOT NULL REFERENCES hotels(id) ON DELETE CASCADE,
    fornitore_id            UUID REFERENCES fornitori(id) ON DELETE SET NULL,
    tipo                    TEXT NOT NULL DEFAULT 'trimestrale'
                            CHECK (tipo IN ('mensile','trimestrale','straordinario','kickoff','annual_review')),
    stato                   TEXT NOT NULL DEFAULT 'pianificato'
                            CHECK (stato IN ('pianificato','confermato','svolto','annullato')),
    data_pianificata        DATE NOT NULL,
    ora                     TIME,
    luogo                   TEXT,
    partecipanti_hotel      TEXT[],
    partecipanti_fornitore  TEXT[],
    agenda                  TEXT,
    verbale                 TEXT,
    esito                   TEXT CHECK (esito IN ('positivo','neutro','critico')),
    action_items            JSONB DEFAULT '[]',     -- [{azione, responsabile, scadenza, completato}]
    score_al_momento        NUMERIC(5,2),
    data_prossimo_meeting   DATE,
    created_at              TIMESTAMPTZ DEFAULT NOW(),
    updated_at              TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_meet_partnership
    ON partnership_meetings (partnership_id, data_pianificata DESC);
CREATE INDEX IF NOT EXISTS idx_meet_hotel_stato
    ON partnership_meetings (hotel_id, stato, data_pianificata DESC);


-- ───────────────────────────────────────────────────────────────────
--  8. PARTNERSHIP SCORECARD
--     Valutazione reciproca hotel ↔ fornitore su 6 dimensioni (scala 1-5)
-- ───────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS partnership_scorecard (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    partnership_id      UUID NOT NULL REFERENCES partnership_agreements(id) ON DELETE CASCADE,
    hotel_id            UUID NOT NULL REFERENCES hotels(id) ON DELETE CASCADE,
    fornitore_id        UUID REFERENCES fornitori(id) ON DELETE SET NULL,
    periodo             TEXT NOT NULL,              -- "2026-Q1"
    direzione           TEXT NOT NULL
                        CHECK (direzione IN ('hotel_su_fornitore','fornitore_su_hotel')),
    -- 6 dimensioni (1 = pessimo, 5 = eccellente)
    qualita_prodotto    SMALLINT CHECK (qualita_prodotto BETWEEN 1 AND 5),
    puntualita          SMALLINT CHECK (puntualita BETWEEN 1 AND 5),
    comunicazione       SMALLINT CHECK (comunicazione BETWEEN 1 AND 5),
    flessibilita        SMALLINT CHECK (flessibilita BETWEEN 1 AND 5),
    innovazione         SMALLINT CHECK (innovazione BETWEEN 1 AND 5),
    sostenibilita       SMALLINT CHECK (sostenibilita BETWEEN 1 AND 5),
    -- Score aggregato 0-100 (calcolato dal backend)
    score_aggregato     NUMERIC(5,2),
    note                TEXT,
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (partnership_id, periodo, direzione)
);

CREATE INDEX IF NOT EXISTS idx_scorecard_partnership
    ON partnership_scorecard (partnership_id, periodo DESC);


-- ───────────────────────────────────────────────────────────────────
--  9. RPC — calcola_vendor_rating
--     Funzione PostgreSQL chiamata da main.py per aggregare
--     score da ordini_fornitori, vendor_kpi_events e fornitori
-- ───────────────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION calcola_vendor_rating(
    p_hotel_id      UUID,
    p_fornitore_id  UUID,
    p_periodo_inizio DATE,
    p_periodo_fine   DATE
)
RETURNS TABLE (
    score_puntualita    NUMERIC,
    score_qualita       NUMERIC,
    score_compliance    NUMERIC,
    score_totale        NUMERIC,
    ordini_analizzati   INTEGER,
    nc_trovate          INTEGER
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_ordini_tot    INTEGER := 0;
    v_ordini_ptl    INTEGER := 0;
    v_nc_count      INTEGER := 0;
    v_s_puntualita  NUMERIC := 50;
    v_s_qualita     NUMERIC := 50;
    v_s_compliance  NUMERIC := 75;   -- default medio se no certificazioni
    v_s_totale      NUMERIC;
BEGIN
    -- Conteggio ordini nel periodo
    SELECT
        COUNT(*),
        SUM(CASE WHEN data_consegna_effettiva <= data_consegna_prevista
                      OR data_consegna_effettiva IS NULL THEN 1 ELSE 0 END)
    INTO v_ordini_tot, v_ordini_ptl
    FROM ordini_fornitori
    WHERE hotel_id    = p_hotel_id
      AND fornitore_id = p_fornitore_id
      AND data_ordine BETWEEN p_periodo_inizio AND p_periodo_fine;

    -- Score puntualità (OTD)
    IF v_ordini_tot > 0 THEN
        v_s_puntualita := ROUND(v_ordini_ptl::NUMERIC / v_ordini_tot * 100, 2);
    END IF;

    -- NC nel periodo da vendor_kpi_events
    SELECT COUNT(*)
    INTO v_nc_count
    FROM vendor_kpi_events
    WHERE hotel_id    = p_hotel_id
      AND fornitore_id = p_fornitore_id
      AND data_evento BETWEEN p_periodo_inizio AND p_periodo_fine
      AND tipo_evento IN ('nc_aperta','scarto_merce')
      AND NOT conforme;

    -- Score qualità: % ordini senza NC (approssimato)
    IF v_ordini_tot > 0 THEN
        v_s_qualita := ROUND(GREATEST(0, 100 - (v_nc_count::NUMERIC / v_ordini_tot * 100)), 2);
    END IF;

    -- Score compliance da certificazioni fornitore
    SELECT
        CASE
            WHEN certificazioni IS NOT NULL AND array_length(certificazioni, 1) >= 3 THEN 90
            WHEN certificazioni IS NOT NULL AND array_length(certificazioni, 1) >= 1 THEN 70
            ELSE 50
        END
    INTO v_s_compliance
    FROM fornitori
    WHERE id = p_fornitore_id;

    -- Score totale: OTD 30% + Qualità 25% + Prezzo 20%(default) + Compliance 15% + Reattività 10%(default)
    v_s_totale := ROUND(
        v_s_puntualita * 0.30 +
        v_s_qualita    * 0.25 +
        50             * 0.20 +   -- prezzo: default neutro senza dati specifici
        v_s_compliance * 0.15 +
        50             * 0.10,    -- reattività: default neutro
    2);

    RETURN QUERY SELECT
        v_s_puntualita,
        v_s_qualita,
        v_s_compliance,
        v_s_totale,
        v_ordini_tot,
        v_nc_count;
END;
$$;

COMMENT ON FUNCTION calcola_vendor_rating IS
    'Calcola Vendor Rating aggregando ordini_fornitori e vendor_kpi_events nel periodo. Chiamata da main.py via RPC.';


-- ───────────────────────────────────────────────────────────────────
--  10. RLC TRIGGER — aggiorna updated_at automaticamente
-- ───────────────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN NEW.updated_at = NOW(); RETURN NEW; END;
$$;

DO $$ BEGIN
    -- Applica trigger a tutte le tabelle nuove con updated_at
    DECLARE tbl TEXT;
    BEGIN
        FOREACH tbl IN ARRAY ARRAY[
            'vendor_rating_history','sla_contracts','sla_alerts',
            'partnership_agreements','partnership_meetings'
        ] LOOP
            EXECUTE format(
                'DROP TRIGGER IF EXISTS trg_%s_updated_at ON %I;
                 CREATE TRIGGER trg_%s_updated_at
                 BEFORE UPDATE ON %I
                 FOR EACH ROW EXECUTE FUNCTION set_updated_at();',
                tbl, tbl, tbl, tbl
            );
        END LOOP;
    END;
END $$;


-- ───────────────────────────────────────────────────────────────────
--  11. ROW LEVEL SECURITY
-- ───────────────────────────────────────────────────────────────────
DO $$ DECLARE tbl TEXT; BEGIN
    FOREACH tbl IN ARRAY ARRAY[
        'vendor_rating_history','vendor_kpi_events',
        'sla_contracts','sla_kpi_measurements','sla_alerts',
        'partnership_agreements','partnership_meetings','partnership_scorecard'
    ] LOOP
        EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY;', tbl);

        -- Service role (backend APScheduler / main.py): accesso totale
        EXECUTE format(
            'DROP POLICY IF EXISTS "service_role_%s" ON %I;
             CREATE POLICY "service_role_%s" ON %I
             FOR ALL USING (auth.role() = ''service_role'');',
            tbl, tbl, tbl, tbl
        );

        -- Utenti autenticati: solo il proprio hotel_id
        EXECUTE format(
            'DROP POLICY IF EXISTS "hotel_user_%s" ON %I;
             CREATE POLICY "hotel_user_%s" ON %I
             FOR SELECT USING (
                 hotel_id IN (
                     SELECT hotel_id FROM hotel_users
                     WHERE user_id = auth.uid() AND stato = ''attivo''
                 )
             );',
            tbl, tbl, tbl, tbl
        );
    END LOOP;
END $$;


-- ───────────────────────────────────────────────────────────────────
--  12. VISTA — v_vendor_ranking_corrente
--     Pronta per la dashboard frontend — join con fornitori
-- ───────────────────────────────────────────────────────────────────
CREATE OR REPLACE VIEW v_vendor_ranking_corrente AS
SELECT
    vrh.hotel_id,
    vrh.fornitore_id,
    f.ragione_sociale                               AS fornitore,
    f.categoria,
    vrh.periodo,
    vrh.score_totale,
    vrh.classe_rating                               AS classe,
    vrh.score_puntualita,
    vrh.score_qualita,
    vrh.score_compliance,
    vrh.variazione_vs_periodo_prec                  AS variazione,
    vrh.flag_miglioramento,
    vrh.flag_peggioramento,
    ROW_NUMBER() OVER (
        PARTITION BY vrh.hotel_id, vrh.periodo
        ORDER BY vrh.score_totale DESC
    )                                               AS posizione
FROM vendor_rating_history vrh
JOIN fornitori f ON f.id = vrh.fornitore_id;

COMMENT ON VIEW v_vendor_ranking_corrente IS
    'Ranking fornitori per periodo, con join fornitori. Usare WHERE hotel_id=X AND periodo=Y.';


-- ───────────────────────────────────────────────────────────────────
--  13. VISTA — v_sla_dashboard
--     Riepilogo SLA con ultimo score compliance per contratto
-- ───────────────────────────────────────────────────────────────────
CREATE OR REPLACE VIEW v_sla_dashboard AS
SELECT
    sc.id                                           AS sla_id,
    sc.hotel_id,
    sc.fornitore_id,
    f.ragione_sociale                               AS fornitore,
    sc.nome                                         AS contratto,
    sc.categoria,
    sc.stato,
    sc.prossima_review,
    sc.frequenza_review,
    sc.target_otd_pct,
    sc.target_qualita_pct,
    -- Ultimo score compliance
    latest.compliance_score,
    latest.periodo                                  AS ultimo_periodo_misurato,
    -- Alert aperti
    COALESCE(alerts.n_alert, 0)                    AS n_alert_aperti,
    COALESCE(alerts.n_critici, 0)                  AS n_critici
FROM sla_contracts sc
JOIN fornitori f ON f.id = sc.fornitore_id
LEFT JOIN LATERAL (
    SELECT compliance_score, periodo
    FROM sla_kpi_measurements
    WHERE sla_id = sc.id
    ORDER BY periodo DESC
    LIMIT 1
) latest ON TRUE
LEFT JOIN LATERAL (
    SELECT
        COUNT(*)                                    AS n_alert,
        SUM(CASE WHEN severity = 'critical' THEN 1 ELSE 0 END) AS n_critici
    FROM sla_alerts
    WHERE sla_id = sc.id AND stato = 'aperto'
) alerts ON TRUE;

COMMENT ON VIEW v_sla_dashboard IS
    'Dashboard SLA: ultimo score + alert aperti per ogni contratto.';


-- ───────────────────────────────────────────────────────────────────
--  14. DATI DEMO (opzionali — commentare in produzione)
--      Inserisce dati di esempio se la tabella hotels ha almeno 1 riga
-- ───────────────────────────────────────────────────────────────────
-- DO $$ DECLARE v_hotel UUID; v_forn UUID;
-- BEGIN
--     SELECT id INTO v_hotel FROM hotels LIMIT 1;
--     SELECT id INTO v_forn  FROM fornitori LIMIT 1;
--     IF v_hotel IS NOT NULL AND v_forn IS NOT NULL THEN
--         INSERT INTO vendor_rating_history (hotel_id, fornitore_id, periodo, score_totale, score_puntualita, score_qualita, score_compliance, classe_rating)
--         VALUES (v_hotel, v_forn, to_char(NOW(),'YYYY-MM'), 82.5, 91.0, 84.0, 78.0, 'B')
--         ON CONFLICT (hotel_id, fornitore_id, periodo) DO NOTHING;
--
--         INSERT INTO sla_contracts (hotel_id, fornitore_id, nome, categoria, data_inizio, target_otd_pct, target_qualita_pct)
--         VALUES (v_hotel, v_forn, 'SLA Demo Food Fresh 2026', 'food_fresh', CURRENT_DATE, 98, 99.5)
--         ON CONFLICT DO NOTHING;
--
--         INSERT INTO partnership_agreements (hotel_id, fornitore_id, nome, livello, data_inizio)
--         VALUES (v_hotel, v_forn, 'Partnership Demo 2025-2027', 'preferred', CURRENT_DATE)
--         ON CONFLICT DO NOTHING;
--     END IF;
-- END $$;
