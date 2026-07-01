-- BAD360.ai — Adempimenti ricettivi CIN/Alloggiati/Imposta soggiorno (niche C3). hotel_id TEXT. Idempotente.
create table if not exists cin_config (
  hotel_id            text primary key,
  cin_code            text,
  cir_code            text,
  comune              text,
  tariffa_soggiorno   numeric default 0,   -- €/persona/notte
  max_notti_tassabili int default 0,       -- 0 = nessun tetto
  note                text,
  updated_at          timestamptz default now()
);

create table if not exists alloggiati_log (
  id                 uuid primary key default gen_random_uuid(),
  hotel_id           text not null,
  data_arrivo        date,
  ospite_nome        text not null,
  n_ospiti           int default 1,
  n_notti            int default 1,
  esente             boolean default false,
  inviato_alloggiati boolean default false,
  note               text,
  created_at         timestamptz default now()
);
create index if not exists idx_allog_hotel on alloggiati_log(hotel_id);
