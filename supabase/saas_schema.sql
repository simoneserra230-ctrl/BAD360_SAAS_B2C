-- ════════════════════════════════════════════════════════════════════
-- BAD360.ai — SaaS layer schema (paywall, billing, quota, settings)
-- Esegui UNA VOLTA nel SQL editor di Supabase.
-- ════════════════════════════════════════════════════════════════════

-- Impostazioni del sito (API key, SMTP, Stripe…). Gestite dal pannello admin.
create table if not exists site_settings (
    key         text primary key,
    value       text,
    updated_at  timestamptz default now()
);

-- Abbonamento/piano per utente (chiave: email). plan: trial|free|active|expired
create table if not exists subscriptions (
    email          text primary key,
    plan           text default 'trial',
    trial_ends_at  text,
    updated_at     timestamptz default now()
);

-- Contatore operazioni AI per utente/mese (controllo costi modello centralizzato)
create table if not exists usage_counters (
    email   text not null,
    period  text not null,           -- 'YYYY-MM'
    count   integer default 0,
    primary key (email, period)
);

-- Preferenze utente (notifiche email, ecc.)
create table if not exists user_prefs (
    email  text not null,
    key    text not null,
    value  text,
    primary key (email, key)
);

-- Nota: queste tabelle sono gestite dal backend con la SERVICE KEY,
-- quindi non serve abilitare policy RLS specifiche per il client anon.
