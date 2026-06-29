-- BAD360.ai — Quality Manager / multi-cliente.
-- Link consulente (qm_uid = email/id del QM) <-> struttura cliente (hotel_id).
-- SICUREZZA: il grant lo crea la STRUTTURA con hotel_id dal token (può autorizzare
-- solo i propri dati). Il QM vede le strutture dove qm_uid = la sua email.

CREATE TABLE IF NOT EXISTS qm_portfolio (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    qm_uid        TEXT NOT NULL,        -- email/id del Quality Manager autorizzato
    hotel_id      TEXT NOT NULL,        -- struttura che concede (dal token del granter)
    cliente_nome  TEXT,                 -- etichetta del cliente per il QM
    granted_by    TEXT,                 -- chi ha concesso (id utente struttura)
    created_at    TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_qm_portfolio_qm    ON qm_portfolio(qm_uid);
CREATE INDEX IF NOT EXISTS idx_qm_portfolio_hotel ON qm_portfolio(hotel_id);
CREATE UNIQUE INDEX IF NOT EXISTS uq_qm_portfolio ON qm_portfolio(qm_uid, hotel_id);
