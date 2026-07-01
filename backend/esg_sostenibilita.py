"""
BAD360.ai — AI ESG / Sostenibilità CSRD (niche C, ondata normativa)

Dal 2026 le strutture devono fornire dati ESG certificati/audit (CSRD); l'ESG incide su
financing, eligibilità brand e ranking sui portali. Qui: raccolta indicatori (energia,
acqua, rifiuti, sociale, governance) + bozza report AI + PONTE a BA.IA (bandi green per
finanziare gli interventi: efficienza energetica, fotovoltaico, ISO 14001/EMAS).

PRINCIPIO: human-in-the-loop. Il report è una BOZZA; i dati CSRD vanno AUDIT/certificati.
Sicurezza: hotel_id dal token. Tabella: esg_indicatori (nuova, TEXT — non la legacy esg_reports UUID).
"""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from backend.database import get_supabase
from backend.auth import require_user, UserProfile
from backend.roles import require_module

router = APIRouter(prefix="/api/esg", tags=["ESG / Sostenibilità"], dependencies=[Depends(require_module("esg"))])
DISCLAIMER = ("⚠️ BOZZA AI — i dati ESG ai fini CSRD vanno VERIFICATI e CERTIFICATI/AUDIT. "
              "Non usare questi numeri come rendicontazione ufficiale senza controllo.")

CATEGORIE = ["energia", "acqua", "rifiuti", "emissioni", "sociale", "governance"]

# Ponte BA.IA: aree di bando che finanziano gli interventi ESG (la ricerca bandi vera è in BA.IA)
BANDI_GREEN = [
    {"area": "Efficienza energetica", "esempi": "metering, illuminazione, climatizzazione efficiente"},
    {"area": "Fotovoltaico / rinnovabili", "esempi": "impianti FV, autoconsumo, comunità energetiche"},
    {"area": "Transizione 5.0 / ecologica", "esempi": "investimenti green per imprese"},
    {"area": "Certificazione ambientale", "esempi": "ISO 14001 / EMAS, ecolabel"},
    {"area": "Gestione rifiuti / economia circolare", "esempi": "riduzione sprechi, riuso"},
]


def _sb():
    sb = get_supabase()
    if not sb:
        raise HTTPException(503, "Database non configurato")
    return sb


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Indicatore(BaseModel):
    id:         Optional[str] = None
    periodo:    Optional[str] = None         # es. "2026" o "2026-Q1"
    categoria:  str                          # energia|acqua|rifiuti|emissioni|sociale|governance
    indicatore: str                          # es. "Consumo energia elettrica"
    valore:     Optional[float] = None
    unita:      Optional[str] = None         # kWh, m3, kg, tCO2, %, n…
    note:       Optional[str] = None


@router.get("/indicatori", summary="Indicatori ESG (admin)")
async def list_indicatori(user: UserProfile = Depends(require_user), categoria: Optional[str] = None):
    sb = _sb()
    q = sb.table("esg_indicatori").select("*").eq("hotel_id", user.hotel_id)
    if categoria:
        q = q.eq("categoria", categoria)
    rows = (q.order("categoria").execute().data) or []
    return {"ok": True, "indicatori": rows, "totale": len(rows)}


@router.post("/indicatori", summary="Aggiungi/aggiorna indicatore")
async def upsert_indicatore(payload: Indicatore, user: UserProfile = Depends(require_user)):
    if payload.categoria not in CATEGORIE:
        raise HTTPException(400, f"Categoria non valida: {CATEGORIE}")
    sb = _sb()
    data = {
        "hotel_id": user.hotel_id, "periodo": (payload.periodo or "").strip(),
        "categoria": payload.categoria, "indicatore": payload.indicatore.strip(),
        "valore": payload.valore, "unita": (payload.unita or "").strip(),
        "note": (payload.note or "").strip(), "updated_at": _now(),
    }
    if payload.id:
        res = sb.table("esg_indicatori").update(data).eq("id", payload.id).eq("hotel_id", user.hotel_id).execute()
        if not res.data:
            raise HTTPException(404, "Indicatore non trovato")
        return {"ok": True, "indicatore": res.data[0]}
    res = sb.table("esg_indicatori").insert(data).execute()
    return {"ok": True, "indicatore": res.data[0] if res.data else data}


@router.delete("/indicatori/{iid}", summary="Elimina indicatore")
async def delete_indicatore(iid: str, user: UserProfile = Depends(require_user)):
    sb = _sb()
    sb.table("esg_indicatori").delete().eq("id", iid).eq("hotel_id", user.hotel_id).execute()
    return {"ok": True}


@router.get("/dashboard", summary="Stato ESG per categoria")
async def dashboard(user: UserProfile = Depends(require_user)):
    sb = _sb()
    rows = (sb.table("esg_indicatori").select("categoria").eq("hotel_id", user.hotel_id).execute().data) or []
    per_cat = {c: sum(1 for r in rows if r.get("categoria") == c) for c in CATEGORIE}
    coperte = sum(1 for c in CATEGORIE if per_cat[c] > 0)
    return {"ok": True, "kpi": {
        "indicatori_totali": len(rows), "categorie_coperte": coperte,
        "categorie_totali": len(CATEGORIE), "per_categoria": per_cat,
        "readiness_pct": round(coperte / len(CATEGORIE) * 100),
    }}


@router.get("/bandi-green", summary="Aree di bando green (ponte BA.IA)")
async def bandi_green(user: UserProfile = Depends(require_user)):
    return {"ok": True, "aree": BANDI_GREEN,
            "nota": "Per i bandi reali e il match sul tuo profilo usa BA.IA (motore finanza agevolata)."}


@router.post("/ai/report", summary="Genera bozza report sostenibilità (AI, human-in-the-loop)")
async def ai_report(user: UserProfile = Depends(require_user)):
    sb = _sb()
    rows = (sb.table("esg_indicatori").select("periodo,categoria,indicatore,valore,unita").eq("hotel_id", user.hotel_id).execute().data) or []
    if not rows:
        return {"ok": True, "stato": "nessun_dato",
                "report_markdown": "Inserisci prima alcuni indicatori (energia, acqua, rifiuti, sociale, governance) per generare la bozza."}
    dati = "\n".join(f"- [{r.get('categoria')}] {r.get('indicatore')}: {r.get('valore','')} {r.get('unita','')} ({r.get('periodo','')})" for r in rows[:60])
    prompt = (
        "Sei un consulente di sostenibilità per l'ospitalità. Genera una BOZZA di REPORT DI "
        "SOSTENIBILITÀ (struttura tipo ESG/CSRD) a partire dai dati forniti. Sezioni: executive summary, "
        "Ambiente (energia/acqua/rifiuti/emissioni), Sociale, Governance, azioni di miglioramento. "
        "Usa SOLO i dati forniti; dove mancano scrivi '[dato da raccogliere]'. NON dichiarare conformità "
        "CSRD: ricorda che i dati vanno verificati/certificati. Markdown.\n\n"
        f"DATI INSERITI:\n{dati}"
    )
    from backend.ai_agents import _ask_claude
    try:
        out = await _ask_claude(prompt, max_tokens=1100)
    except Exception as ex:
        raise HTTPException(502, f"AI non raggiungibile: {ex}")
    return {"ok": True, "report_markdown": (out or "").strip(), "disclaimer": DISCLAIMER}
