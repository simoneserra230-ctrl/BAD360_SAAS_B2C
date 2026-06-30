-- ═══════════════════════════════════════════════════════════════════
--  BAD360.ai — AI Guest Assistant: knowledge base ospiti (multi-tenant)
--  La struttura pubblica le info per gli ospiti; l'AI risponde SOLO da qui.
--  hotel_id TEXT (dal token lato admin). Idempotente.
-- ═══════════════════════════════════════════════════════════════════
create table if not exists guest_kb (
  id         uuid primary key default gen_random_uuid(),
  hotel_id   text not null,
  categoria  text default 'Info',     -- Check-in, Wifi, Colazione, Servizi, Regole, Esperienze, Come arrivare…
  titolo     text not null,
  contenuto  text,
  attivo     boolean default true,
  updated_at timestamptz default now()
);
create index if not exists idx_guest_kb_hotel         on guest_kb(hotel_id);
create index if not exists idx_guest_kb_hotel_attivo  on guest_kb(hotel_id, attivo);
