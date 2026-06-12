CREATE TABLE scm_rischi (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    hotel_id        UUID REFERENCES hotels(id) ON DELETE CASCADE,
    categoria       TEXT NOT NULL,  -- fornitore | logistica | qualita | prezzi | recall
    fornitore_id    UUID REFERENCES fornitori(id),
    descrizione     TEXT NOT NULL,
    probabilita     INTEGER CHECK (probabilita BETWEEN 1 AND 5),
    impatto         INTEGER CHECK (impatto BETWEEN 1 AND 5),
    score           INTEGER GENERATED ALWAYS AS (probabilita * impatto) STORED,
    livello         TEXT,           -- basso | medio | alto | critico
    misure          TEXT,
    responsabile    TEXT,
    stato           TEXT DEFAULT 'aperto',  -- aperto | mitigato | chiuso
    scadenza        DATE,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);