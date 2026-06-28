-- BAD360.ai — Hotellerie F&B: Carta Vini multi-tenant (hotel_id TEXT).
-- Il backend filtra SEMPRE per user.hotel_id dal token. Beverage cost calcolato a runtime.

CREATE TABLE IF NOT EXISTS ht_vini (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    hotel_id   TEXT NOT NULL,
    nome       TEXT NOT NULL,
    prod       TEXT,                 -- produttore
    reg        TEXT,                 -- regione
    tipo       TEXT DEFAULT 'Rosso', -- Rosso | Bianco | Spumante | ...
    annata     TEXT,                 -- anno o 'NV'
    costo      NUMERIC(10,2) DEFAULT 0,  -- costo acquisto bottiglia
    calice     NUMERIC(10,2) DEFAULT 0,  -- prezzo al calice
    bott       NUMERIC(10,2) DEFAULT 0,  -- prezzo bottiglia in carta
    score      INTEGER DEFAULT 0,
    giacenza   INTEGER DEFAULT 0,
    descr      TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_ht_vini_hotel ON ht_vini(hotel_id, reg, nome);
