-- ═══════════════════════════════════════════════════════════════════
--  BAD360.ai — Schema Non Conformità (NC)  ·  multi-tenant (hotel_id TEXT)
--  Modulo qualità 8D: apertura → contenimento → analisi → CAPA → verifica → chiusura.
--  hotel_id arriva SEMPRE dal token (vedi backend/non_conformita.py): TEXT, es. 'hotel-ss-001'.
--  Idempotente: CREATE TABLE IF NOT EXISTS.
-- ═══════════════════════════════════════════════════════════════════

create table if not exists non_conformita (
  id              uuid primary key default gen_random_uuid(),
  hotel_id        text not null,
  numero_nc       text,
  area            text not null,
  gravita         text not null default 'media',   -- critica | alta | media | bassa
  titolo          text not null,
  descrizione     text,
  evidenza_url    text,
  -- riferimenti opzionali alle sorgenti (TEXT, nessun vincolo FK rigido)
  haccp_temp_id   text,
  lotto_id        text,
  fornitore_id    text,
  ordine_id       text,
  stato           text not null default 'aperta',  -- aperta|in_contenimento|in_analisi|in_corso|in_verifica|chiusa|annullata
  -- contenimento (D3)
  azione_immediata        text,
  contenimento_operatore  text,
  contenimento_at         timestamptz,
  -- analisi causa radice (D4)
  metodo_analisi  text,
  causa_radice    text,
  analisi_ai      text,
  analisi_at      timestamptz,
  -- piano azione correttiva (D5-D6)
  azione_correttiva text,
  responsabile_ac   text,
  scadenza_ac       date,
  ac_avviata_at     timestamptz,
  -- verifica efficacia (D7)
  verifica_descrizione text,
  verifica_efficace    boolean,
  verifica_operatore   text,
  verifica_at          timestamptz,
  -- chiusura (D8)
  lezione_appresa  text,
  chiusa_da        text,
  chiusa_at        timestamptz,
  note_annullamento text,
  ricorrente       boolean default false,
  rilevato_da      text,
  rilevato_at      timestamptz default now()
);
create index if not exists idx_nc_hotel        on non_conformita(hotel_id);
create index if not exists idx_nc_hotel_stato  on non_conformita(hotel_id, stato);
create index if not exists idx_nc_hotel_grav   on non_conformita(hotel_id, gravita);

-- Log transizioni di stato (audit trail)
create table if not exists nc_log (
  id        uuid primary key default gen_random_uuid(),
  nc_id     uuid references non_conformita(id) on delete cascade,
  hotel_id  text not null,
  stato_da  text,
  stato_a   text,
  azione    text,
  operatore text,
  ts        timestamptz default now()
);
create index if not exists idx_nclog_nc on nc_log(nc_id);

-- Analisi 5-Why
create table if not exists nc_azioni_5why (
  id        uuid primary key default gen_random_uuid(),
  nc_id     uuid references non_conformita(id) on delete cascade,
  hotel_id  text not null,
  livello   int,
  domanda   text,
  risposta  text
);
create index if not exists idx_nc5why_nc on nc_azioni_5why(nc_id);
