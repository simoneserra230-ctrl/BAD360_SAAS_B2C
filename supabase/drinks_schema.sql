-- ═══════════════════════════════════════════════════════════════════
--  BAD360.ai — Drink Cost / Ricette (persistenza reale, multi-tenant)
--  Esegui UNA VOLTA nel SQL editor di Supabase.
--  Il drink cost calculator ora SALVA le ricette (prima erano demo).
--  costo e costpct sono calcolati lato server.
--
--  hotel_id è TEXT (compatibile con i demo id tipo 'hotel-ss-001').
--  Ogni riga è isolata per hotel_id — il backend lo prende SEMPRE dal token.
-- ═══════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS drink_recipes (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    hotel_id     TEXT NOT NULL,
    nome         TEXT NOT NULL,
    prezzo       NUMERIC(10,2) DEFAULT 0,
    costo        NUMERIC(10,2) DEFAULT 0,
    costpct      NUMERIC(6,1) DEFAULT 0,
    ingredienti  JSONB DEFAULT '[]'::jsonb,   -- [{ing,qty,unit,cost}, ...]
    note         TEXT,
    created_at   TIMESTAMPTZ DEFAULT NOW(),
    updated_at   TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_drink_recipes_hotel ON drink_recipes (hotel_id, nome);
