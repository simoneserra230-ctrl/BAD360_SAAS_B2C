-- BAD360.ai — Event/Wedding Coordinator (niche A). Multi-tenant hotel_id TEXT. Idempotente.
create table if not exists eventi_pro (
  id         uuid primary key default gen_random_uuid(),
  hotel_id   text not null,
  nome       text not null,
  tipo       text default 'matrimonio',   -- matrimonio | aziendale | privato | gala
  data       date,
  n_invitati int default 0,
  budget     numeric default 0,
  location   text,
  stato      text default 'lead',         -- lead | pianificazione | confermato | concluso | annullato
  note       text,
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);
create index if not exists idx_eventipro_hotel on eventi_pro(hotel_id);

create table if not exists evento_fornitori (
  id         uuid primary key default gen_random_uuid(),
  hotel_id   text not null,
  evento_id  uuid,
  categoria  text default 'Fornitore',    -- Catering, Fiori, Musica, Foto, Staff, Allestimento…
  nome       text,
  costo      numeric default 0,
  stato      text default 'da_contattare',-- da_contattare | contattato | confermato
  note       text
);
create index if not exists idx_evfor_hotel on evento_fornitori(hotel_id);
create index if not exists idx_evfor_evento on evento_fornitori(evento_id);
