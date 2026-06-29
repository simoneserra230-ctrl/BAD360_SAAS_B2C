-- ═══════════════════════════════════════════════════════════════════
--  RLS — tabelle BA.IA nel progetto Supabase BAD360 (iajffojwiabfiuevainv)
--  ✅ APPLICATO il 29 giu 2026 (migration enable_rls_baia_tables) dopo verifica:
--     tutte le 14 tabelle owner=postgres con BYPASSRLS=true → backend (asyncpg
--     owner) e service_role non impattati. Post-check: rowsecurity=true su 14/14.
--     Rollback eventuale: ALTER TABLE public.<t> DISABLE ROW LEVEL SECURITY;
--
--  PROBLEMA (advisory Supabase, livello CRITICO):
--    14 tabelle BA.IA in questo progetto hanno RLS DISABILITATO → chiunque
--    abbia la anon key puo' leggere/scrivere ogni riga, incluse users e
--    sessions (credenziali e token di sessione).
--
--  ANALISI DI SICUREZZA (verificata sul CODICE, non a memoria — giu 2026):
--    • Backend BA.IA: si connette via asyncpg + DATABASE_URL (backend/db.py,
--      sqlite_pg_bridge.py) = connessione diretta come ruolo OWNER (postgres),
--      che **BYPASSA RLS**.
--    • Frontend BA.IA: NON usa supabase-js ne' la anon key (grep su frontend/
--      pulito) — parla solo col proprio backend via BACKEND_URL.
--    • service_role di Supabase ha BYPASSRLS.
--    ⇒ Abilitare RLS SENZA policy (deny-all per anon/authenticated) CHIUDE il
--      buco e NON rompe nulla: backend (owner) e service_role continuano a
--      leggere/scrivere normalmente.
--
--  ⚠️ USARE "ENABLE" (NON "FORCE"): FORCE ROW LEVEL SECURITY farebbe rispettare
--     le policy anche all'OWNER → bloccherebbe il backend asyncpg. NON usarlo.
--
--  PRE-FLIGHT (da verificare PRIMA di eseguire):
--    1. La DATABASE_URL di BA.IA punta a QUESTO progetto e si connette come
--       owner: esegui sul backend  ->  SELECT current_user;   (atteso: postgres)
--    2. Nessun ALTRO consumer usa la anon key su queste tabelle (Edge Functions,
--       altri frontend, automazioni/n8n, ecc.). [frontend BA.IA gia' verificato = ok]
--    3. Esegui in finestra a basso traffico, poi TEST:
--         - login BA.IA  (tabelle users/sessions)
--         - scraper bandi (scraper_log/bandi)
--         - portale cliente + rendicontazione (portal_*/rendicontazione_*)
--
--  ROLLBACK immediato se qualcosa si blocca:
--    ALTER TABLE public.<tabella> DISABLE ROW LEVEL SECURITY;
-- ═══════════════════════════════════════════════════════════════════

-- ── Credenziali / sessioni (priorita' massima) ──
ALTER TABLE public.users    ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.sessions ENABLE ROW LEVEL SECURITY;

-- ── Dati core BA.IA ──
ALTER TABLE public.bandi       ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.aziende     ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.sal         ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.history     ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.scraper_log ENABLE ROW LEVEL SECURITY;

-- ── Portale cliente ──
ALTER TABLE public.portal_shares   ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.portal_messages ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.portal_docs     ENABLE ROW LEVEL SECURITY;

-- ── Rendicontazione ──
ALTER TABLE public.rendicontazioni            ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.rendicontazione_milestones ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.rendicontazione_documenti  ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.rendicontazione_checklist  ENABLE ROW LEVEL SECURITY;

-- NB: nessuna CREATE POLICY. "Deny-all per anon/authenticated" e' il
--     comportamento VOLUTO: queste tabelle sono solo backend. Owner (asyncpg)
--     e service_role bypassano RLS e continuano a funzionare.
--
-- Verifica post-applicazione (deve restituire rowsecurity=true per tutte):
--   SELECT relname, relrowsecurity FROM pg_class
--   WHERE relname IN ('users','sessions','bandi','aziende','sal','history',
--     'scraper_log','portal_shares','portal_messages','portal_docs',
--     'rendicontazioni','rendicontazione_milestones','rendicontazione_documenti',
--     'rendicontazione_checklist');
