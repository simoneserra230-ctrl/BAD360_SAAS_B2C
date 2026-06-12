# BAD360.ai — Stato e Percorso al Lancio
# Aggiornato: 12 giugno 2026 | Ruolo strategico: SECONDO ATTO (upsell ai clienti BA.IA)

## Cos'è
Suite SaaS per bar, ristoranti e hotel: 22+ moduli (HACCP, shift, inventory,
shelf life, tracciabilità, academy, recensioni, bandi...) + 8 agenti AI integrati.
Design system warm gold (#C9A84C) — bad360-ds.css. Backend FastAPI + Supabase.

## Stato attuale — COMPLETO AL ~70%
✅ 22 pagine moduli in BAD360_SPLIT (rebuild design gold in corso, quasi completo)
✅ 8 agenti AI implementati (Review Manager, Inventory, Shift Planner, Concierge,
   Event Planner, Training Tracker, Tutor, SOP Generator)
✅ bad360-sdk.js + login + account demo
✅ Backend FastAPI + Supabase (37 tabelle) + render.yaml + Dockerfile
✅ Repo GitHub: simoneserra230-ctrl/BAD360_SAAS_B2C
✅ BAD360_CONTINUITY.md per riprendere il rebuild in nuove sessioni
⬜ Rebuild pagine: verificare le ultime sezioni vs design system
⬜ Deploy produzione mai eseguito end-to-end
⬜ Pagamenti/abbonamenti non configurati
⬜ Zero clienti

## NON nel repo (per scelta)
- `file input/` (386 MB documenti operativi — fonte contenuti, restano locali)
- `STORICO HTML/` (backup vecchie versioni)
- `BAD360_ACCOUNT_DEMO.txt` (credenziali demo)

## Percorso al "livello finale" (lancio)
1. Completare rebuild gold (seguire BAD360_CONTINUITY.md)
2. Smoke test moduli core: login → hub → 3 moduli principali con dati demo
3. Deploy: backend Render + frontend Vercel (config pronte)
4. Pricing a moduli (proposta: base €49/mese, pro €99/mese) + Stripe
5. Lancio SOLO dopo che BA.IA ha i primi clienti (strategia del cuneo:
   BAD360 si vende meglio a chi già si fida via BA.IA)

## Collegamenti ecosistema
- Modulo bandi.html → futuro white-label del motore BA.IA
- Modulo academy → contenuti da SSFormazione quando riprende
- shiftmanager → futuro collegamento BarmanMatch (staff)
