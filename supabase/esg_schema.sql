-- BAD360.ai — ESG / Sostenibilità CSRD (niche C). Multi-tenant hotel_id TEXT (nuova, non la legacy esg_reports UUID). Idempotente.
create table if not exists esg_indicatori (
  id         uuid primary key default gen_random_uuid(),
  hotel_id   text not null,
  periodo    text,
  categoria  text not null,   -- energia | acqua | rifiuti | emissioni | sociale | governance
  indicatore text not null,
  valore     numeric,
  unita      text,
  note       text,
  updated_at timestamptz default now()
);
create index if not exists idx_esg_hotel on esg_indicatori(hotel_id);
create index if not exists idx_esg_hotel_cat on esg_indicatori(hotel_id, categoria);
