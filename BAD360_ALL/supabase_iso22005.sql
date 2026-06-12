-- ═══════════════════════════════════════════════════════════════════
--  BAD.S Unified Platform — Modulo Tracciabilità ISO 22005
--  Esegui DOPO supabase_setup.sql e supabase_fb_cost.sql
--  Norma: ISO 22005:2007 — Traceability in the feed and food chain
--  Versione: 1.0.0 | 2026
-- ═══════════════════════════════════════════════════════════════════

-- ─────────────────────────────────────────────────────────────────
--  TABELLA: lotti
--  Registro centralizzato di ogni lotto ricevuto da fornitore
--  Punto di ingresso della catena di tracciabilità (§ 5.3 ISO 22005)
-- ─────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS lotti (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    hotel_id            UUID REFERENCES hotels(id) ON DELETE CASCADE,

    -- Identificazione lotto
    codice_lotto        TEXT NOT NULL,           -- es. "LOT-2026-03-0041"
    codice_lotto_forn   TEXT,                    -- codice lotto del fornitore
    barcode             TEXT,                    -- EAN/GS1 se disponibile

    -- Collegamento supply chain
    fornitore_id        UUID REFERENCES fornitori(id),
    ingrediente_id      UUID REFERENCES fb_ingredienti(id),  -- ingrediente corrispondente
    ordine_id           UUID REFERENCES ordini_fornitori(id),

    -- Dati prodotto
    descrizione         TEXT NOT NULL,
    categoria           TEXT,                    -- carne | pesce | latticini | verdure | secchi | bevande
    quantita_ricevuta   NUMERIC(12,3) NOT NULL,
    unita_misura        TEXT DEFAULT 'kg',
    quantita_residua    NUMERIC(12,3),           -- aggiornata dai movimenti

    -- Date critiche (FEFO — First Expired First Out)
    data_produzione     DATE,
    data_consegna       DATE NOT NULL DEFAULT CURRENT_DATE,
    data_scadenza       DATE,
    data_tmc            DATE,                    -- Termine Minima Conservazione (TMC)

    -- Condizioni ricevimento (CCP ricezione merce)
    temp_ricezione      NUMERIC(6,2),            -- °C al momento del ricevimento
    temp_conforme       BOOLEAN DEFAULT TRUE,
    ddt_numero          TEXT,                    -- Documento Di Trasporto
    ddt_data            DATE,
    conforme_ricezione  BOOLEAN DEFAULT TRUE,
    note_ricezione      TEXT,

    -- Stato lotto
    stato               TEXT DEFAULT 'attivo'    -- attivo | esaurito | ritirato | bloccato | scaduto
        CHECK (stato IN ('attivo','esaurito','ritirato','bloccato','scaduto')),
    posizione_magazzino TEXT,                    -- es. "cella_A | shelf_B3"
    metodo_rotazione    TEXT DEFAULT 'FEFO'      -- FEFO | FIFO
        CHECK (metodo_rotazione IN ('FEFO','FIFO')),

    -- Audit trail
    operatore           TEXT,
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    updated_at          TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(hotel_id, codice_lotto)
);

CREATE INDEX IF NOT EXISTS idx_lotti_hotel        ON lotti(hotel_id, stato);
CREATE INDEX IF NOT EXISTS idx_lotti_ingrediente  ON lotti(ingrediente_id);
CREATE INDEX IF NOT EXISTS idx_lotti_fornitore    ON lotti(fornitore_id);
CREATE INDEX IF NOT EXISTS idx_lotti_scadenza     ON lotti(data_scadenza) WHERE stato = 'attivo';

-- ─────────────────────────────────────────────────────────────────
--  TABELLA: lotti_movimenti
--  Ogni utilizzo/scarico di un lotto — cuore della tracciabilità
--  Permette di ricostruire DOVE è finito ogni grammo (§ 5.4 ISO 22005)
-- ─────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS lotti_movimenti (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    lotto_id        UUID REFERENCES lotti(id) ON DELETE CASCADE,
    hotel_id        UUID REFERENCES hotels(id) ON DELETE CASCADE,

    -- Tipo movimento
    tipo            TEXT NOT NULL
        CHECK (tipo IN (
            'carico',       -- ricezione merce
            'scarico',      -- utilizzo in cucina
            'trasferimento',-- spostamento tra reparti/magazzini
            'reso',         -- reso al fornitore
            'scarto',       -- scarto/eliminazione
            'campione',     -- prelievo campione per analisi
            'inventario'    -- rettifica inventario
        )),

    -- Quantità
    quantita        NUMERIC(12,3) NOT NULL,
    unita_misura    TEXT DEFAULT 'kg',
    segno           SMALLINT DEFAULT -1         -- +1 carico | -1 scarico

        CHECK (segno IN (1, -1)),

    -- Destinazione (per tracciabilità a valle)
    ricetta_id      UUID REFERENCES fb_ricette(id),    -- se usato in una ricetta
    vendita_id      UUID REFERENCES fb_vendite(id),    -- se collegato a una vendita
    reparto_dest    TEXT,                               -- cucina | bar | room_service | banqueting

    -- Dati operatore e turno
    operatore       TEXT,
    turno           TEXT,                              -- colazione | pranzo | cena
    note            TEXT,
    timestamp       TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_movimenti_lotto   ON lotti_movimenti(lotto_id, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_movimenti_ricetta ON lotti_movimenti(ricetta_id);

-- ─────────────────────────────────────────────────────────────────
--  TABELLA: ricette_lotti
--  Collega ogni produzione/batch di ricetta ai lotti usati
--  Abilita tracciabilità a monte: "Questa ricetta usa il lotto X"
-- ─────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS ricette_lotti (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    hotel_id        UUID REFERENCES hotels(id) ON DELETE CASCADE,
    ricetta_id      UUID REFERENCES fb_ricette(id),
    lotto_id        UUID REFERENCES lotti(id),
    ingrediente_id  UUID REFERENCES fb_ingredienti(id),
    quantita_usata  NUMERIC(12,4) NOT NULL,
    unita_misura    TEXT DEFAULT 'kg',
    data_produzione TIMESTAMPTZ DEFAULT NOW(),
    n_porzioni      INTEGER DEFAULT 1,          -- quante porzioni prodotte
    turno           TEXT,
    operatore       TEXT,
    note            TEXT
);

CREATE INDEX IF NOT EXISTS idx_ric_lotti_ricetta ON ricette_lotti(ricetta_id);
CREATE INDEX IF NOT EXISTS idx_ric_lotti_lotto   ON ricette_lotti(lotto_id);

-- ─────────────────────────────────────────────────────────────────
--  TABELLA: ritiri_lotti
--  Gestione ritiri/recall (§ 7 ISO 22005 + Reg. CE 178/2002 art. 19)
--  Procedura obbligatoria: identificare e bloccare in < 24h
-- ─────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS ritiri_lotti (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    hotel_id        UUID REFERENCES hotels(id) ON DELETE CASCADE,

    -- Identificazione ritiro
    numero_ritiro   TEXT UNIQUE,                -- es. "RECALL-2026-001"
    tipo            TEXT DEFAULT 'ritiro'       -- ritiro | richiamo | precauzionale
        CHECK (tipo IN ('ritiro','richiamo','precauzionale')),

    -- Lotti coinvolti (può essere multiplo)
    lotti_ids       UUID[],                     -- array di lotto IDs
    motivo          TEXT NOT NULL,              -- contaminazione | errore etichetta | allerta RASFF...
    descrizione     TEXT,
    gravita         TEXT DEFAULT 'media'
        CHECK (gravita IN ('bassa','media','alta','critica')),

    -- Azioni intraprese
    quantita_ritirata   NUMERIC(12,3),
    quantita_smaltita   NUMERIC(12,3),
    quantita_resa_forn  NUMERIC(12,3),
    azioni_correttive   TEXT,
    comunicazione_asf   BOOLEAN DEFAULT FALSE,  -- Comunicato all'ASL/ASF?
    data_comunicazione  DATE,
    numero_pratica_asl  TEXT,

    -- Efficacia del ritiro
    pct_recuperato      NUMERIC(5,2),          -- % lotto recuperato rispetto a distribuito
    verifica_efficacia  TEXT,

    -- Stato
    stato           TEXT DEFAULT 'aperto'
        CHECK (stato IN ('aperto','in_corso','chiuso','archiviato')),
    responsabile    TEXT,
    data_apertura   DATE DEFAULT CURRENT_DATE,
    data_chiusura   DATE,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

-- ─────────────────────────────────────────────────────────────────
--  TABELLA: nc_tracciabilita
--  Non Conformità legate a lotti specifici (collegato a HACCP)
-- ─────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS nc_tracciabilita (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    hotel_id        UUID REFERENCES hotels(id) ON DELETE CASCADE,
    lotto_id        UUID REFERENCES lotti(id),
    tipo_nc         TEXT,                      -- temp_fuori_range | scaduto | contaminazione | etichetta
    descrizione     TEXT NOT NULL,
    gravita         TEXT DEFAULT 'media'
        CHECK (gravita IN ('bassa','media','alta','critica')),
    azione          TEXT,                      -- scarto | reso | blocco | analisi_lab
    risolta         BOOLEAN DEFAULT FALSE,
    responsabile    TEXT,
    data_nc         TIMESTAMPTZ DEFAULT NOW(),
    data_risoluzione TIMESTAMPTZ
);

-- ─────────────────────────────────────────────────────────────────
--  AGGIORNAMENTI TABELLE ESISTENTI (ALTER)
--  Aggiunge colonne ISO 22005 alle tabelle già presenti
-- ─────────────────────────────────────────────────────────────────

-- Aggiungi riferimento lotto alle righe ordine (già ha campo lotto TEXT)
ALTER TABLE ordini_righe
    ADD COLUMN IF NOT EXISTS lotto_id UUID REFERENCES lotti(id);

-- Aggiungi lotto all'inventario (già ha lotto_attivo TEXT)
ALTER TABLE inventario
    ADD COLUMN IF NOT EXISTS lotto_id UUID REFERENCES lotti(id);

-- Aggiungi lotti usati alla vendita (per tracciabilità completa)
ALTER TABLE fb_vendite
    ADD COLUMN IF NOT EXISTS lotti_usati UUID[];

-- ─────────────────────────────────────────────────────────────────
--  VIEW: v_tracciabilita_lotto
--  Vista unificata per query di rintracciabilità a monte (backward)
--  "Dato il lotto X, da quale fornitore viene e cosa contiene?"
-- ─────────────────────────────────────────────────────────────────
CREATE OR REPLACE VIEW v_tracciabilita_lotto AS
SELECT
    l.id                        AS lotto_id,
    l.codice_lotto,
    l.codice_lotto_forn,
    l.descrizione               AS prodotto,
    l.categoria,
    l.data_consegna,
    l.data_scadenza,
    l.stato                     AS stato_lotto,
    l.quantita_ricevuta,
    l.quantita_residua,
    l.temp_ricezione,
    l.conforme_ricezione,
    -- Fornitore
    f.ragione_sociale           AS fornitore,
    f.piva                      AS fornitore_piva,
    f.cert_iso22005             AS fornitore_cert_iso22005,
    f.cert_iso22000             AS fornitore_cert_iso22000,
    -- Ingrediente collegato
    fi.nome                     AS ingrediente,
    fi.allergeni,
    -- Ordine
    o.numero_ordine,
    o.data_ordine,
    -- Hotel
    h.nome                      AS hotel
FROM lotti l
LEFT JOIN fornitori   f  ON f.id  = l.fornitore_id
LEFT JOIN fb_ingredienti fi ON fi.id = l.ingrediente_id
LEFT JOIN ordini_fornitori o ON o.id = l.ordine_id
LEFT JOIN hotels      h  ON h.id  = l.hotel_id;

-- ─────────────────────────────────────────────────────────────────
--  VIEW: v_tracciabilita_ricette
--  Vista per tracciabilità a valle (forward)
--  "Il lotto X è stato usato in quali ricette/vendite?"
-- ─────────────────────────────────────────────────────────────────
CREATE OR REPLACE VIEW v_tracciabilita_ricette AS
SELECT
    l.codice_lotto,
    l.descrizione               AS prodotto_lotto,
    l.stato                     AS stato_lotto,
    r.nome                      AS ricetta,
    r.tipo                      AS tipo_ricetta,
    rl.quantita_usata,
    rl.data_produzione,
    rl.n_porzioni,
    rl.operatore,
    rl.turno,
    f.ragione_sociale           AS fornitore_origine
FROM ricette_lotti rl
JOIN lotti           l  ON l.id  = rl.lotto_id
JOIN fb_ricette      r  ON r.id  = rl.ricetta_id
LEFT JOIN fornitori  f  ON f.id  = l.fornitore_id;

-- ─────────────────────────────────────────────────────────────────
--  FUNZIONE: fn_traccia_lotto_completo(codice TEXT)
--  Restituisce l'intera catena a monte + a valle per un lotto
--  Usata dall'endpoint /api/tracciabilita/lotto/{codice}
-- ─────────────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION fn_traccia_lotto_completo(p_codice TEXT)
RETURNS JSON AS $$
DECLARE
    v_lotto    lotti%ROWTYPE;
    v_result   JSON;
BEGIN
    SELECT * INTO v_lotto FROM lotti WHERE codice_lotto = p_codice LIMIT 1;

    IF NOT FOUND THEN
        RETURN json_build_object('errore', 'Lotto non trovato: ' || p_codice);
    END IF;

    SELECT json_build_object(
        'lotto',        row_to_json(v_lotto),
        'fornitore',    (SELECT row_to_json(f) FROM fornitori f WHERE f.id = v_lotto.fornitore_id),
        'ingrediente',  (SELECT row_to_json(fi) FROM fb_ingredienti fi WHERE fi.id = v_lotto.ingrediente_id),
        'movimenti',    (SELECT json_agg(m ORDER BY m.timestamp) FROM lotti_movimenti m WHERE m.lotto_id = v_lotto.id),
        'ricette',      (SELECT json_agg(rl) FROM ricette_lotti rl WHERE rl.lotto_id = v_lotto.id),
        'nc',           (SELECT json_agg(nc) FROM nc_tracciabilita nc WHERE nc.lotto_id = v_lotto.id)
    ) INTO v_result;

    RETURN v_result;
END;
$$ LANGUAGE plpgsql;

-- ─────────────────────────────────────────────────────────────────
--  FUNZIONE: fn_lotti_in_scadenza(giorni INT, hotel UUID)
--  Allerta lotti in scadenza entro N giorni
-- ─────────────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION fn_lotti_in_scadenza(p_giorni INT, p_hotel_id UUID)
RETURNS TABLE (
    codice_lotto    TEXT,
    descrizione     TEXT,
    data_scadenza   DATE,
    giorni_rimasti  INT,
    quantita_residua NUMERIC,
    posizione       TEXT,
    fornitore       TEXT
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        l.codice_lotto,
        l.descrizione,
        l.data_scadenza,
        (l.data_scadenza - CURRENT_DATE)::INT AS giorni_rimasti,
        l.quantita_residua,
        l.posizione_magazzino,
        f.ragione_sociale
    FROM lotti l
    LEFT JOIN fornitori f ON f.id = l.fornitore_id
    WHERE l.hotel_id = p_hotel_id
      AND l.stato = 'attivo'
      AND l.data_scadenza IS NOT NULL
      AND l.data_scadenza <= CURRENT_DATE + p_giorni
    ORDER BY l.data_scadenza ASC;
END;
$$ LANGUAGE plpgsql;

-- ─────────────────────────────────────────────────────────────────
--  TRIGGER: aggiorna quantita_residua lotto dopo ogni movimento
-- ─────────────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION trg_aggiorna_residuo_lotto()
RETURNS TRIGGER AS $$
BEGIN
    UPDATE lotti
    SET quantita_residua = quantita_residua + (NEW.segno * NEW.quantita),
        stato = CASE
            WHEN quantita_residua + (NEW.segno * NEW.quantita) <= 0 THEN 'esaurito'
            ELSE stato
        END,
        updated_at = NOW()
    WHERE id = NEW.lotto_id;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_movimenti_residuo
    AFTER INSERT ON lotti_movimenti
    FOR EACH ROW EXECUTE FUNCTION trg_aggiorna_residuo_lotto();

-- ─────────────────────────────────────────────────────────────────
--  TRIGGER: blocca utilizzo lotti scaduti o ritirati
-- ─────────────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION trg_blocca_lotto_non_valido()
RETURNS TRIGGER AS $$
DECLARE
    v_stato TEXT;
    v_scad  DATE;
BEGIN
    SELECT stato, data_scadenza INTO v_stato, v_scad
    FROM lotti WHERE id = NEW.lotto_id;

    IF v_stato IN ('ritirato','bloccato','scaduto') THEN
        RAISE EXCEPTION 'Lotto % non utilizzabile: stato = %', NEW.lotto_id, v_stato;
    END IF;

    IF v_scad IS NOT NULL AND v_scad < CURRENT_DATE AND NEW.tipo = 'scarico' THEN
        RAISE EXCEPTION 'Lotto % scaduto in data %', NEW.lotto_id, v_scad;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_blocca_lotto
    BEFORE INSERT ON lotti_movimenti
    FOR EACH ROW EXECUTE FUNCTION trg_blocca_lotto_non_valido();

-- ─────────────────────────────────────────────────────────────────
--  RLS — Row Level Security
-- ─────────────────────────────────────────────────────────────────
ALTER TABLE lotti               ENABLE ROW LEVEL SECURITY;
ALTER TABLE lotti_movimenti     ENABLE ROW LEVEL SECURITY;
ALTER TABLE ricette_lotti       ENABLE ROW LEVEL SECURITY;
ALTER TABLE ritiri_lotti        ENABLE ROW LEVEL SECURITY;
ALTER TABLE nc_tracciabilita    ENABLE ROW LEVEL SECURITY;

-- ─────────────────────────────────────────────────────────────────
--  DATI DI TEST (commenta in produzione)
-- ─────────────────────────────────────────────────────────────────
DO $$
DECLARE
    v_hotel_id  UUID;
    v_forn_id   UUID;
    v_ingr_id   UUID;
    v_lotto_id  UUID;
BEGIN
    SELECT id INTO v_hotel_id FROM hotels WHERE nome = 'Hotel BAD.S Demo' LIMIT 1;
    SELECT id INTO v_forn_id  FROM fornitori WHERE hotel_id = v_hotel_id LIMIT 1;
    SELECT id INTO v_ingr_id  FROM fb_ingredienti WHERE hotel_id = v_hotel_id LIMIT 1;

    IF v_hotel_id IS NOT NULL THEN
        INSERT INTO lotti (hotel_id, codice_lotto, codice_lotto_forn, descrizione,
                           categoria, quantita_ricevuta, quantita_residua, unita_misura,
                           fornitore_id, ingrediente_id, data_consegna, data_scadenza,
                           temp_ricezione, conforme_ricezione, ddt_numero, operatore)
        VALUES
            (v_hotel_id, 'LOT-2026-03-0001', 'FRN-88821', 'Salmone Atlantico fresco',
             'pesce', 15.0, 15.0, 'kg',
             v_forn_id, v_ingr_id, CURRENT_DATE, CURRENT_DATE + 3,
             2.5, TRUE, 'DDT-20260330-001', 'Chef Marco')
        ON CONFLICT DO NOTHING
        RETURNING id INTO v_lotto_id;

        IF v_lotto_id IS NOT NULL THEN
            INSERT INTO lotti_movimenti (lotto_id, hotel_id, tipo, quantita, segno, operatore, turno)
            VALUES (v_lotto_id, v_hotel_id, 'carico', 15.0, 1, 'Chef Marco', 'mattina');
        END IF;
    END IF;
END $$;

SELECT 'ISO 22005 Tracciabilità — Schema v1.0.0 installato ✓' AS risultato;
