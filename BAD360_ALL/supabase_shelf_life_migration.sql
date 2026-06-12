-- ═══════════════════════════════════════════════════════════════════
--  BAD.S Platform — Migration: Shelf Life Tracker & FEFO Alerts
--  Eseguire su Supabase SQL Editor
--  Compatibile con: supabase_setup.sql (tabella inventario già esistente)
-- ═══════════════════════════════════════════════════════════════════

-- ───────────────────────────────────────────────────────────────────
--  1. AUDIT LOG — expiry_alert_log
--     Storico giornaliero degli alert scadenze generati dall'APScheduler.
--     Utile per: report compliance HACCP, trend sprechi, audit fornitori.
-- ───────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS expiry_alert_log (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    hotel_id            UUID NOT NULL REFERENCES hotels(id) ON DELETE CASCADE,
    inventario_id       UUID REFERENCES inventario(id) ON DELETE SET NULL,
    articolo            TEXT NOT NULL,
    lotto_attivo        TEXT,
    scadenza_lotto      DATE NOT NULL,
    giorni_alla_scadenza INTEGER NOT NULL,           -- negativo = già scaduto
    urgenza             TEXT NOT NULL                -- SCADUTO | CRITICO | ALTO | ATTENZIONE
                        CHECK (urgenza IN ('SCADUTO','CRITICO','ALTO','ATTENZIONE')),
    giacenza_attuale    NUMERIC(12,3),
    unita_misura        TEXT,
    azione_consigliata  TEXT,
    data_controllo      DATE NOT NULL DEFAULT CURRENT_DATE,
    created_at          TIMESTAMPTZ DEFAULT NOW()
);

-- Indice per query frequenti (storico per hotel, ultimi N giorni)
CREATE INDEX IF NOT EXISTS idx_expiry_log_hotel_data
    ON expiry_alert_log (hotel_id, data_controllo DESC);

-- Indice per analisi scaduti (waste tracking)
CREATE INDEX IF NOT EXISTS idx_expiry_log_urgenza
    ON expiry_alert_log (urgenza, data_controllo DESC);

-- Unico per giorno × articolo (evita duplicati se il job gira 2 volte)
CREATE UNIQUE INDEX IF NOT EXISTS idx_expiry_log_dedup
    ON expiry_alert_log (hotel_id, inventario_id, data_controllo)
    WHERE inventario_id IS NOT NULL;


-- ───────────────────────────────────────────────────────────────────
--  2. COLONNE AGGIUNTIVE su `inventario` (opzionali, retrocompatibili)
--     Se non presenti nel setup iniziale, aggiungile qui.
-- ───────────────────────────────────────────────────────────────────

-- Data di ricevimento lotto (per FIFO basato su data ingresso, non solo scadenza)
ALTER TABLE inventario
    ADD COLUMN IF NOT EXISTS data_ricezione_lotto DATE;

-- Flag manuale "lotto bloccato" (es. richiamo fornitore, NC HACCP)
ALTER TABLE inventario
    ADD COLUMN IF NOT EXISTS lotto_bloccato BOOLEAN DEFAULT FALSE;

-- Temperatura conservazione prescritta (verifica conformità catena freddo)
ALTER TABLE inventario
    ADD COLUMN IF NOT EXISTS temp_conservazione_min NUMERIC(4,1),  -- °C
    ADD COLUMN IF NOT EXISTS temp_conservazione_max NUMERIC(4,1);  -- °C

-- Commento colonne per documentazione Supabase
COMMENT ON COLUMN inventario.scadenza_lotto IS
    'Data scadenza lotto attivo (TMC o scadenza). Obbligatoria per FEFO.';
COMMENT ON COLUMN inventario.metodo_rotazione IS
    'FIFO = primo entrato primo uscito | FEFO = prima scadenza prima uscita';
COMMENT ON COLUMN inventario.lotto_attivo IS
    'Numero lotto DDT fornitore — obbligatorio per tracciabilità D.Lgs 231/2017';
COMMENT ON COLUMN inventario.lotto_bloccato IS
    'TRUE se il lotto è bloccato per NC/richiamo — nasconde da picking automatico';


-- ───────────────────────────────────────────────────────────────────
--  3. VISTA — v_expiry_dashboard
--     Vista pronta per la dashboard frontend con tutti i campi necessari.
-- ───────────────────────────────────────────────────────────────────
CREATE OR REPLACE VIEW v_expiry_dashboard AS
SELECT
    i.id,
    i.hotel_id,
    h.nome                                          AS hotel_nome,
    i.articolo,
    i.categoria,
    i.lotto_attivo,
    i.scadenza_lotto,
    (i.scadenza_lotto - CURRENT_DATE)::INTEGER      AS giorni_alla_scadenza,
    CASE
        WHEN i.scadenza_lotto < CURRENT_DATE        THEN 'SCADUTO'
        WHEN i.scadenza_lotto <= CURRENT_DATE + 3   THEN 'CRITICO'
        WHEN i.scadenza_lotto <= CURRENT_DATE + 7   THEN 'ALTO'
        WHEN i.scadenza_lotto <= CURRENT_DATE + 14  THEN 'ATTENZIONE'
        ELSE 'OK'
    END                                             AS urgenza,
    i.giacenza_attuale,
    i.unita_misura,
    i.metodo_rotazione,
    i.posizione,
    i.lotto_bloccato,
    i.ultimo_aggiornamento
FROM inventario i
LEFT JOIN hotels h ON h.id = i.hotel_id
WHERE i.scadenza_lotto IS NOT NULL
  AND (i.lotto_bloccato IS FALSE OR i.lotto_bloccato IS NULL)
ORDER BY i.scadenza_lotto ASC;


-- ───────────────────────────────────────────────────────────────────
--  4. ROW LEVEL SECURITY su expiry_alert_log
-- ───────────────────────────────────────────────────────────────────
ALTER TABLE expiry_alert_log ENABLE ROW LEVEL SECURITY;

-- Il service_role ha accesso pieno (usato dal backend APScheduler)
CREATE POLICY "service_role_full_access" ON expiry_alert_log
    FOR ALL USING (auth.role() = 'service_role');

-- Gli utenti autenticati vedono solo i log del proprio hotel
CREATE POLICY "hotel_user_read" ON expiry_alert_log
    FOR SELECT USING (
        hotel_id IN (
            SELECT hotel_id FROM hotel_users
            WHERE user_id = auth.uid() AND stato = 'attivo'
        )
    );


-- ───────────────────────────────────────────────────────────────────
--  5. DATI DI TEST (opzionale — commentare in produzione)
-- ───────────────────────────────────────────────────────────────────
-- INSERT INTO inventario (hotel_id, articolo, categoria, giacenza_attuale,
--     unita_misura, lotto_attivo, scadenza_lotto, metodo_rotazione, punto_riordino)
-- SELECT
--     (SELECT id FROM hotels LIMIT 1),
--     unnest(ARRAY['Salmone Affumicato','Mozzarella Bufala','Surgelati Verdure']),
--     unnest(ARRAY['pesce','latticini','surgelati']),
--     unnest(ARRAY[3.5, 8.0, 5.0]),
--     unnest(ARRAY['kg','kg','kg']),
--     unnest(ARRAY['LOT-A1','LOT-B3','LOT-D9']),
--     unnest(ARRAY[
--         CURRENT_DATE + 2,
--         CURRENT_DATE + 5,
--         CURRENT_DATE - 1   -- scaduto!
--     ]),
--     unnest(ARRAY['FEFO','FEFO','FEFO']),
--     unnest(ARRAY[5, 10, 8]);
