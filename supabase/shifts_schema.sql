-- ═══════════════════════════════════════════════════════════════════
--  BAD360.ai — Turni & Staff (persistenza reale, multi-tenant)
--  Esegui UNA VOLTA nel SQL editor di Supabase.
--  shiftmanager.html prima era 100% demo: ora anagrafica + turni persistono.
--
--  hotel_id è TEXT (compatibile con i demo id tipo 'hotel-ss-001').
--  Ogni riga è isolata per hotel_id — il backend lo prende SEMPRE dal token.
-- ═══════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS staff (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    hotel_id    TEXT NOT NULL,
    nome        TEXT NOT NULL,
    ruolo       TEXT DEFAULT '',
    reparto     TEXT DEFAULT '',
    ore_sett    NUMERIC(5,1) DEFAULT 40,
    attivo      BOOLEAN DEFAULT TRUE,
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    updated_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS turni (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    hotel_id    TEXT NOT NULL,
    dipendente  TEXT NOT NULL,
    ruolo       TEXT DEFAULT '',
    data        DATE NOT NULL,
    turno       TEXT DEFAULT '',
    ore         TEXT DEFAULT '8h',
    reparto     TEXT DEFAULT '',
    stato       TEXT DEFAULT 'ok',     -- ok | riposo | warn
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    updated_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_staff_hotel ON staff (hotel_id, nome);
CREATE INDEX IF NOT EXISTS idx_turni_hotel_data ON turni (hotel_id, data DESC);
