-- BAD360.ai — STR / Case Vacanza (niche D). Multi-tenant hotel_id TEXT (=account gestore). Idempotente.
create table if not exists str_unita (
  id uuid primary key default gen_random_uuid(), hotel_id text not null, nome text not null,
  indirizzo text, capienza int default 2, note text, attivo boolean default true,
  updated_at timestamptz default now());
create index if not exists idx_strun_hotel on str_unita(hotel_id);

create table if not exists str_prenotazioni (
  id uuid primary key default gen_random_uuid(), hotel_id text not null, unita_id uuid, unita_nome text,
  ospite_nome text not null, canale text default 'diretto', check_in date, check_out date,
  n_ospiti int default 1, importo numeric default 0, stato text default 'confermata',
  verificato boolean default false, pulizia_fatta boolean default false, note text,
  created_at timestamptz default now());
create index if not exists idx_strpren_hotel on str_prenotazioni(hotel_id);
create index if not exists idx_strpren_hotel_stato on str_prenotazioni(hotel_id, stato);
