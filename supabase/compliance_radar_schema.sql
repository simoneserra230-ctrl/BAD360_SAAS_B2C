-- BAD360.ai — Compliance Radar (niche C2). Multi-tenant hotel_id TEXT. Idempotente.
create table if not exists compliance_profile (
  hotel_id        text primary key,
  tipo_struttura  text default 'hotel',
  n_camere        int default 0,
  n_posti_letto   int default 0,
  regione         text,
  n_dipendenti    int default 0,
  cucina          boolean default false,
  piscina         boolean default false,
  updated_at      timestamptz default now()
);

create table if not exists compliance_status (
  id               uuid primary key default gen_random_uuid(),
  hotel_id         text not null,
  obbligo_key      text not null,
  fatto            boolean default false,
  data_adempimento date,
  data_scadenza    date,
  note             text,
  updated_at       timestamptz default now()
);
create index if not exists idx_compstat_hotel on compliance_status(hotel_id);
create unique index if not exists idx_compstat_hotel_key on compliance_status(hotel_id, obbligo_key);
