-- ═══════════════════════════════════════════════════════════════════
--  BAD360.ai — Recensioni / Reputation (persistenza reale, multi-tenant)
--  Esegui UNA VOLTA nel SQL editor di Supabase (o già applicato via MCP).
--  Le recensioni e le risposte persistono per hotel.
--
--  hotel_id è TEXT (compatibile con i demo id tipo 'hotel-ss-001').
--  Ogni riga è isolata per hotel_id — il backend lo prende SEMPRE dal token.
-- ═══════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS recensioni (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    hotel_id    TEXT NOT NULL,
    platform    TEXT DEFAULT 'google',   -- google | tripadvisor | thefork | booking
    author      TEXT DEFAULT '',
    stars       INTEGER DEFAULT 5,
    date        DATE,
    text        TEXT DEFAULT '',
    sentiment   TEXT DEFAULT 'neu',      -- pos | neu | neg
    keywords    JSONB DEFAULT '[]'::jsonb,
    replied     BOOLEAN DEFAULT FALSE,
    reply       TEXT DEFAULT '',
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    updated_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_recensioni_hotel_date ON recensioni (hotel_id, date DESC);
CREATE INDEX IF NOT EXISTS idx_recensioni_hotel_plat ON recensioni (hotel_id, platform);
