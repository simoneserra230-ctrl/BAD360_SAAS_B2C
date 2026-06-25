-- ═══════════════════════════════════════════════════════════════════
--  BAD360.ai — Housekeeping (persistenza reale, multi-tenant)
--  Esegui UNA VOLTA su Supabase (o già applicato via MCP).
--  Tabelle NUOVE hk_camere / hk_forniture / hk_task (hotel_id TEXT) —
--  NON riusano le legacy hk_rooms/hk_tasks/hk_supplies (hotel_id UUID).
--  Ogni riga è isolata per hotel_id — il backend lo prende SEMPRE dal token.
-- ═══════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS hk_camere (
    id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    hotel_id           TEXT NOT NULL,
    numero             TEXT NOT NULL,
    piano              INTEGER DEFAULT 1,
    tipo               TEXT DEFAULT 'Standard',
    stato_hk           TEXT DEFAULT 'pulita',     -- da_pulire|in_pulizia|pulita|ispezionata|fuori_servizio
    stato_occupazione  TEXT DEFAULT 'libera',     -- libera|occupata|in_partenza|bloccata
    priorita           INTEGER DEFAULT 2,
    note               TEXT DEFAULT '',
    created_at         TIMESTAMPTZ DEFAULT NOW(),
    updated_at         TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS hk_forniture (
    id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    hotel_id           TEXT NOT NULL,
    nome               TEXT NOT NULL,
    categoria          TEXT DEFAULT '',
    giacenza_attuale   NUMERIC(12,2) DEFAULT 0,
    par_level          NUMERIC(12,2) DEFAULT 0,
    punto_riordino     NUMERIC(12,2) DEFAULT 0,
    created_at         TIMESTAMPTZ DEFAULT NOW(),
    updated_at         TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS hk_task (
    id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    hotel_id           TEXT NOT NULL,
    camera             TEXT NOT NULL,
    tipo               TEXT DEFAULT 'partenza',   -- partenza|stayover|deep_clean|ispezione
    stato              TEXT DEFAULT 'assegnato',  -- assegnato|in_corso|completato|nc
    priorita           INTEGER DEFAULT 2,
    durata_stimata     INTEGER DEFAULT 30,
    data               DATE DEFAULT CURRENT_DATE,
    note               TEXT DEFAULT '',
    created_at         TIMESTAMPTZ DEFAULT NOW(),
    updated_at         TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_hk_camere_hotel    ON hk_camere   (hotel_id, piano, numero);
CREATE INDEX IF NOT EXISTS idx_hk_forniture_hotel ON hk_forniture(hotel_id, categoria, nome);
CREATE INDEX IF NOT EXISTS idx_hk_task_hotel_data ON hk_task     (hotel_id, data);
