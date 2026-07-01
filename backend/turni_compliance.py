"""
BAD360.ai — Scheduling labor-compliant (niche F)

Verifica DETERMINISTICA della conformità di una rota ai vincoli tipo CCNL/D.Lgs 66/2003:
- riposo giornaliero ≥ 11h consecutive tra due turni dello stesso dipendente
- durata massima del singolo turno (≤13h indicativo)
- pausa obbligatoria se turno > 6h (reminder)
- ore settimanali ≤ 48h (media; qui per settimana ISO)
- riposo settimanale: flag se lavora 7 giorni consecutivi

È un CHECK (stateless): non salva nulla, riceve i turni e restituisce le violazioni +
uno score. Human-in-the-loop: i massimali esatti dipendono dal CCNL applicabile → verifica.
Enhancement naturale: leggere dai turni salvati (modulo Turni) — qui resta su input.
"""
from __future__ import annotations
from datetime import datetime, timedelta
from typing import Optional, List

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from backend.auth import require_user, UserProfile
from backend.roles import require_module

router = APIRouter(prefix="/api/turnicompliance", tags=["Scheduling CCNL"], dependencies=[Depends(require_module("turnicompliance"))])

RIPOSO_MIN_H = 11
MAX_GIORNALIERO_H = 13
PAUSA_SOGLIA_H = 6
MAX_SETTIMANALE_H = 48
DISCLAIMER = ("⚠️ Verifica INDICATIVA (D.Lgs 66/2003 / vincoli tipo CCNL). I massimali esatti "
              "(riposi, deroghe, settori) dipendono dal CCNL applicabile: confronta con il tuo contratto.")


class Turno(BaseModel):
    dipendente: str
    giorno:     str          # YYYY-MM-DD
    inizio:     str          # HH:MM
    fine:       str          # HH:MM


class CheckBody(BaseModel):
    turni: List[Turno]


def _dt(giorno: str, ora: str) -> datetime:
    return datetime.strptime(f"{giorno} {ora}", "%Y-%m-%d %H:%M")


def _parse(turni: List[Turno]):
    out = []
    for t in turni:
        try:
            s = _dt(t.giorno, t.inizio)
            e = _dt(t.giorno, t.fine)
        except ValueError:
            raise HTTPException(400, f"Formato data/ora non valido per {t.dipendente} {t.giorno}")
        if e <= s:
            e += timedelta(days=1)      # turno a cavallo della mezzanotte
        out.append({"dip": t.dipendente.strip(), "start": s, "end": e,
                    "ore": (e - s).total_seconds() / 3600, "giorno": t.giorno})
    return out


def _max_consecutivi(date_set) -> int:
    if not date_set:
        return 0
    days = sorted(datetime.strptime(d, "%Y-%m-%d").date() for d in date_set)
    best = run = 1
    for i in range(1, len(days)):
        run = run + 1 if (days[i] - days[i - 1]).days == 1 else 1
        best = max(best, run)
    return best


@router.post("/check", summary="Verifica conformità rota (deterministico)")
async def check(body: CheckBody, _user: UserProfile = Depends(require_user)):
    if not body.turni:
        return {"ok": False, "error": "Nessun turno fornito"}
    shifts = _parse(body.turni)
    viol = []
    note = []

    # per turno: durata + pausa
    for s in shifts:
        if s["ore"] > MAX_GIORNALIERO_H:
            viol.append({"dipendente": s["dip"], "giorno": s["giorno"], "tipo": "durata_turno",
                         "dettaglio": f"Turno di {s['ore']:.1f}h supera il massimo indicativo di {MAX_GIORNALIERO_H}h", "gravita": "alta"})
        elif s["ore"] > PAUSA_SOGLIA_H:
            note.append({"dipendente": s["dip"], "giorno": s["giorno"], "tipo": "pausa",
                         "dettaglio": f"Turno di {s['ore']:.1f}h (>{PAUSA_SOGLIA_H}h): deve essere prevista una pausa"})

    # per dipendente: riposo giornaliero, ore settimanali, riposo settimanale
    by_dip: dict = {}
    for s in shifts:
        by_dip.setdefault(s["dip"], []).append(s)
    riepilogo = []
    for dip, ss in by_dip.items():
        ss.sort(key=lambda x: x["start"])
        for prev, nxt in zip(ss, ss[1:]):
            riposo = (nxt["start"] - prev["end"]).total_seconds() / 3600
            if 0 <= riposo < RIPOSO_MIN_H:
                viol.append({"dipendente": dip, "giorno": nxt["giorno"], "tipo": "riposo_giornaliero",
                             "dettaglio": f"Solo {riposo:.1f}h di riposo prima del turno (minimo {RIPOSO_MIN_H}h)", "gravita": "alta"})
        # ore per settimana ISO
        per_sett: dict = {}
        for s in ss:
            wk = s["start"].isocalendar()[:2]
            per_sett[wk] = per_sett.get(wk, 0) + s["ore"]
        for wk, ore in per_sett.items():
            if ore > MAX_SETTIMANALE_H:
                viol.append({"dipendente": dip, "giorno": f"sett. {wk[1]}/{wk[0]}", "tipo": "ore_settimanali",
                             "dettaglio": f"{ore:.1f}h in settimana (max indicativo {MAX_SETTIMANALE_H}h)", "gravita": "media"})
        # riposo settimanale
        if _max_consecutivi({s["giorno"] for s in ss}) >= 7:
            viol.append({"dipendente": dip, "giorno": "—", "tipo": "riposo_settimanale",
                         "dettaglio": "Lavora 7+ giorni consecutivi: manca il riposo settimanale", "gravita": "alta"})
        riepilogo.append({"dipendente": dip, "turni": len(ss), "ore_totali": round(sum(s["ore"] for s in ss), 1)})

    score = max(0, 100 - 12 * len(viol))
    return {"ok": True, "conforme": len(viol) == 0, "score": score,
            "violazioni": viol, "note": note, "riepilogo": riepilogo, "disclaimer": DISCLAIMER}


@router.post("/ai/spiega", summary="Spiega le violazioni e suggerisci come sistemare (AI)")
async def ai_spiega(body: CheckBody, user: UserProfile = Depends(require_user)):
    res = await check(body, user)
    if res.get("conforme"):
        return {"ok": True, "spiegazione": "✅ La rota risulta conforme ai controlli indicativi. Verifica comunque il CCNL applicabile.", "disclaimer": DISCLAIMER}
    elenco = "; ".join(f"{v['dipendente']} ({v['tipo']}): {v['dettaglio']}" for v in res["violazioni"][:20])
    prompt = (
        "Sei un consulente del lavoro. Spiega in modo semplice queste criticità di una rota e suggerisci "
        "come RISISTEMARE i turni per renderla conforme (riposo 11h, riposo settimanale, ore max, pause). "
        "Conciso, operativo. Ricorda che i massimali dipendono dal CCNL applicabile.\n\n"
        f"CRITICITÀ: {elenco}"
    )
    from backend.ai_agents import _ask_claude
    try:
        out = await _ask_claude(prompt, max_tokens=600)
    except Exception as ex:
        raise HTTPException(502, f"AI non raggiungibile: {ex}")
    return {"ok": True, "spiegazione": (out or "").strip(), "violazioni": res["violazioni"], "disclaimer": DISCLAIMER}
