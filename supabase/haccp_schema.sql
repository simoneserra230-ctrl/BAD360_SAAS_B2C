-- ═══════════════════════════════════════════════════════════════════
--  BAD360.ai — HACCP (persistenza reale, multi-tenant)
--  Esegui UNA VOLTA nel SQL editor di Supabase.
--  Modulo "fondamenta dati": registro temperature HACCP per hotel.
--
--  NOTA: hotel_id è TEXT (non UUID) per compatibilità con gli account demo
--  (es. 'hotel-ss-001') e con eventuali id Supabase. Ogni riga è isolata per
--  hotel_id — il backend lo prende SEMPRE dal token (mai dal client).
-- ═══════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS haccp_temperature (
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

-- Index per le query frequenti (storico per hotel, alert del giorno)
CREATE INDEX IF NOT EXISTS idx_haccp_temp_hotel_ts
    ON haccp_temperature (hotel_id, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_haccp_temp_alert
    ON haccp_temperature (hotel_id, alert) WHERE alert = TRUE;
CREATE INDEX IF NOT EXISTS idx_haccp_temp_zona
    ON haccp_temperature (hotel_id, zona, timestamp DESC);

-- (Opzionale) Row Level Security: con la service key del backend è bypassata,
-- ma la lasciamo pronta se in futuro si userà l'accesso diretto da client.
-- ALTER TABLE haccp_temperature ENABLE ROW LEVEL SECURITY;
