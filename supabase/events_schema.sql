-- ═══════════════════════════════════════════════════════════════════
--  BAD360.ai — Events / CRM eventi (persistenza reale, multi-tenant)
--  Esegui UNA VOLTA nel SQL editor di Supabase.
--  La pipeline CRM eventi (lead → preventivo → follow-up → chiuso) persiste.
--  Ponte ecosistema: gli eventi (BAD) alimenteranno lo staffing (Barman Match).
--
--  hotel_id è TEXT (compatibile con i demo id tipo 'hotel-ss-001').
--  Ogni riga è isolata per hotel_id — il backend lo prende SEMPRE dal token.
-- ═══════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS eventi (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    hotel_id    TEXT NOT NULL,
    nome        TEXT NOT NULL,
    tipo        TEXT DEFAULT '',
    data        DATE,
    pax         INTEGER DEFAULT 0,
    budget      NUMERIC(12,2) DEFAULT 0,
    stato       TEXT DEFAULT 'lead',     -- lead | preventivo | followup | chiuso
    follow_up   DATE,
    note        TEXT,
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    updated_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_eventi_hotel_data ON eventi (hotel_id, data);
CREATE INDEX IF NOT EXISTS idx_eventi_hotel_stato ON eventi (hotel_id, stato);
