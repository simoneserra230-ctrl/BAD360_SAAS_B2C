-- BAD360.ai — Certificazioni (multi-tenant, hotel_id TEXT).
-- Tre aree: attestati personale / licenze locale / certificazioni aziendali ISO-EMAS.
-- La multi-tenancy e' garantita dal backend (hotel_id SEMPRE dal token, service-role).
-- Lo stato (ok/in_scadenza/scaduto/permanente) e' CALCOLATO a runtime dalla data_scadenza.

-- 1) Attestati del PERSONALE (HACCP, antincendio, primo soccorso, 81/08, allergeni, ...)
CREATE TABLE IF NOT EXISTS cert_personale (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    hotel_id       TEXT NOT NULL,
    dipendente     TEXT NOT NULL,
    ruolo          TEXT,
    tipo           TEXT NOT NULL,        -- HACCP | Allergeni | Sicurezza 81/08 | Antincendio | Primo Soccorso | Preposto | ...
    ente           TEXT,
    data_rilascio  DATE,
    data_scadenza  DATE,
    file_url       TEXT,
    note           TEXT,
    created_at     TIMESTAMPTZ DEFAULT NOW(),
    updated_at     TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_cert_personale_hotel ON cert_personale(hotel_id, dipendente);
CREATE INDEX IF NOT EXISTS idx_cert_personale_scad  ON cert_personale(hotel_id, data_scadenza);

-- 2) Licenze / autorizzazioni del LOCALE (SCIA, autorizzazione sanitaria, somministrazione, ...)
CREATE TABLE IF NOT EXISTS cert_licenze (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    hotel_id       TEXT NOT NULL,
    tipo           TEXT NOT NULL,        -- SCIA | Autorizzazione sanitaria | Licenza somministrazione | Registrazione ASL | ...
    numero         TEXT,
    ente           TEXT,
    data_rilascio  DATE,
    data_scadenza  DATE,                 -- NULL = permanente
    file_url       TEXT,
    note           TEXT,
    created_at     TIMESTAMPTZ DEFAULT NOW(),
    updated_at     TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_cert_licenze_hotel ON cert_licenze(hotel_id, data_scadenza);

-- 3) Certificazioni AZIENDALI ISO / EMAS
CREATE TABLE IF NOT EXISTS cert_aziendali (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    hotel_id              TEXT NOT NULL,
    norma                 TEXT NOT NULL,  -- ISO 22000:2018 | ISO 9001:2015 | EMAS / ISO 14001 | ...
    ente_certificatore    TEXT,
    data_rilascio         DATE,
    data_scadenza         DATE,
    prossima_sorveglianza DATE,
    file_url              TEXT,
    note                  TEXT,
    created_at            TIMESTAMPTZ DEFAULT NOW(),
    updated_at            TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_cert_aziendali_hotel ON cert_aziendali(hotel_id, data_scadenza);
