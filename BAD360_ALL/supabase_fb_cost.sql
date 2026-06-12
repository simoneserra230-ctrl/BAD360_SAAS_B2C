-- ═══════════════════════════════════════════════════════════════════
--  BAD.S Unified Platform — Modulo Food & Beverage Cost
--  Aggiungi queste tabelle DOPO aver eseguito supabase_setup.sql
--  Versione: 1.0.0 | Aggiornato: 2026
-- ═══════════════════════════════════════════════════════════════════

-- ─────────────────────────────────────────────────────────────────
--  TABELLA: fb_ingredienti
--  Anagrafica ingredienti con costo acquisto aggiornabile
-- ─────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS fb_ingredienti (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    hotel_id        UUID REFERENCES hotels(id) ON DELETE CASCADE,
    nome            TEXT NOT NULL,
    categoria       TEXT NOT NULL,
    -- food: carne | pesce | verdure | latticini | secchi | bevande_alcoliche | analcolici | spirits | vini | birre
    unita_misura    TEXT DEFAULT 'kg',   -- kg | lt | pz | cl | ml
    costo_unitario  NUMERIC(10,4) NOT NULL,  -- prezzo acquisto per unità
    fornitore_id    UUID REFERENCES fornitori(id),
    allergeni       TEXT[],              -- Reg. UE 1169/2011: glutine, lattosio, noci, ecc.
    note            TEXT,
    attivo          BOOLEAN DEFAULT TRUE,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

-- ─────────────────────────────────────────────────────────────────
--  TABELLA: fb_ricette
--  Ricette complete con prezzo di vendita e categoria BCG
-- ─────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS fb_ricette (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    hotel_id        UUID REFERENCES hotels(id) ON DELETE CASCADE,
    nome            TEXT NOT NULL,
    tipo            TEXT NOT NULL,          -- food | beverage | cocktail | mocktail
    categoria       TEXT,                   -- antipasto | primo | secondo | dolce | aperitivo | long_drink | shot
    prezzo_vendita  NUMERIC(10,2) NOT NULL, -- prezzo al cliente (IVA esclusa)
    iva_pct         NUMERIC(5,2) DEFAULT 10.0, -- aliquota IVA (10% ristorazione, 22% alcolici)
    costo_ricetta   NUMERIC(10,4),          -- calcolato automaticamente dalla somma ingredienti
    food_cost_pct   NUMERIC(6,2),           -- costo_ricetta / prezzo_vendita * 100
    -- BCG Matrix (calcolata dal backend)
    bcg_categoria   TEXT,                   -- star | cash_cow | question_mark | dog
    bcg_popolarita  TEXT DEFAULT 'media',   -- alta | media | bassa
    -- Dati operativi
    tempo_prep_min  INTEGER,
    porzioni        INTEGER DEFAULT 1,
    note_allergie   TEXT,
    attiva          BOOLEAN DEFAULT TRUE,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

-- ─────────────────────────────────────────────────────────────────
--  TABELLA: fb_ricette_ingredienti
--  Dettaglio ingredienti per singola ricetta (distinta base)
-- ─────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS fb_ricette_ingredienti (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    ricetta_id      UUID REFERENCES fb_ricette(id) ON DELETE CASCADE,
    ingrediente_id  UUID REFERENCES fb_ingredienti(id),
    quantita        NUMERIC(10,4) NOT NULL,  -- quantità nell'unità di misura dell'ingrediente
    note            TEXT                     -- es: "garnish opzionale", "sostituzione possibile"
);

-- Index per join frequenti
CREATE INDEX IF NOT EXISTS idx_ricette_ing_ricetta ON fb_ricette_ingredienti(ricetta_id);
CREATE INDEX IF NOT EXISTS idx_ricette_ing_ingrediente ON fb_ricette_ingredienti(ingrediente_id);

-- ─────────────────────────────────────────────────────────────────
--  TABELLA: fb_vendite
--  Log vendite per calcolo food/bev cost reale (non teorico)
-- ─────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS fb_vendite (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    hotel_id        UUID REFERENCES hotels(id) ON DELETE CASCADE,
    ricetta_id      UUID REFERENCES fb_ricette(id),
    data_vendita    DATE NOT NULL DEFAULT CURRENT_DATE,
    turno           TEXT DEFAULT 'pranzo',  -- colazione | pranzo | cena | aperitivo | notte
    quantita_venduta INTEGER NOT NULL DEFAULT 1,
    prezzo_effettivo NUMERIC(10,2),         -- se diverso da prezzo_vendita (happy hour, sconti)
    revenue         NUMERIC(12,2),          -- quantita_venduta * prezzo_effettivo
    costo_totale    NUMERIC(12,4),          -- quantita_venduta * costo_ricetta
    food_cost_pct   NUMERIC(6,2),           -- costo_totale / revenue * 100
    note            TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_fb_vendite_hotel_data ON fb_vendite(hotel_id, data_vendita DESC);

-- ─────────────────────────────────────────────────────────────────
--  TABELLA: fb_inventario_snapshot
--  Snapshot inventario per calcolo food cost reale con formula:
--  FC reale = (Inv.Iniziale + Acquisti - Inv.Finale) / Revenue * 100
-- ─────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS fb_inventario_snapshot (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    hotel_id        UUID REFERENCES hotels(id) ON DELETE CASCADE,
    ingrediente_id  UUID REFERENCES fb_ingredienti(id),
    data_rilevazione DATE NOT NULL,
    tipo            TEXT NOT NULL,  -- apertura | chiusura
    quantita        NUMERIC(12,4) NOT NULL,
    valore          NUMERIC(12,2) NOT NULL,  -- quantita * costo_unitario
    rilevato_da     TEXT,
    note            TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- ─────────────────────────────────────────────────────────────────
--  TABELLA: fb_cost_report
--  Report periodici food & beverage cost (settimanale/mensile)
-- ─────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS fb_cost_report (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    hotel_id        UUID REFERENCES hotels(id) ON DELETE CASCADE,
    periodo_da      DATE NOT NULL,
    periodo_a       DATE NOT NULL,
    tipo_report     TEXT DEFAULT 'mensile',  -- settimanale | mensile | annuale
    -- Food Cost
    food_revenue        NUMERIC(14,2) DEFAULT 0,
    food_costo          NUMERIC(14,2) DEFAULT 0,
    food_cost_pct       NUMERIC(6,2) DEFAULT 0,
    food_cost_target    NUMERIC(6,2) DEFAULT 32.0,  -- benchmark 4★
    -- Beverage Cost
    bev_revenue         NUMERIC(14,2) DEFAULT 0,
    bev_costo           NUMERIC(14,2) DEFAULT 0,
    bev_cost_pct        NUMERIC(6,2) DEFAULT 0,
    bev_cost_target     NUMERIC(6,2) DEFAULT 22.0,  -- target cocktail bar
    -- Totali F&B
    fb_revenue_totale   NUMERIC(14,2) DEFAULT 0,
    fb_costo_totale     NUMERIC(14,2) DEFAULT 0,
    fb_cost_pct_totale  NUMERIC(6,2) DEFAULT 0,
    -- Gross Profit
    gross_profit        NUMERIC(14,2) DEFAULT 0,
    gross_profit_pct    NUMERIC(6,2) DEFAULT 0,
    -- Top 5 voci di costo
    top_costi           JSONB,
    -- Analisi AI
    analisi_ai          TEXT,
    suggerimenti_ai     TEXT,
    stato               TEXT DEFAULT 'bozza',  -- bozza | approvato | archiviato
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    updated_at          TIMESTAMPTZ DEFAULT NOW()
);

-- ─────────────────────────────────────────────────────────────────
--  ROW LEVEL SECURITY
-- ─────────────────────────────────────────────────────────────────
ALTER TABLE fb_ingredienti            ENABLE ROW LEVEL SECURITY;
ALTER TABLE fb_ricette                ENABLE ROW LEVEL SECURITY;
ALTER TABLE fb_ricette_ingredienti    ENABLE ROW LEVEL SECURITY;
ALTER TABLE fb_vendite                ENABLE ROW LEVEL SECURITY;
ALTER TABLE fb_inventario_snapshot    ENABLE ROW LEVEL SECURITY;
ALTER TABLE fb_cost_report            ENABLE ROW LEVEL SECURITY;

-- Trigger updated_at
CREATE TRIGGER trg_fb_ricette_updated
    BEFORE UPDATE ON fb_ricette
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER trg_fb_report_updated
    BEFORE UPDATE ON fb_cost_report
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- ─────────────────────────────────────────────────────────────────
--  FUNZIONE: ricalcola_costo_ricetta()
--  Trigger che aggiorna costo_ricetta e food_cost_pct automaticamente
-- ─────────────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION ricalcola_costo_ricetta()
RETURNS TRIGGER AS $$
DECLARE
    v_costo     NUMERIC;
    v_prezzo    NUMERIC;
    v_fc_pct    NUMERIC;
BEGIN
    -- Somma costo ingredienti per la ricetta coinvolta
    SELECT COALESCE(SUM(i.costo_unitario * ri.quantita), 0)
    INTO v_costo
    FROM fb_ricette_ingredienti ri
    JOIN fb_ingredienti i ON i.id = ri.ingrediente_id
    WHERE ri.ricetta_id = COALESCE(NEW.ricetta_id, OLD.ricetta_id);

    SELECT prezzo_vendita INTO v_prezzo
    FROM fb_ricette
    WHERE id = COALESCE(NEW.ricetta_id, OLD.ricetta_id);

    v_fc_pct := CASE WHEN v_prezzo > 0 THEN ROUND((v_costo / v_prezzo) * 100, 2) ELSE 0 END;

    UPDATE fb_ricette
    SET costo_ricetta  = v_costo,
        food_cost_pct  = v_fc_pct,
        updated_at     = NOW()
    WHERE id = COALESCE(NEW.ricetta_id, OLD.ricetta_id);

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_ricosta_costo
    AFTER INSERT OR UPDATE OR DELETE ON fb_ricette_ingredienti
    FOR EACH ROW EXECUTE FUNCTION ricalcola_costo_ricetta();

-- ─────────────────────────────────────────────────────────────────
--  DATI DI TEST (demo — rimuovi in produzione)
-- ─────────────────────────────────────────────────────────────────
DO $$
DECLARE v_hotel UUID;
BEGIN
    SELECT id INTO v_hotel FROM hotels WHERE nome = 'Hotel BAD.S Demo' LIMIT 1;
    IF v_hotel IS NULL THEN RETURN; END IF;

    -- Ingredienti demo
    INSERT INTO fb_ingredienti (hotel_id, nome, categoria, unita_misura, costo_unitario, allergeni) VALUES
        (v_hotel, 'Vodka premium', 'spirits', 'cl', 0.35, ARRAY[]::TEXT[]),
        (v_hotel, 'Succo limone', 'analcolici', 'cl', 0.05, ARRAY[]::TEXT[]),
        (v_hotel, 'Sciroppo zucchero', 'analcolici', 'cl', 0.03, ARRAY[]::TEXT[]),
        (v_hotel, 'Prosecco DOC', 'vini', 'cl', 0.18, ARRAY[]::TEXT[]),
        (v_hotel, 'Filetto manzo', 'carne', 'kg', 28.00, ARRAY[]::TEXT[]),
        (v_hotel, 'Parmigiano Reggiano DOP', 'latticini', 'kg', 18.50, ARRAY['latte']),
        (v_hotel, 'Gamberi rossi', 'pesce', 'kg', 35.00, ARRAY['crostacei']),
        (v_hotel, 'Pasta artigianale', 'secchi', 'kg', 3.20, ARRAY['glutine'])
    ON CONFLICT DO NOTHING;

    -- Ricetta demo: Vodka Lemon
    WITH r AS (
        INSERT INTO fb_ricette (hotel_id, nome, tipo, categoria, prezzo_vendita, iva_pct, bcg_popolarita)
        VALUES (v_hotel, 'Vodka Lemon', 'cocktail', 'long_drink', 9.00, 22.0, 'alta')
        RETURNING id
    )
    INSERT INTO fb_ricette_ingredienti (ricetta_id, ingrediente_id, quantita)
    SELECT r.id, i.id,
        CASE i.nome
            WHEN 'Vodka premium'       THEN 4    -- 4 cl
            WHEN 'Succo limone'        THEN 2    -- 2 cl
            WHEN 'Sciroppo zucchero'   THEN 1    -- 1 cl
        END
    FROM r, fb_ingredienti i
    WHERE i.hotel_id = v_hotel
      AND i.nome IN ('Vodka premium', 'Succo limone', 'Sciroppo zucchero');
END;
$$;

SELECT 'Modulo Food & Beverage Cost schema v1.0.0 creato! 🍸🍽️' AS risultato;
