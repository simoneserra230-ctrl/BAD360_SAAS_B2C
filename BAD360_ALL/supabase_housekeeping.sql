-- ═══════════════════════════════════════════════════════════════════
--  BAD.S Unified Platform — Modulo Housekeeping & Lavanderia
--  Esegui su: Supabase Dashboard → SQL Editor → Run
--  Versione: 1.0.0 | Fonti: Cora Hospitality, Finlogic EMS,
--            Detergo Industry 5.0, B2Scout, Suitex International
-- ═══════════════════════════════════════════════════════════════════

-- ═══════════════════════════════════════════════════════════════════
--  TABELLA: hk_rooms
--  Anagrafica camere con stato HK e ciclo pulizia
-- ═══════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS hk_rooms (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    hotel_id        UUID REFERENCES hotels(id) ON DELETE CASCADE,
    numero          TEXT NOT NULL,              -- "101", "201A"
    piano           INTEGER,
    tipo            TEXT DEFAULT 'standard',    -- standard | superior | suite | appartamento
    n_letti         INTEGER DEFAULT 1,
    superficie_mq   NUMERIC(6,1),
    -- Stato attuale
    stato_hk        TEXT DEFAULT 'pulita',      -- pulita | da_pulire | in_pulizia | ispezionata | fuori_servizio
    stato_occupazione TEXT DEFAULT 'libera',    -- libera | occupata | in_partenza | bloccata
    -- Frequenza pulizia
    frequenza_pulizia TEXT DEFAULT 'giornaliera', -- giornaliera | a_richiesta | ogni_3gg
    ultima_pulizia  TIMESTAMPTZ,
    prossima_pulizia DATE,
    -- Assignazione
    addetta_id      UUID REFERENCES auth.users(id),
    priorita        INTEGER DEFAULT 2 CHECK (priorita BETWEEN 1 AND 3), -- 1=alta 2=normale 3=bassa
    note            TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(hotel_id, numero)
);

CREATE INDEX IF NOT EXISTS idx_hk_rooms_hotel_stato ON hk_rooms(hotel_id, stato_hk);
CREATE INDEX IF NOT EXISTS idx_hk_rooms_piano ON hk_rooms(hotel_id, piano);

-- ═══════════════════════════════════════════════════════════════════
--  TABELLA: hk_tasks
--  Attività di pulizia con checklist operativa
-- ═══════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS hk_tasks (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    hotel_id        UUID REFERENCES hotels(id) ON DELETE CASCADE,
    room_id         UUID REFERENCES hk_rooms(id) ON DELETE CASCADE,
    tipo            TEXT NOT NULL,              -- check_out | stay_over | deepclean | ispezione | fuori_servizio
    stato           TEXT DEFAULT 'assegnato',   -- assegnato | in_corso | completato | nc | saltato
    priorita        INTEGER DEFAULT 2,
    -- Tempi
    assegnato_a     UUID REFERENCES auth.users(id),
    assegnato_da    TEXT,                       -- nome supervisor
    data_pianificata DATE NOT NULL DEFAULT CURRENT_DATE,
    ora_inizio      TIMESTAMPTZ,
    ora_fine        TIMESTAMPTZ,
    durata_min      INTEGER,                    -- minuti effettivi
    -- Checklist completamento (JSONB array di {voce, fatto, note})
    checklist       JSONB DEFAULT '[]',
    -- Biancheria cambiata
    lenzuola_cambiate   BOOLEAN DEFAULT FALSE,
    asciugamani_cambiati BOOLEAN DEFAULT FALSE,
    n_set_biancheria    INTEGER DEFAULT 0,
    -- Qualità
    punteggio_ispezione INTEGER CHECK (punteggio_ispezione BETWEEN 0 AND 100),
    ispezionato_da  TEXT,
    nc_rilevate     TEXT,                       -- descrizione non conformità
    -- Prodotti consumati (JSONB {prodotto_id, quantita})
    prodotti_usati  JSONB DEFAULT '[]',
    note            TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_hk_tasks_hotel_data ON hk_tasks(hotel_id, data_pianificata DESC);
CREATE INDEX IF NOT EXISTS idx_hk_tasks_stato ON hk_tasks(hotel_id, stato);
CREATE INDEX IF NOT EXISTS idx_hk_tasks_room ON hk_tasks(room_id, data_pianificata DESC);

-- ═══════════════════════════════════════════════════════════════════
--  TABELLA: hk_supplies
--  Scorte prodotti housekeeping con par level
--  (detergenti, amenities, biancheria, materiale vario)
-- ═══════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS hk_supplies (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    hotel_id        UUID REFERENCES hotels(id) ON DELETE CASCADE,
    nome            TEXT NOT NULL,
    categoria       TEXT NOT NULL,              -- detergente | amenity | biancheria | carta | altro
    sottocategoria  TEXT,                       -- es. "lenzuola matrimoniali", "shampoo 30ml"
    unita_misura    TEXT DEFAULT 'pz',          -- pz | lt | kg | rotoli
    fornitore_id    UUID REFERENCES fornitori(id),
    prezzo_unitario NUMERIC(10,4),
    -- Stock
    giacenza_attuale NUMERIC(12,2) DEFAULT 0,
    par_level       NUMERIC(12,2),              -- scorta target
    punto_riordino  NUMERIC(12,2),              -- soglia alert
    scorta_minima   NUMERIC(12,2),
    -- Consumo medio
    consumo_medio_giornaliero NUMERIC(8,3),     -- calcolato automaticamente
    lead_time_giorni INTEGER DEFAULT 3,
    -- Posizione
    ubicazione      TEXT,                       -- "magazzino HK piano 1"
    note            TEXT,
    attivo          BOOLEAN DEFAULT TRUE,
    ultimo_aggiornamento TIMESTAMPTZ DEFAULT NOW(),
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_hk_supplies_hotel ON hk_supplies(hotel_id, categoria);
CREATE INDEX IF NOT EXISTS idx_hk_supplies_alert ON hk_supplies(hotel_id, giacenza_attuale, punto_riordino);

-- ═══════════════════════════════════════════════════════════════════
--  TABELLA: hk_supply_movements
--  Movimenti magazzino HK (carichi, scarichi, inventari)
-- ═══════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS hk_supply_movements (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    hotel_id        UUID REFERENCES hotels(id) ON DELETE CASCADE,
    supply_id       UUID REFERENCES hk_supplies(id) ON DELETE CASCADE,
    tipo            TEXT NOT NULL,              -- carico | scarico | inventario | reso
    quantita        NUMERIC(10,3) NOT NULL,
    giacenza_dopo   NUMERIC(12,2),
    riferimento     TEXT,                       -- n. ordine, task_id, ecc.
    operatore       TEXT,
    note            TEXT,
    timestamp       TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_hk_movements_supply ON hk_supply_movements(supply_id, timestamp DESC);

-- ═══════════════════════════════════════════════════════════════════
--  TABELLA: laundry_contracts
--  Contratti con lavanderie esterne
-- ═══════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS laundry_contracts (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    hotel_id        UUID REFERENCES hotels(id) ON DELETE CASCADE,
    fornitore_id    UUID REFERENCES fornitori(id),
    nome_lavanderia TEXT NOT NULL,
    tipo_contratto  TEXT DEFAULT 'noleggio',    -- noleggio | solo_lavaggio | misto
    -- Tariffe (€)
    tariffa_lenzuola    NUMERIC(8,4),           -- €/pezzo
    tariffa_asciugamani NUMERIC(8,4),
    tariffa_accappatoio NUMERIC(8,4),
    tariffa_tovagliato  NUMERIC(8,4),
    tariffa_kg          NUMERIC(8,4),           -- alternativa a pezzo
    -- Servizio
    frequenza_ritiro TEXT DEFAULT 'giornaliero', -- giornaliero | trisettimanale | settimanale
    orario_ritiro   TEXT,                        -- "08:00"
    orario_consegna TEXT,                        -- "14:00"
    lead_time_ore   INTEGER DEFAULT 24,          -- ore da ritiro a riconsegna
    -- Dotazione noleggio (pezzi in circolazione)
    dotazione_lenzuola      INTEGER DEFAULT 0,
    dotazione_asciugamani   INTEGER DEFAULT 0,
    dotazione_accappatoi    INTEGER DEFAULT 0,
    dotazione_tovagliato    INTEGER DEFAULT 0,
    -- Contratto
    data_inizio     DATE,
    data_scadenza   DATE,
    importo_mensile_stimato NUMERIC(10,2),
    attivo          BOOLEAN DEFAULT TRUE,
    note            TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

-- ═══════════════════════════════════════════════════════════════════
--  TABELLA: laundry_cycles
--  Cicli di ritiro/consegna biancheria
--  Fonte: Finlogic EMS, Detergo Industry 5.0
-- ═══════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS laundry_cycles (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    hotel_id        UUID REFERENCES hotels(id) ON DELETE CASCADE,
    contract_id     UUID REFERENCES laundry_contracts(id),
    -- Ritiro
    data_ritiro     DATE NOT NULL DEFAULT CURRENT_DATE,
    ora_ritiro      TIME,
    operatore_ritiro TEXT,
    -- Pezzi ritirati (conteggio uscita)
    lenzuola_out        INTEGER DEFAULT 0,
    asciugamani_out     INTEGER DEFAULT 0,
    accappatoi_out      INTEGER DEFAULT 0,
    tovagliato_out      INTEGER DEFAULT 0,
    altro_out_kg        NUMERIC(8,2),           -- biancheria varia in kg
    -- Consegna
    data_consegna   DATE,
    ora_consegna    TIME,
    operatore_consegna TEXT,
    -- Pezzi consegnati (conteggio entrata)
    lenzuola_in         INTEGER DEFAULT 0,
    asciugamani_in      INTEGER DEFAULT 0,
    accappatoi_in       INTEGER DEFAULT 0,
    tovagliato_in       INTEGER DEFAULT 0,
    -- Scarti e NC
    pezzi_scartati      INTEGER DEFAULT 0,      -- macchiati, strappati
    nc_rilevate         TEXT,
    -- Costi
    costo_ciclo     NUMERIC(10,2),
    fattura_riferimento TEXT,
    -- Stato
    stato           TEXT DEFAULT 'ritirato',    -- ritirato | consegnato | nc | fatturato
    note            TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_laundry_cycles_hotel ON laundry_cycles(hotel_id, data_ritiro DESC);
CREATE INDEX IF NOT EXISTS idx_laundry_cycles_stato ON laundry_cycles(hotel_id, stato);

-- ═══════════════════════════════════════════════════════════════════
--  TABELLA: hk_kpi_daily
--  KPI giornalieri housekeeping (aggregati per report)
-- ═══════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS hk_kpi_daily (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    hotel_id        UUID REFERENCES hotels(id) ON DELETE CASCADE,
    data            DATE NOT NULL,
    -- Produttività
    camere_pulite       INTEGER DEFAULT 0,
    camere_ispezionate  INTEGER DEFAULT 0,
    camere_nc           INTEGER DEFAULT 0,
    ore_lavorate        NUMERIC(6,2),
    camere_ora          NUMERIC(5,2),           -- KPI: camere/ora
    -- Qualità
    punteggio_medio_ispezione NUMERIC(5,2),     -- 0-100
    tasso_nc_pct        NUMERIC(5,2),           -- % camere con NC
    -- Biancheria
    kg_biancheria_out   NUMERIC(8,2),
    kg_biancheria_in    NUMERIC(8,2),
    costo_lavanderia    NUMERIC(10,2),
    costo_lavanderia_camera NUMERIC(8,4),       -- €/camera occupata
    -- Prodotti
    costo_prodotti_hk   NUMERIC(10,2),
    costo_hk_camera     NUMERIC(8,4),           -- €/camera pulita (totale)
    -- Occupazione
    camere_occupate     INTEGER DEFAULT 0,
    tasso_occupazione_pct NUMERIC(5,2),
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(hotel_id, data)
);

CREATE INDEX IF NOT EXISTS idx_hk_kpi_hotel_data ON hk_kpi_daily(hotel_id, data DESC);

-- ═══════════════════════════════════════════════════════════════════
--  TRIGGER: aggiorna updated_at
-- ═══════════════════════════════════════════════════════════════════
CREATE TRIGGER trg_hk_rooms_updated
    BEFORE UPDATE ON hk_rooms
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER trg_hk_tasks_updated
    BEFORE UPDATE ON hk_tasks
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER trg_laundry_contracts_updated
    BEFORE UPDATE ON laundry_contracts
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- ═══════════════════════════════════════════════════════════════════
--  ROW LEVEL SECURITY
-- ═══════════════════════════════════════════════════════════════════
ALTER TABLE hk_rooms             ENABLE ROW LEVEL SECURITY;
ALTER TABLE hk_tasks             ENABLE ROW LEVEL SECURITY;
ALTER TABLE hk_supplies          ENABLE ROW LEVEL SECURITY;
ALTER TABLE hk_supply_movements  ENABLE ROW LEVEL SECURITY;
ALTER TABLE laundry_contracts    ENABLE ROW LEVEL SECURITY;
ALTER TABLE laundry_cycles       ENABLE ROW LEVEL SECURITY;
ALTER TABLE hk_kpi_daily         ENABLE ROW LEVEL SECURITY;

-- ═══════════════════════════════════════════════════════════════════
--  FUNZIONE: calcola par level biancheria automatico
--  Formula: (n_camere × set_per_camera × rotation_factor) + scorta_sicurezza
-- ═══════════════════════════════════════════════════════════════════
CREATE OR REPLACE FUNCTION calc_linen_par_level(
    p_n_camere INTEGER,
    p_set_per_camera NUMERIC DEFAULT 3.0,
    p_rotation_days INTEGER DEFAULT 2,
    p_safety_factor NUMERIC DEFAULT 1.2
) RETURNS TABLE(
    par_lenzuola INTEGER,
    par_asciugamani INTEGER,
    par_accappatoi INTEGER,
    scorta_sicurezza_lenzuola INTEGER
) AS $$
BEGIN
    RETURN QUERY SELECT
        -- Lenzuola: 2 lenzuola per letto, set di rotazione * safety
        ROUND((p_n_camere * 2 * p_set_per_camera * p_safety_factor))::INTEGER,
        -- Asciugamani: media 2 per camera (bagno + viso)
        ROUND((p_n_camere * 2 * p_set_per_camera * p_safety_factor))::INTEGER,
        -- Accappatoi: 1 per camera (solo strutture 4-5*)
        ROUND((p_n_camere * 1 * p_set_per_camera * p_safety_factor))::INTEGER,
        -- Scorta sicurezza lenzuola (lead time lavanderia)
        ROUND((p_n_camere * 2 * p_rotation_days * 0.3))::INTEGER;
END;
$$ LANGUAGE plpgsql;

-- ═══════════════════════════════════════════════════════════════════
--  DATI DI TEST
-- ═══════════════════════════════════════════════════════════════════
DO $$
DECLARE v_hotel_id UUID;
BEGIN
    SELECT id INTO v_hotel_id FROM hotels WHERE nome = 'Hotel BAD.S Demo' LIMIT 1;
    IF v_hotel_id IS NULL THEN RETURN; END IF;

    -- Camere demo
    INSERT INTO hk_rooms (hotel_id, numero, piano, tipo, stato_hk, stato_occupazione, n_letti, superficie_mq)
    VALUES
        (v_hotel_id, '101', 1, 'standard',  'da_pulire', 'in_partenza', 2, 22),
        (v_hotel_id, '102', 1, 'standard',  'pulita',    'libera',      2, 22),
        (v_hotel_id, '103', 1, 'superior',  'in_pulizia','occupata',    2, 28),
        (v_hotel_id, '201', 2, 'standard',  'da_pulire', 'in_partenza', 1, 20),
        (v_hotel_id, '202', 2, 'suite',     'ispezionata','occupata',   2, 45),
        (v_hotel_id, '203', 2, 'standard',  'pulita',    'libera',      2, 22)
    ON CONFLICT (hotel_id, numero) DO NOTHING;

    -- Forniture HK demo
    INSERT INTO hk_supplies (hotel_id, nome, categoria, unita_misura, giacenza_attuale, par_level, punto_riordino, prezzo_unitario)
    VALUES
        (v_hotel_id, 'Detergente multiuso 5L',    'detergente', 'lt',  45, 80,  20, 4.50),
        (v_hotel_id, 'Candeggina 5L',             'detergente', 'lt',  12, 40,  10, 2.80),
        (v_hotel_id, 'Shampoo monodose 30ml',     'amenity',    'pz',  380, 600, 150, 0.35),
        (v_hotel_id, 'Gel doccia 30ml',           'amenity',    'pz',  420, 600, 150, 0.35),
        (v_hotel_id, 'Sapone mani 20ml',          'amenity',    'pz',  280, 500, 120, 0.22),
        (v_hotel_id, 'Carta igienica 2 veli',     'carta',      'rotoli', 95, 200, 50, 0.28),
        (v_hotel_id, 'Sacchetti pattumiera 10L',  'altro',      'pz',  180, 300, 80, 0.08),
        (v_hotel_id, 'Lenzuola matrimoniali',     'biancheria', 'pz',  88,  120, 30, 12.00),
        (v_hotel_id, 'Asciugamani viso 50x100',   'biancheria', 'pz',  140, 200, 50, 4.50),
        (v_hotel_id, 'Accappatoi taglia M',       'biancheria', 'pz',  40,  60,  15, 25.00)
    ON CONFLICT DO NOTHING;

END;
$$;

SELECT 'BAD.S Housekeeping & Laundry schema v1.0.0 creato ✅' AS risultato;
