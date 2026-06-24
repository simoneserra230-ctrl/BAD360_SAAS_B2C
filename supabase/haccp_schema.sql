-- ═══════════════════════════════════════════════════════════════════
--  BAD360.ai — HACCP (persistenza reale, multi-tenant)
--  Esegui UNA VOLTA nel SQL editor di Supabase.
--  Modulo "fondamenta dati": registro temperature HACCP per hotel.
--
--  NOTA: usa la tabella NUOVA `haccp_letture` con hotel_id TEXT (compatibile
--  con gli account demo tipo 'hotel-ss-001' e con eventuali id Supabase).
--  Volutamente NON riusa la vecchia `haccp_temperature` (hotel_id UUID, legacy
--  dello schema iniziale) per non doverla alterare. Ogni riga è isolata per
--  hotel_id — il backend lo prende SEMPRE dal token, mai dal client.
-- ═══════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS haccp_letture (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    hotel_id        TEXT NOT NULL,
    sensor_id       TEXT NOT NULL DEFAULT 'b360-ui',
    zona            TEXT NOT NULL,           -- cella_frigo | cella_surgelati | frigo_bar | zona_calda | cantina | abbattitore
    temperatura     NUMERIC(6,2) NOT NULL,
    temp_min_norm   NUMERIC(6,2),
    temp_max_norm   NUMERIC(6,2),
    alert           BOOLEAN DEFAULT FALSE,
    severity        TEXT DEFAULT 'ok',       -- ok | warning | critical
    messaggio       TEXT,
    conforme_reg    BOOLEAN DEFAULT TRUE,
    rilevato_da     TEXT DEFAULT 'manuale',  -- manuale | iot
    timestamp       TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_haccp_letture_hotel_ts
    ON haccp_letture (hotel_id, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_haccp_letture_alert
    ON haccp_letture (hotel_id, alert) WHERE alert = TRUE;
CREATE INDEX IF NOT EXISTS idx_haccp_letture_zona
    ON haccp_letture (hotel_id, zona, timestamp DESC);
