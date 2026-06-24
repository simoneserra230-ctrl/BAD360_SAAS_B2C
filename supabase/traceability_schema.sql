-- ═══════════════════════════════════════════════════════════════════
--  BAD360.ai — Tracciabilità lotti ISO 22005 (persistenza reale, multi-tenant)
--  Esegui UNA VOLTA su Supabase (o già applicato via MCP).
--  Tabella NUOVA trace_lotti (hotel_id TEXT) — non riusa la legacy `lotti`
--  (schema ISO22005 diverso, hotel_id UUID).
--  Ogni riga è isolata per hotel_id — il backend lo prende SEMPRE dal token.
-- ═══════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS trace_lotti (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    hotel_id    TEXT NOT NULL,
    codice      TEXT NOT NULL,
    prodotto    TEXT DEFAULT '',
    fornitore   TEXT DEFAULT '',
    carico      DATE,
    scad        DATE,
    qty         TEXT DEFAULT '',
    origine     TEXT DEFAULT '',
    stato       TEXT DEFAULT 'ok',     -- ok | warn | nc
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    updated_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_trace_lotti_hotel ON trace_lotti (hotel_id, codice);
CREATE INDEX IF NOT EXISTS idx_trace_lotti_hotel_carico ON trace_lotti (hotel_id, carico DESC);
