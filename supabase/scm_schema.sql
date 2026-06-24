-- ═══════════════════════════════════════════════════════════════════
--  BAD360.ai — SCM Pro: Fornitori & Ordini (persistenza reale, multi-tenant)
--  Esegui UNA VOLTA su Supabase (o già applicato via MCP).
--  Tabelle NUOVE scm_fornitori / scm_ordini (hotel_id TEXT) — non riusano le
--  legacy `fornitori`/`ordini_fornitori` (hotel_id UUID).
--  Ogni riga è isolata per hotel_id — il backend lo prende SEMPRE dal token.
-- ═══════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS scm_fornitori (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    hotel_id    TEXT NOT NULL,
    nome        TEXT NOT NULL,
    cat         TEXT DEFAULT '',
    cert        TEXT DEFAULT '',
    contatto    TEXT DEFAULT '',
    sla         INTEGER DEFAULT 85,
    spend       NUMERIC(12,2) DEFAULT 0,
    stato       TEXT DEFAULT 'ok',
    icon        TEXT DEFAULT '🏭',
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    updated_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS scm_ordini (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    hotel_id    TEXT NOT NULL,
    num         TEXT NOT NULL,
    forn        TEXT DEFAULT '',
    cat         TEXT DEFAULT 'Misto',
    data        DATE,
    cons        DATE,
    importo     NUMERIC(12,2) DEFAULT 0,
    prod        TEXT DEFAULT '',
    stato       TEXT DEFAULT 'aperto',    -- aperto | transit | ok
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    updated_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_scm_fornitori_hotel ON scm_fornitori (hotel_id, nome);
CREATE INDEX IF NOT EXISTS idx_scm_ordini_hotel_data ON scm_ordini (hotel_id, data DESC);
