-- ═══════════════════════════════════════════════════════════════════
--  BAD360.ai — Shelf Life / Inventario (persistenza reale, multi-tenant)
--  Esegui UNA VOLTA nel SQL editor di Supabase.
--  Aggiunge il WRITE PATH mancante: l'utente inserisce il suo inventario
--  con lotto + scadenza e lo ritrova. FEFO calcolato lato backend.
--
--  hotel_id è TEXT (compatibile con gli account demo tipo 'hotel-ss-001').
--  Ogni riga è isolata per hotel_id — il backend lo prende SEMPRE dal token.
-- ═══════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS shelf_life_items (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    hotel_id         TEXT NOT NULL,
    articolo         TEXT NOT NULL,
    categoria        TEXT DEFAULT '',
    lotto            TEXT DEFAULT '',
    giacenza_attuale NUMERIC(10,2) DEFAULT 0,
    unita_misura     TEXT DEFAULT 'kg',
    data_scadenza    DATE,
    fornitore        TEXT DEFAULT '',
    lotto_bloccato   BOOLEAN DEFAULT FALSE,
    note             TEXT,
    created_at       TIMESTAMPTZ DEFAULT NOW(),
    updated_at       TIMESTAMPTZ DEFAULT NOW()
);

-- Index per FEFO (per hotel, ordinato per scadenza) e per categoria
CREATE INDEX IF NOT EXISTS idx_shelf_items_hotel_scad
    ON shelf_life_items (hotel_id, data_scadenza ASC);
CREATE INDEX IF NOT EXISTS idx_shelf_items_hotel_cat
    ON shelf_life_items (hotel_id, categoria);
