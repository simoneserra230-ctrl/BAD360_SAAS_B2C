-- BAD360.ai — Privacy (GDPR) & Whistleblowing (niche C5). Multi-tenant hotel_id TEXT. Idempotente.

create table if not exists privacy_trattamenti (
  id                     uuid primary key default gen_random_uuid(),
  hotel_id               text not null,
  nome                   text not null,
  finalita               text,
  base_giuridica         text default 'contratto',
  categorie_dati         text,
  categorie_interessati  text,
  destinatari            text,
  trasferimento_extra_ue boolean default false,
  conservazione          text,
  misure_sicurezza       text,
  created_at             timestamptz default now()
);
create index if not exists idx_privtratt_hotel on privacy_trattamenti(hotel_id);

create table if not exists privacy_breach (
  id                 uuid primary key default gen_random_uuid(),
  hotel_id           text not null,
  data_evento        date,
  descrizione        text not null,
  dati_coinvolti     text,
  gravita            text default 'media',   -- bassa | media | alta
  notificato_garante boolean default false,
  data_notifica      date,
  stato              text default 'aperto',  -- aperto | gestito | chiuso
  created_at         timestamptz default now()
);
create index if not exists idx_privbreach_hotel on privacy_breach(hotel_id);

create table if not exists whistleblowing_segnalazioni (
  id          uuid primary key default gen_random_uuid(),
  hotel_id    text not null,
  codice      text not null,               -- codice di tracciamento (anonimato segnalante)
  oggetto     text not null,
  categoria   text default 'altro',
  descrizione text,
  anonima     boolean default true,
  stato       text default 'ricevuta',     -- ricevuta | in_esame | gestita | archiviata
  esito       text,
  created_at  timestamptz default now()
);
create index if not exists idx_wb_hotel on whistleblowing_segnalazioni(hotel_id);
create index if not exists idx_wb_codice on whistleblowing_segnalazioni(codice);
