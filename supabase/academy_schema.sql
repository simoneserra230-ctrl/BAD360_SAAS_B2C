-- BAD360.ai — Academy (LMS interno) multi-tenant. hotel_id TEXT, dal token.
-- academy_corsi = catalogo; academy_iscrizioni = progressi del personale.

CREATE TABLE IF NOT EXISTS academy_corsi (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    hotel_id     TEXT NOT NULL,
    titolo       TEXT NOT NULL,
    categoria    TEXT,
    livello      TEXT DEFAULT 'base',      -- base | intermedio | avanzato
    durata_ore   NUMERIC(6,2) DEFAULT 1,
    tags         JSONB DEFAULT '[]'::jsonb,
    descrizione  TEXT,
    link         TEXT,                     -- contenuto / SSFormazione
    attivo       BOOLEAN DEFAULT TRUE,
    created_at   TIMESTAMPTZ DEFAULT NOW(),
    updated_at   TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_academy_corsi_hotel ON academy_corsi(hotel_id, categoria);

CREATE TABLE IF NOT EXISTS academy_iscrizioni (
    id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    hotel_id           TEXT NOT NULL,
    corso_id           UUID NOT NULL,
    dipendente         TEXT NOT NULL,
    stato              TEXT DEFAULT 'non_iniziato',  -- non_iniziato | in_corso | completato
    progresso          INTEGER DEFAULT 0,            -- 0-100
    data_completamento DATE,
    created_at         TIMESTAMPTZ DEFAULT NOW(),
    updated_at         TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_academy_isc_hotel ON academy_iscrizioni(hotel_id, corso_id);
