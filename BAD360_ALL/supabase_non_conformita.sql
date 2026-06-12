-- ═══════════════════════════════════════════════════════════════════
--  BAD.S Unified Platform — Modulo Non Conformità (NC)
--  Esegui DOPO supabase_setup.sql
--  Normativa: ISO 9001:2015 § 10.2 | ISO 22000:2018 § 10.1 | Reg. CE 852/2004
--  Versione: 1.0.0 | 2026
-- ═══════════════════════════════════════════════════════════════════

-- ─────────────────────────────────────────────────────────────────
--  ENUM-LIKE CHECK CONSTRAINTS (Postgres puro, no tipi custom)
--  area:    da dove proviene la NC
--  gravita: SLA di risposta
--  stato:   macchina a stati del ciclo di vita
-- ─────────────────────────────────────────────────────────────────

-- ─────────────────────────────────────────────────────────────────
--  TABELLA: non_conformita
--  Registro master di tutte le NC — ogni area alimenta questa tabella
-- ─────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS non_conformita (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    hotel_id        UUID REFERENCES hotels(id) ON DELETE CASCADE,

    -- Identificazione
    numero_nc       TEXT UNIQUE,            -- NC-2026-03-0041 (generato automaticamente)
    area            TEXT NOT NULL
        CHECK (area IN (
            'haccp',            -- temperatura/CCP fuori range
            'tracciabilita',    -- lotto scaduto, non conforme, ritirato
            'fornitore',        -- qualità fornitura, DDT errato, mancata cert.
            'housekeeping',     -- camera difettosa, pulizia, biancheria
            'fb_cost',          -- food cost fuori soglia, spreco, porzione errata
            'audit_interno',    -- rilievo da audit qualità interno
            'cliente',          -- reclamo ospite
            'manutenzione',     -- attrezzatura guasta, CCP non funzionante
            'altro'
        )),

    gravita         TEXT NOT NULL DEFAULT 'media'
        CHECK (gravita IN ('bassa','media','alta','critica')),
    -- SLA risposta: critica=4h | alta=24h | media=72h | bassa=7gg

    stato           TEXT NOT NULL DEFAULT 'aperta'
        CHECK (stato IN (
            'aperta',           -- appena registrata
            'in_contenimento',  -- azione immediata avviata
            'in_analisi',       -- causa radice in analisi
            'in_corso',         -- piano azione correttiva assegnato
            'in_verifica',      -- azione eseguita, verifica efficacia pendente
            'chiusa',           -- efficace e documentata
            'annullata'         -- falso positivo
        )),

    -- Descrizione del problema (8D: D1-D2)
    titolo          TEXT NOT NULL,
    descrizione     TEXT NOT NULL,
    evidenza_url    TEXT,                   -- foto/allegato (es. URL Supabase Storage)

    -- Collegamento alle entità sorgente (FK opzionali)
    haccp_temp_id   UUID REFERENCES haccp_temperature(id),
    lotto_id        UUID REFERENCES lotti(id),          -- se tabella lotti esiste
    fornitore_id    UUID REFERENCES fornitori(id),
    ordine_id       UUID REFERENCES ordini_fornitori(id),

    -- Contenimento immediato (8D: D3)
    azione_immediata        TEXT,           -- es. "lotto isolato in quarantena"
    contenimento_at         TIMESTAMPTZ,
    contenimento_operatore  TEXT,

    -- Causa radice (8D: D4)
    metodo_analisi  TEXT DEFAULT '5why'     -- 5why | ishikawa | fta | ai
        CHECK (metodo_analisi IN ('5why','ishikawa','fta','ai','altro')),
    causa_radice    TEXT,
    analisi_ai      TEXT,                   -- output analisi AI (Claude)
    analisi_at      TIMESTAMPTZ,

    -- Piano azione correttiva (8D: D5-D6)
    azione_correttiva   TEXT,
    responsabile_ac     TEXT,
    scadenza_ac         DATE,
    ac_avviata_at       TIMESTAMPTZ,

    -- Verifica efficacia (8D: D7)
    verifica_descrizione    TEXT,
    verifica_efficace       BOOLEAN,
    verifica_at             TIMESTAMPTZ,
    verifica_operatore      TEXT,

    -- Chiusura (8D: D8)
    lezione_appresa     TEXT,               -- knowledge base per prevenzione
    chiusa_at           TIMESTAMPTZ,
    chiusa_da           TEXT,

    -- Ricorrenza (per KPI)
    nc_correlata_id UUID REFERENCES non_conformita(id),  -- se è ricorrenza di NC precedente
    ricorrente      BOOLEAN DEFAULT FALSE,

    -- Meta
    rilevato_da     TEXT,                   -- operatore che ha aperto la NC
    rilevato_at     TIMESTAMPTZ DEFAULT NOW(),
    notifica_inviata BOOLEAN DEFAULT FALSE,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_nc_hotel_stato   ON non_conformita(hotel_id, stato);
CREATE INDEX IF NOT EXISTS idx_nc_hotel_area    ON non_conformita(hotel_id, area);
CREATE INDEX IF NOT EXISTS idx_nc_gravita       ON non_conformita(hotel_id, gravita) WHERE stato != 'chiusa';
CREATE INDEX IF NOT EXISTS idx_nc_scadenza      ON non_conformita(scadenza_ac) WHERE stato IN ('in_corso','in_verifica');

-- ─────────────────────────────────────────────────────────────────
--  TABELLA: nc_log
--  Audit trail di ogni cambio di stato (immutabile)
--  Obbligatorio ISO 9001 § 10.2.2 — "evidenza documentata"
-- ─────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS nc_log (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    nc_id       UUID REFERENCES non_conformita(id) ON DELETE CASCADE,
    stato_da    TEXT,
    stato_a     TEXT NOT NULL,
    azione      TEXT NOT NULL,          -- descrizione operazione
    operatore   TEXT,
    note        TEXT,
    ts          TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_nc_log_nc ON nc_log(nc_id, ts DESC);

-- ─────────────────────────────────────────────────────────────────
--  TABELLA: nc_azioni_5why
--  5 livelli di Why per l'analisi causa radice
-- ─────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS nc_azioni_5why (
    id      UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    nc_id   UUID REFERENCES non_conformita(id) ON DELETE CASCADE,
    livello SMALLINT NOT NULL CHECK (livello BETWEEN 1 AND 5),
    domanda TEXT NOT NULL,   -- "Perché …?"
    risposta TEXT,
    ts      TIMESTAMPTZ DEFAULT NOW()
);

-- ─────────────────────────────────────────────────────────────────
--  TRIGGER: genera numero_nc sequenziale e aggiorna updated_at
-- ─────────────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION trg_genera_numero_nc()
RETURNS TRIGGER AS $$
DECLARE
    v_count INTEGER;
BEGIN
    SELECT COUNT(*) + 1 INTO v_count
    FROM non_conformita
    WHERE hotel_id = NEW.hotel_id
      AND EXTRACT(YEAR FROM created_at) = EXTRACT(YEAR FROM NOW());

    NEW.numero_nc := 'NC-' || TO_CHAR(NOW(), 'YYYY-MM') || '-' || LPAD(v_count::TEXT, 4, '0');
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_nc_numero
    BEFORE INSERT ON non_conformita
    FOR EACH ROW WHEN (NEW.numero_nc IS NULL)
    EXECUTE FUNCTION trg_genera_numero_nc();

CREATE TRIGGER trg_nc_updated
    BEFORE UPDATE ON non_conformita
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- ─────────────────────────────────────────────────────────────────
--  TRIGGER: blocca transizioni di stato non ammesse
--  Macchina a stati: evita salti illegali
-- ─────────────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION trg_nc_stato_valido()
RETURNS TRIGGER AS $$
DECLARE
    TRANSIZIONI CONSTANT JSONB := '{
        "aperta":          ["in_contenimento","in_analisi","annullata"],
        "in_contenimento": ["in_analisi","annullata"],
        "in_analisi":      ["in_corso","annullata"],
        "in_corso":        ["in_verifica","in_analisi"],
        "in_verifica":     ["chiusa","in_corso"],
        "chiusa":          [],
        "annullata":       []
    }';
BEGIN
    IF OLD.stato = NEW.stato THEN RETURN NEW; END IF;

    IF NOT (TRANSIZIONI -> OLD.stato) @> to_jsonb(NEW.stato) THEN
        RAISE EXCEPTION 'Transizione NC non valida: % → %', OLD.stato, NEW.stato;
    END IF;

    -- Log automatico cambio stato
    INSERT INTO nc_log(nc_id, stato_da, stato_a, azione, operatore)
    VALUES (NEW.id, OLD.stato, NEW.stato,
            'Cambio stato automatico', NEW.rilevato_da);

    -- Aggiorna timestamp di fase
    CASE NEW.stato
        WHEN 'in_contenimento' THEN NEW.contenimento_at := COALESCE(NEW.contenimento_at, NOW());
        WHEN 'in_analisi'      THEN NEW.analisi_at      := COALESCE(NEW.analisi_at, NOW());
        WHEN 'in_corso'        THEN NEW.ac_avviata_at   := COALESCE(NEW.ac_avviata_at, NOW());
        WHEN 'chiusa'          THEN NEW.chiusa_at        := COALESCE(NEW.chiusa_at, NOW());
        ELSE NULL;
    END CASE;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_nc_stato
    BEFORE UPDATE OF stato ON non_conformita
    FOR EACH ROW EXECUTE FUNCTION trg_nc_stato_valido();

-- ─────────────────────────────────────────────────────────────────
--  TRIGGER: quando HACCP lancia un alert critico → apre NC automatica
-- ─────────────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION trg_haccp_to_nc()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.alert = TRUE AND NEW.severity IN ('critical','warning') THEN
        INSERT INTO non_conformita (
            hotel_id, area, gravita, stato, titolo, descrizione,
            haccp_temp_id, azione_immediata, rilevato_da
        )
        VALUES (
            NEW.hotel_id,
            'haccp',
            CASE WHEN NEW.severity = 'critical' THEN 'critica' ELSE 'alta' END,
            'aperta',
            'Temperatura fuori range — ' || REPLACE(NEW.zona, '_', ' '),
            FORMAT('Zona: %s | Temp: %s°C | Range: %s°C–%s°C | Sensor: %s',
                   NEW.zona, NEW.temperatura, NEW.temp_min_norm,
                   NEW.temp_max_norm, NEW.sensor_id),
            NEW.id,
            'Verificare immediatamente zona ' || NEW.zona,
            'sistema_iot'
        )
        ON CONFLICT DO NOTHING;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_haccp_nc
    AFTER INSERT ON haccp_temperature
    FOR EACH ROW EXECUTE FUNCTION trg_haccp_to_nc();

-- ─────────────────────────────────────────────────────────────────
--  VIEW: v_nc_dashboard
--  Vista per KPI dashboard — una riga per NC con aging e SLA
-- ─────────────────────────────────────────────────────────────────
CREATE OR REPLACE VIEW v_nc_dashboard AS
SELECT
    nc.id,
    nc.numero_nc,
    nc.area,
    nc.gravita,
    nc.stato,
    nc.titolo,
    nc.rilevato_at,
    nc.scadenza_ac,
    nc.ricorrente,
    -- Aging in ore dall'apertura
    EXTRACT(EPOCH FROM (NOW() - nc.rilevato_at)) / 3600 AS aging_ore,
    -- SLA in ore per gravità
    CASE nc.gravita
        WHEN 'critica' THEN 4
        WHEN 'alta'    THEN 24
        WHEN 'media'   THEN 72
        WHEN 'bassa'   THEN 168  -- 7 giorni
    END AS sla_ore,
    -- Stato SLA
    CASE
        WHEN nc.stato IN ('chiusa','annullata') THEN 'rispettato'
        WHEN EXTRACT(EPOCH FROM (NOW() - nc.rilevato_at)) / 3600 >
             CASE nc.gravita WHEN 'critica' THEN 4 WHEN 'alta' THEN 24
                             WHEN 'media' THEN 72 ELSE 168 END
        THEN 'scaduto'
        WHEN EXTRACT(EPOCH FROM (NOW() - nc.rilevato_at)) / 3600 >
             CASE nc.gravita WHEN 'critica' THEN 3 WHEN 'alta' THEN 20
                             WHEN 'media' THEN 60 ELSE 140 END
        THEN 'in_scadenza'
        ELSE 'ok'
    END AS stato_sla,
    h.nome AS hotel,
    nc.responsabile_ac
FROM non_conformita nc
JOIN hotels h ON h.id = nc.hotel_id;

-- ─────────────────────────────────────────────────────────────────
--  VIEW: v_nc_kpi_mensili
--  KPI aggregati per mese (per trend e report ESG/qualità)
-- ─────────────────────────────────────────────────────────────────
CREATE OR REPLACE VIEW v_nc_kpi_mensili AS
SELECT
    hotel_id,
    DATE_TRUNC('month', rilevato_at)    AS mese,
    area,
    COUNT(*)                             AS totale_nc,
    COUNT(*) FILTER (WHERE gravita = 'critica') AS n_critiche,
    COUNT(*) FILTER (WHERE stato = 'chiusa')    AS n_chiuse,
    COUNT(*) FILTER (WHERE ricorrente = TRUE)   AS n_ricorrenti,
    ROUND(AVG(
        EXTRACT(EPOCH FROM (COALESCE(chiusa_at, NOW()) - rilevato_at)) / 3600
    )::NUMERIC, 1)                       AS tempo_medio_chiusura_ore,
    ROUND(
        COUNT(*) FILTER (WHERE stato = 'chiusa')::NUMERIC / NULLIF(COUNT(*),0) * 100, 1
    )                                    AS tasso_chiusura_pct
FROM non_conformita
GROUP BY hotel_id, DATE_TRUNC('month', rilevato_at), area;

-- ─────────────────────────────────────────────────────────────────
--  RLS
-- ─────────────────────────────────────────────────────────────────
ALTER TABLE non_conformita  ENABLE ROW LEVEL SECURITY;
ALTER TABLE nc_log          ENABLE ROW LEVEL SECURITY;
ALTER TABLE nc_azioni_5why  ENABLE ROW LEVEL SECURITY;

-- ─────────────────────────────────────────────────────────────────
--  DATI DI TEST
-- ─────────────────────────────────────────────────────────────────
DO $$
DECLARE v_hotel UUID;
BEGIN
    SELECT id INTO v_hotel FROM hotels WHERE nome = 'Hotel BAD.S Demo' LIMIT 1;
    IF v_hotel IS NOT NULL THEN
        INSERT INTO non_conformita
            (hotel_id, area, gravita, stato, titolo, descrizione, rilevato_da)
        VALUES
            (v_hotel, 'haccp', 'critica', 'in_contenimento',
             'Cella frigo +8°C (limite +4°C)',
             'Sensor CELL-01 ha rilevato 8.2°C per 45 minuti. Prodotti a rischio: salmone lotto LOT-2026-03-0001.',
             'sistema_iot'),
            (v_hotel, 'fornitore', 'media', 'aperta',
             'DDT mancante su consegna pesce fresco',
             'Fornitore Ittica Sarda non ha allegato DDT alla consegna del 30/03/2026.',
             'Chef Marco'),
            (v_hotel, 'housekeeping', 'bassa', 'chiusa',
             'Camera 214 — macchia su moquette non rimossa',
             'Ospite segnala macchia residua dopo pulizia. Governante intervenuta con prodotto specifico.',
             'Reception')
        ON CONFLICT DO NOTHING;
    END IF;
END $$;

SELECT 'Modulo NC — Schema v1.0.0 installato ✓' AS risultato;
