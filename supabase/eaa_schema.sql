-- BAD360.ai — Accessibilità EAA (niche C4). hotel_id TEXT. Idempotente.
create table if not exists eaa_checklist (
  id           uuid primary key default gen_random_uuid(),
  hotel_id     text not null,
  criterio_key text not null,
  stato        text default 'da_verificare',  -- ok | no | na | da_verificare
  note         text,
  updated_at   timestamptz default now()
);
create index if not exists idx_eaa_hotel on eaa_checklist(hotel_id);
create unique index if not exists idx_eaa_hotel_crit on eaa_checklist(hotel_id, criterio_key);
