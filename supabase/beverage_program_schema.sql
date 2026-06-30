-- BAD360.ai — AI Beverage Program (niche B). Multi-tenant hotel_id TEXT. Idempotente.
create table if not exists beverage_items (
  id         uuid primary key default gen_random_uuid(),
  hotel_id   text not null,
  nome       text not null,
  tipo       text default 'cocktail',   -- cocktail | vino | birra | spirito | analcolico
  categoria  text,
  prezzo     numeric default 0,
  costo      numeric default 0,
  venduti    int default 0,
  attivo     boolean default true,
  updated_at timestamptz default now()
);
create index if not exists idx_bev_hotel on beverage_items(hotel_id);
