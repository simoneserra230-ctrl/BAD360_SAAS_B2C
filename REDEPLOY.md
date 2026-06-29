# 🔁 BAD360 — Guida al REDEPLOY (prod già esistente)

> BAD360 è già online (Render backend Docker `bad360-api` + frontend statico su Vercel +
> Supabase). Questa guida rilascia le **modifiche recenti**. Il deploy parte col `git push`
> (`autoDeploy: true` nel `render.yaml`); niente viene pubblicato in automatico da qui.

## Cosa è cambiato (da rilasciare)
- **Modulo Housekeeping multi-tenant**: `backend/housekeeping_api.py` (router `/api/hk`,
  `require_user` → `hotel_id` SEMPRE dal token) + rimozione vecchi endpoint `/api/hk/*`
  insicuri da `main.py` + `BAD360_SPLIT/housekeeping.html` (add/delete/stato via authFetch).
  Usa **TABELLE NUOVE** `hk_camere` / `hk_forniture` / `hk_task` (`hotel_id TEXT`).
- **Link "✦ Hub"** nel topbar di 23 pagine/moduli `BAD360_SPLIT/` (ritorno all'ecosistema).
- Footer README → SkillSolutions; privacy `barman.html` → barmanadomiciliosardegna@gmail.com.

## ⚠️ DB migration OBBLIGATORIA (prima o insieme al deploy)
Nel progetto **Supabase di BAD360** → SQL Editor → esegui:
- `supabase/housekeeping_schema.sql` (crea `hk_camere`, `hk_forniture`, `hk_task` + indici).
- `supabase/cert_schema.sql` (crea `cert_personale`, `cert_licenze`, `cert_aziendali` — modulo Certificazioni rifatto).
- `supabase/menu_engineering_schema.sql` (`me_recipes` + colonna `hotel_id` — Menu Engineering messo in sicurezza multi-tenant).
- `supabase/hotellerie_schema.sql` (crea `ht_vini` — Carta Vini / Hotellerie F&B).
- `supabase/academy_schema.sql` (crea `academy_corsi`, `academy_iscrizioni` — Academy LMS).
- `supabase/qm_schema.sql` (crea `qm_portfolio` — Quality Manager multi-cliente).
Senza queste tabelle, i moduli Housekeeping / Certificazioni / Menu Engineering / Hotellerie / Academy / Quality Manager vanno in errore.
> NB (fine sessione giu 2026): `academy_schema.sql` e `qm_schema.sql` NON ancora applicate (connettore Supabase offline) → applicarle appena possibile.

## Passi di redeploy
1. **Commit + push** del repo BAD360 → Render ribuilda il Docker (`bad360-api`), il frontend Vercel si aggiorna.
2. **Verifica env su Render** (Dashboard → bad360-api → Environment):
   - `ANTHROPIC_API_KEY`, `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`, `ALLOWED_ORIGINS` (URL frontend)
   - `APP_SECRET` è auto-generata; gli altri (`APP_ENV`, `DEBUG`, rate limit) sono fissi nel `render.yaml`.
3. Esegui la **migration** qui sopra su Supabase (idempotente: `CREATE TABLE IF NOT EXISTS`).

## Verifica post-deploy
- `https://<backend>/api/health` → ok.
- Apri il modulo **Housekeeping** da un account hotel: crea una camera/fornitura/task → deve
  persistere (multi-tenant: vedi solo i dati del tuo `hotel_id`).
- Da un modulo, il link **✦ Hub** porta a `SKILLSOLUTIONS.COM` (in locale è relativo; in prod
  diventerà assoluto quando ci saranno i domini — vedi `ECOSISTEMA_MAPPA_DOMINI.md`).

## Note
- Le altre tabelle moduli (HACCP, shelf-life, drinks, reviews, scm, shifts, saas...) sono in
  `supabase/*_schema.sql` — eseguile se quei moduli non erano ancora migrati.
- Mai chiavi nel frontend: `SUPABASE_SERVICE_KEY` e `ANTHROPIC_API_KEY` solo nelle env di Render.
