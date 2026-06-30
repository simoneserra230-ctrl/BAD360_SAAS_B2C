-- ═══════════════════════════════════════════════════════════════════
--  BAD360.ai — Upsell Esperienze (Layer Ospite & Ricavi #2)
--  Catalogo esperienze + prenotazioni (multi-tenant, hotel_id TEXT). Idempotente.
-- ═══════════════════════════════════════════════════════════════════
create table if not exists esperienze (
  id             uuid primary key default gen_random_uuid(),
  hotel_id       text not null,
  titolo         text not null,
  descrizione    text,
  categoria      text default 'Esperienza',
  prezzo         numeric default 0,
  durata         text,
  fornitore      text default 'interno',   -- interno | BAD | esterno
  richiede_staff boolean default false,    -- → ponte Barman Match
  attivo         boolean default true,
  updated_at     timestamptz default now()
);
create index if not exists idx_esp_hotel on esperienze(hotel_id);

create table if not exists esperienze_prenotazioni (
  id                uuid primary key default gen_random_uuid(),
  hotel_id          text not null,
  esperienza_id     uuid,
  esperienza_titolo text,
  ospite_nome       text not null,
  ospite_contatto   text,
  data              date,
  n_persone         int default 1,
  stato             text default 'richiesta',  -- richiesta | confermata | erogata | annullata
  ricavo            numeric,
  note              text,
  created_at        timestamptz default now()
);
create index if not exists idx_esppren_hotel        on esperienze_prenotazioni(hotel_id);
create index if not exists idx_esppren_hotel_stato  on esperienze_prenotazioni(hotel_id, stato);
