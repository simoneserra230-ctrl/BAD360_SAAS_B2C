-- BAD360.ai — Restaurant Intelligence (niche E). Multi-tenant hotel_id TEXT. Idempotente.
create table if not exists rest_coperti (
  id uuid primary key default gen_random_uuid(), hotel_id text not null, data date,
  coperti_previsti int default 0, coperti_effettivi int default 0, no_show int default 0,
  incasso numeric default 0, note text, updated_at timestamptz default now());
create index if not exists idx_restcop_hotel on rest_coperti(hotel_id);

create table if not exists rest_sprechi (
  id uuid primary key default gen_random_uuid(), hotel_id text not null, data date,
  categoria text default 'cucina', quantita_kg numeric default 0, valore numeric default 0,
  causa text, note text, created_at timestamptz default now());
create index if not exists idx_restspr_hotel on rest_sprechi(hotel_id);
