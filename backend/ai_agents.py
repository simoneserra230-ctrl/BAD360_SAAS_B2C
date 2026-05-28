"""
BAD360.ai — AI Agents Proattivi
Agenti intelligenti che analizzano dati operativi e generano
raccomandazioni azionabili via Claude.

Endpoints:
  POST /api/agents/smart-reorder      — Suggerimenti riordino intelligente
  GET  /api/agents/compliance-score   — Score conformità HACCP/NC con trend
  POST /api/agents/revenue-insights   — Analisi RevPAR/ADR con insight AI
  GET  /api/agents/vendor-health      — Salute complessiva parco fornitori
"""

from __future__ import annotations
import os
import logging
from datetime import date, datetime, timedelta
from typing import Optional, List, Dict

import httpx
from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

logger = logging.getLogger("bad360.ai_agents")
router = APIRouter(prefix="/api/agents", tags=["AI Agents"])

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
SUPABASE_URL      = os.getenv("SUPABASE_URL", "")


# ── Shared Claude helper ──────────────────────────────────────────────

async def _ask_claude(prompt: str, max_tokens: int = 800, model: str = "claude-haiku-4-5-20251001") -> str:
    if not ANTHROPIC_API_KEY:
        return "[AI non disponibile — configura ANTHROPIC_API_KEY]"
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": ANTHROPIC_API_KEY,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": model,
                    "max_tokens": max_tokens,
                    "messages": [{"role": "user", "content": prompt}],
                },
            )
        data = resp.json()
        return data["content"][0]["text"]
    except Exception as e:
        logger.error(f"[AI Agents] Claude error: {e}")
        return f"[Errore AI: {e}]"


# ══════════════════════════════════════════════════════════════════════
#  AGENT 1 — SMART REORDER
#  Analizza inventario vs PAR level → suggerisce ordini ottimali
# ══════════════════════════════════════════════════════════════════════

class SmartReorderRequest(BaseModel):
    hotel_id: str
    categoria: Optional[str] = None
    giorni_copertura_target: int = 7


def _demo_inventory_status() -> List[dict]:
    return [
        {"articolo": "Prosciutto Crudo DOP", "categoria": "Salumi",        "giacenza": 8.0,  "par_level": 20.0, "unita": "kg",  "consumo_medio_giorno": 2.5,  "fornitore": "Salumificio Sardo", "prezzo_kg": 38.5},
        {"articolo": "Mozzarella di Bufala", "categoria": "Latticini",     "giacenza": 3.2,  "par_level": 15.0, "unita": "kg",  "consumo_medio_giorno": 3.0,  "fornitore": "Caseificio Campano","prezzo_kg": 22.0},
        {"articolo": "Bottarga di Muggine",  "categoria": "Pesce/Ittico",  "giacenza": 1.5,  "par_level": 5.0,  "unita": "kg",  "consumo_medio_giorno": 0.3,  "fornitore": "Pescheria Cagliari","prezzo_kg": 185.0},
        {"articolo": "Olio EVO Sardegna Bio","categoria": "Oli",           "giacenza": 18.0, "par_level": 24.0, "unita": "L",   "consumo_medio_giorno": 0.8,  "fornitore": "Frantoi Oristano",  "prezzo_L": 18.0},
        {"articolo": "Frutta fresca mista",  "categoria": "Ortofrutta",    "giacenza": 12.0, "par_level": 30.0, "unita": "kg",  "consumo_medio_giorno": 5.0,  "fornitore": "Frutta & Co. Srl",  "prezzo_kg": 4.5},
        {"articolo": "Farina 00 bio",        "categoria": "Pane e pasta",  "giacenza": 25.0, "par_level": 20.0, "unita": "kg",  "consumo_medio_giorno": 3.0,  "fornitore": "Mulino Campano",    "prezzo_kg": 2.8},
        {"articolo": "Vino Rosso IGP",       "categoria": "Vini",          "giacenza": 6.0,  "par_level": 30.0, "unita": "bott","consumo_medio_giorno": 4.0,  "fornitore": "Cantina Sarda Srl", "prezzo_bott": 12.0},
    ]


@router.post("/smart-reorder", summary="Agente Smart Reorder — suggerimenti ordini ottimali")
async def smart_reorder(req: SmartReorderRequest):
    """
    Analizza la giacenza corrente vs PAR level e consumo storico.
    Calcola quantità ottimali da ordinare e genera raccomandazioni AI.
    """
    items = _demo_inventory_status()
    if req.categoria:
        items = [i for i in items if i["categoria"].lower() == req.categoria.lower()]

    target_days = req.giorni_copertura_target
    reorder_list = []

    for item in items:
        consumo = item.get("consumo_medio_giorno", 1.0)
        giacenza = item.get("giacenza", 0)
        par = item.get("par_level", 10)
        giorni_rimasti = giacenza / consumo if consumo > 0 else 999
        qty_target = consumo * target_days
        qty_da_ordinare = max(0, qty_target - giacenza)
        urgenza = (
            "URGENTE" if giorni_rimasti < 2
            else "ALTA" if giorni_rimasti < target_days
            else "NORMALE" if qty_da_ordinare > 0
            else "OK"
        )

        if qty_da_ordinare > 0 or urgenza in ("URGENTE", "ALTA"):
            unit_price = item.get("prezzo_kg") or item.get("prezzo_L") or item.get("prezzo_bott") or 0
            reorder_list.append({
                "articolo":      item["articolo"],
                "categoria":     item["categoria"],
                "fornitore":     item["fornitore"],
                "giacenza_att":  giacenza,
                "unita":         item["unita"],
                "giorni_rimasti": round(giorni_rimasti, 1),
                "qty_da_ordinare": round(qty_da_ordinare, 1),
                "valore_ordine_est": round(qty_da_ordinare * unit_price, 2),
                "urgenza":       urgenza,
            })

    reorder_list.sort(key=lambda x: {"URGENTE": 0, "ALTA": 1, "NORMALE": 2, "OK": 3}[x["urgenza"]])

    # AI narrative
    riassunto = "\n".join(
        f"- {r['articolo']}: ordina {r['qty_da_ordinare']} {r['unita']} da {r['fornitore']} "
        f"(giacenza per {r['giorni_rimasti']}gg, urgenza: {r['urgenza']})"
        for r in reorder_list[:8]
    )
    totale_valore = sum(r["valore_ordine_est"] for r in reorder_list)

    ai_text = await _ask_claude(
        f"""Sei un esperto di supply chain alberghiero. Analizza questi ordini da fare entro oggi e fornisci:
1. Priorità di acquisto (chi chiamare SUBITO)
2. Possibilità di consolidare ordini per risparmiare
3. Un consiglio strategico su un fornitore da valutare
Lista riordini:
{riassunto}
Valore totale stimato: €{totale_valore:.0f}
Rispondi in italiano, max 150 parole, tono operativo e diretto.""",
        max_tokens=400
    )

    return {
        "data": date.today().isoformat(),
        "hotel_id": req.hotel_id,
        "reorder_list": reorder_list,
        "totale_articoli_da_ordinare": len(reorder_list),
        "valore_totale_stimato_eur": round(totale_valore, 2),
        "raccomandazioni_ai": ai_text,
        "giorni_copertura_target": target_days,
        "nota": "Demo mode" if not SUPABASE_URL else "Live",
    }


# ══════════════════════════════════════════════════════════════════════
#  AGENT 2 — COMPLIANCE SCORE
#  Score aggregato HACCP + NC con trend e insight AI
# ══════════════════════════════════════════════════════════════════════

@router.get("/compliance-score", summary="Agente Compliance Score — HACCP + NC con trend AI")
async def compliance_score(hotel_id: str = Query("hotel-demo-001")):
    """
    Calcola il punteggio di conformità aggregato (HACCP + NC + SLA)
    con trend degli ultimi 30 giorni e analisi AI dei rischi.
    """
    # Demo data — replace with Supabase queries in production
    nc_data = {
        "aperte": 3, "chiuse_30gg": 18, "scadute": 1,
        "per_tipo": {"temperatura": 2, "documentazione": 1, "qualita": 0},
        "per_priorita": {"ALTA": 1, "MEDIA": 1, "BASSA": 1},
        "trend_mensile": [12, 15, 18, 14, 11, 9, 8],  # last 7 months
    }
    haccp_data = {
        "ccp_ok": 9, "ccp_totali": 11,
        "temperature_fuori_range_7gg": 2,
        "registrazioni_mancanti_7gg": 0,
        "ultimo_audit": (date.today() - timedelta(days=22)).isoformat(),
    }
    sla_data = {
        "fornitori_in_breach": 2, "fornitori_totali": 8,
        "compliance_media_pct": 87.3,
    }

    # Score calculation
    nc_score = max(0, 100 - (nc_data["aperte"] * 8) - (nc_data["scadute"] * 15) - (nc_data["per_priorita"]["ALTA"] * 10))
    haccp_score = (haccp_data["ccp_ok"] / haccp_data["ccp_totali"]) * 100 - (haccp_data["temperature_fuori_range_7gg"] * 5)
    sla_score = sla_data["compliance_media_pct"]
    overall = round((nc_score * 0.4 + haccp_score * 0.4 + sla_score * 0.2), 1)

    livello = "ECCELLENTE" if overall >= 90 else "BUONO" if overall >= 75 else "ATTENZIONE" if overall >= 60 else "CRITICO"

    ai_text = await _ask_claude(
        f"""Sei un auditor di conformità HACCP e qualità per hotel. Analizza questi dati e dai 3 raccomandazioni concrete:
NC score: {nc_score:.0f}/100 ({nc_data['aperte']} NC aperte, {nc_data['scadute']} scadute, {nc_data['per_priorita']['ALTA']} alta priorità)
HACCP score: {haccp_score:.0f}/100 ({haccp_data['ccp_ok']}/{haccp_data['ccp_totali']} CCP ok, {haccp_data['temperature_fuori_range_7gg']} temp. fuori range nell'ultima settimana, ultimo audit {haccp_data['ultimo_audit']})
SLA score: {sla_score:.0f}/100 ({sla_data['fornitori_in_breach']}/{sla_data['fornitori_totali']} fornitori in breach)
Score complessivo: {overall}/100 — {livello}
Rispondi in italiano, tono da consulente esperto, max 180 parole.""",
        max_tokens=450
    )

    return {
        "data": date.today().isoformat(),
        "hotel_id": hotel_id,
        "score_complessivo": overall,
        "livello": livello,
        "dettaglio": {
            "nc_score":    round(nc_score, 1),
            "haccp_score": round(haccp_score, 1),
            "sla_score":   round(sla_score, 1),
        },
        "pesi": {"nc": "40%", "haccp": "40%", "sla": "20%"},
        "dati_grezzi": {"nc": nc_data, "haccp": haccp_data, "sla": sla_data},
        "trend_nc_7mesi": nc_data["trend_mensile"],
        "analisi_ai": ai_text,
        "nota": "Demo mode" if not SUPABASE_URL else "Live",
    }


# ══════════════════════════════════════════════════════════════════════
#  AGENT 3 — REVENUE INSIGHTS
#  Analisi RevPAR/ADR/Occupazione con benchmark e insight AI
# ══════════════════════════════════════════════════════════════════════

class RevenueInsightsRequest(BaseModel):
    hotel_id: str
    adr_attuale: float = Field(..., description="Average Daily Rate attuale €")
    occupazione_pct: float = Field(..., description="Occupazione % (0-100)")
    camere_totali: int = Field(..., description="Numero totale camere")
    stelle: int = Field(4, ge=2, le=5, description="Categoria hotel (stelle)")
    mese: Optional[int] = None
    anno: Optional[int] = None


# Italian benchmark data by star rating
_BENCHMARKS = {
    3: {"adr": 95,  "occupazione": 62, "revpar": 59,  "fb_cost_pct": 32},
    4: {"adr": 145, "occupazione": 68, "revpar": 99,  "fb_cost_pct": 28},
    5: {"adr": 290, "occupazione": 72, "revpar": 209, "fb_cost_pct": 25},
}


@router.post("/revenue-insights", summary="Agente Revenue Insights — analisi RevPAR + AI benchmark")
async def revenue_insights(req: RevenueInsightsRequest):
    """
    Calcola RevPAR, confronta con benchmark italiani per categoria,
    identifica gap e genera insight strategici via AI.
    """
    revpar = req.adr_attuale * (req.occupazione_pct / 100)
    bench = _BENCHMARKS.get(req.stelle, _BENCHMARKS[4])
    bench_revpar = bench["adr"] * (bench["occupazione"] / 100)

    gap_adr = req.adr_attuale - bench["adr"]
    gap_occ = req.occupazione_pct - bench["occupazione"]
    gap_revpar = revpar - bench_revpar

    ricavi_attuali = revpar * req.camere_totali * 30
    ricavi_potenziali = bench_revpar * req.camere_totali * 30
    upside = ricavi_potenziali - ricavi_attuali

    ai_text = await _ask_claude(
        f"""Sei un Revenue Manager esperto per hotel italiani {req.stelle} stelle. Analizza la performance:
ADR attuale: €{req.adr_attuale} vs benchmark: €{bench['adr']} (gap {gap_adr:+.0f}€)
Occupazione: {req.occupazione_pct}% vs benchmark: {bench['occupazione']}% (gap {gap_occ:+.0f}%)
RevPAR: €{revpar:.1f} vs benchmark: €{bench_revpar:.1f} (gap {gap_revpar:+.0f}€)
Camere: {req.camere_totali} | Ricavi mensili stimati: €{ricavi_attuali:,.0f}
Potenziale mensile non catturato: €{upside:,.0f}

Fornisci:
1. Diagnosi principale (in 2 righe)
2. Top 3 leve di revenue management per recuperare il gap
3. Un'opportunità non ovvia specifica per un hotel italiano {req.stelle}*
Tono: consulenziale, pratico, concreto. Max 200 parole in italiano.""",
        max_tokens=500
    )

    return {
        "data": date.today().isoformat(),
        "hotel_id": req.hotel_id,
        "kpi_attuali": {
            "adr": req.adr_attuale,
            "occupazione_pct": req.occupazione_pct,
            "revpar": round(revpar, 2),
            "ricavi_mensili_est": round(ricavi_attuali, 0),
        },
        "benchmark_italiano": {
            "stelle": req.stelle,
            "adr_bench": bench["adr"],
            "occupazione_bench": bench["occupazione"],
            "revpar_bench": round(bench_revpar, 2),
        },
        "gap_analysis": {
            "adr_gap":    round(gap_adr, 2),
            "occ_gap":    round(gap_occ, 2),
            "revpar_gap": round(gap_revpar, 2),
            "upside_mensile_eur": round(upside, 0),
            "performance": "SOPRA" if revpar > bench_revpar else "SOTTO",
        },
        "insights_ai": ai_text,
        "nota": "Benchmark: medie nazionali 2024 — Federalberghi + STR Italy",
    }


# ══════════════════════════════════════════════════════════════════════
#  AGENT 4 — VENDOR HEALTH
#  Panoramica salute parco fornitori con scoring e alert
# ══════════════════════════════════════════════════════════════════════

@router.get("/vendor-health", summary="Agente Vendor Health — salute parco fornitori")
async def vendor_health(hotel_id: str = Query("hotel-demo-001")):
    """
    Calcola il vendor health score aggregato per tutti i fornitori attivi,
    con ranking, alert critici e raccomandazioni AI.
    """
    # Demo vendor data
    vendors = [
        {"nome": "Salumificio Sardo Srl",    "otd": 94, "qualita": 91, "prezzo": 85, "compliance": 100, "nc_30gg": 0, "categoria": "Salumi"},
        {"nome": "Caseificio Campano SpA",   "otd": 88, "qualita": 82, "prezzo": 90, "compliance": 95,  "nc_30gg": 1, "categoria": "Latticini"},
        {"nome": "Frigo Express Srl",        "otd": 72, "qualita": 78, "prezzo": 95, "compliance": 80,  "nc_30gg": 2, "categoria": "Logistica freddo"},
        {"nome": "Bio Latte Srl",            "otd": 85, "qualita": 80, "prezzo": 88, "compliance": 92,  "nc_30gg": 1, "categoria": "Latticini bio"},
        {"nome": "Frantoi Oristano SpA",     "otd": 97, "qualita": 96, "prezzo": 82, "compliance": 100, "nc_30gg": 0, "categoria": "Oli"},
        {"nome": "Pescheria Cagliari Srl",   "otd": 91, "qualita": 94, "prezzo": 78, "compliance": 98,  "nc_30gg": 0, "categoria": "Pesce/Ittico"},
        {"nome": "Cantina Sarda Srl",        "otd": 96, "qualita": 95, "prezzo": 88, "compliance": 100, "nc_30gg": 0, "categoria": "Vini"},
        {"nome": "Frutta & Co. Srl",         "otd": 83, "qualita": 86, "prezzo": 92, "compliance": 90,  "nc_30gg": 1, "categoria": "Ortofrutta"},
    ]

    scored = []
    for v in vendors:
        score = (
            v["otd"] * 0.30 +
            v["qualita"] * 0.25 +
            v["prezzo"] * 0.20 +
            v["compliance"] * 0.15 +
            max(0, 100 - v["nc_30gg"] * 10) * 0.10
        )
        classe = "A" if score >= 90 else "B" if score >= 78 else "C" if score >= 65 else "D"
        scored.append({**v, "score": round(score, 1), "classe": classe})

    scored.sort(key=lambda x: -x["score"])
    critici = [v for v in scored if v["classe"] in ("C", "D")]
    top = scored[:3]

    ai_text = await _ask_claude(
        f"""Sei un esperto di supply chain alberghiero. Analizza il parco fornitori:
Fornitori totali: {len(scored)}
Top performer: {', '.join(f"{v['nome']} ({v['score']:.0f}/100)" for v in top)}
Critici (classe C/D): {', '.join(f"{v['nome']} ({v['score']:.0f}/100, {v['nc_30gg']} NC)" for v in critici) or 'Nessuno'}
Score medio parco: {sum(v['score'] for v in scored)/len(scored):.1f}/100

Rispondi con:
1. Giudizio globale sul parco fornitori (2 righe)
2. Un'azione specifica per il fornitore più critico
3. Un suggerimento per rafforzare il rapporto col fornitore migliore
Max 150 parole, tono consulenziale in italiano.""",
        max_tokens=400
    )

    return {
        "data": date.today().isoformat(),
        "hotel_id": hotel_id,
        "score_medio_parco": round(sum(v["score"] for v in scored) / len(scored), 1),
        "fornitori": scored,
        "riepilogo": {
            "classe_A": sum(1 for v in scored if v["classe"] == "A"),
            "classe_B": sum(1 for v in scored if v["classe"] == "B"),
            "classe_C": sum(1 for v in scored if v["classe"] == "C"),
            "classe_D": sum(1 for v in scored if v["classe"] == "D"),
            "critici": len(critici),
        },
        "analisi_ai": ai_text,
        "nota": "Demo mode" if not SUPABASE_URL else "Live",
    }
