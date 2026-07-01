-- BAD360.ai — Sistema di Gestione Integrato ISO (QM-ISO). Multi-tenant hotel_id TEXT. Idempotente.
create table if not exists sgi_config (
  hotel_id    text primary key,
  norme       text default '9001',   -- csv: 9001,14001,45001,37001,haccp
  updated_at  timestamptz default now()
);

create table if not exists sgi_stato (
  id              uuid primary key default gen_random_uuid(),
  hotel_id        text not null,
  processo_codice text not null,
  stato           text default 'da_avviare',  -- da_avviare | in_corso | attivo | da_riesaminare
  responsabile    text,
  note            text,
  updated_at      timestamptz default now()
);
create index if not exists idx_sgi_stato_hotel on sgi_stato(hotel_id);
create unique index if not exists idx_sgi_stato_hotel_proc on sgi_stato(hotel_id, processo_codice);
