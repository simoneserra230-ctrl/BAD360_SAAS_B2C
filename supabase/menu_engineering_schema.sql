-- BAD360.ai — Menu Engineering (food): ricette costate multi-tenant.
-- hotel_id TEXT (compatibile coi demo id tipo 'hotel-ss-001'). Il backend filtra
-- SEMPRE per user.hotel_id dal token (prima era condiviso tra tutti = falla).

CREATE TABLE IF NOT EXISTS me_recipes (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    hotel_id       TEXT NOT NULL,
    name           TEXT NOT NULL,
    category       TEXT DEFAULT 'primi',
    ingredients    JSONB DEFAULT '[]'::jsonb,   -- [{n,qty,unit,cost}]
    selling_price  NUMERIC(10,2) DEFAULT 0,
    monthly_sales  INTEGER DEFAULT 0,
    allergens      JSONB DEFAULT '[]'::jsonb,   -- sottoinsieme dei 14 allergeni UE 1169/2011
    created_at     TIMESTAMPTZ DEFAULT NOW()
);

-- caso tabella legacy già esistente senza hotel_id: aggiungi la colonna
ALTER TABLE me_recipes ADD COLUMN IF NOT EXISTS hotel_id TEXT;

CREATE INDEX IF NOT EXISTS idx_me_recipes_hotel ON me_recipes(hotel_id, category);
