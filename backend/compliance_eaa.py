"""
BAD360.ai — Accessibilità sito (European Accessibility Act) (niche C4)

Dal giu 2025 siti/booking devono essere accessibili (WCAG 2.1 AA / EN 301 549).
Qui: checklist auto-valutazione dei criteri chiave + AUDIT EURISTICO di un URL
(lang, alt immagini, titolo, label form, h1, viewport) + sintesi AI delle correzioni
prioritarie. Human-in-the-loop: l'audit euristico NON sostituisce un test di accessibilità completo.

Sicurezza: hotel_id dal token. Tabella: eaa_checklist.
"""
from __future__ import annotations
import re
from datetime import datetime, timezone
from typing import Optional

import httpx
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from backend.database import get_supabase
from backend.auth import require_user, UserProfile

router = APIRouter(prefix="/api/eaa", tags=["Accessibilità (EAA)"])
DISCLAIMER = "⚠️ Audit EURISTICO automatico — non sostituisce una verifica WCAG completa con strumenti dedicati e test manuali."

EAA_CRITERI = [
    {"key": "testo_alternativo", "titolo": "Testo alternativo immagini (alt)", "wcag": "1.1.1"},
    {"key": "contrasto", "titolo": "Contrasto colori sufficiente (4.5:1)", "wcag": "1.4.3"},
    {"key": "ridimensionamento", "titolo": "Testo ridimensionabile fino al 200%", "wcag": "1.4.4"},
    {"key": "tastiera", "titolo": "Navigazione completa da tastiera", "wcag": "2.1.1"},
    {"key": "focus_visibile", "titolo": "Indicatore di focus visibile", "wcag": "2.4.7"},
    {"key": "titolo_pagina", "titolo": "Titolo di pagina descrittivo", "wcag": "2.4.2"},
    {"key": "lingua", "titolo": "Lingua della pagina dichiarata (html lang)", "wcag": "3.1.1"},
    {"key": "label_form", "titolo": "Etichette nei campi del form di prenotazione", "wcag": "3.3.2"},
    {"key": "struttura_heading", "titolo": "Struttura titoli corretta (H1/H2)", "wcag": "1.3.1"},
    {"key": "video_sottotitoli", "titolo": "Sottotitoli/alternative per audio-video", "wcag": "1.2.x"},
]


def _sb():
    sb = get_supabase()
    if not sb:
        raise HTTPException(503, "Database non configurato")
    return sb


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@router.get("/checklist", summary="Checklist accessibilità (criteri + stato)")
async def checklist(user: UserProfile = Depends(require_user)):
    sb = _sb()
    saved = {s["criterio_key"]: s for s in (sb.table("eaa_checklist").select("*").eq("hotel_id", user.hotel_id).execute().data) or []}
    out = []
    for c in EAA_CRITERI:
        s = saved.get(c["key"], {})
        out.append({**c, "stato": s.get("stato", "da_verificare"), "note": s.get("note", "")})
    return {"ok": True, "criteri": out}


class CriterioBody(BaseModel):
    criterio_key: str
    stato:        str           # ok | no | na | da_verificare
    note:         Optional[str] = None


@router.put("/criterio", summary="Aggiorna stato criterio")
async def set_criterio(payload: CriterioBody, user: UserProfile = Depends(require_user)):
    if payload.criterio_key not in {c["key"] for c in EAA_CRITERI}:
        raise HTTPException(400, "Criterio sconosciuto")
    if payload.stato not in {"ok", "no", "na", "da_verificare"}:
        raise HTTPException(400, "Stato non valido")
    sb = _sb()
    data = {"hotel_id": user.hotel_id, "criterio_key": payload.criterio_key,
            "stato": payload.stato, "note": (payload.note or "").strip(), "updated_at": _now()}
    exist = (sb.table("eaa_checklist").select("id").eq("hotel_id", user.hotel_id).eq("criterio_key", payload.criterio_key).execute().data) or []
    if exist:
        sb.table("eaa_checklist").update(data).eq("hotel_id", user.hotel_id).eq("criterio_key", payload.criterio_key).execute()
    else:
        sb.table("eaa_checklist").insert(data).execute()
    return {"ok": True}


@router.get("/dashboard", summary="Readiness accessibilità")
async def dashboard(user: UserProfile = Depends(require_user)):
    sb = _sb()
    saved = (sb.table("eaa_checklist").select("stato").eq("hotel_id", user.hotel_id).execute().data) or []
    tot = len(EAA_CRITERI)
    ok = sum(1 for s in saved if s.get("stato") == "ok")
    no = sum(1 for s in saved if s.get("stato") == "no")
    valutati = sum(1 for s in saved if s.get("stato") in ("ok", "no", "na"))
    return {"ok": True, "kpi": {
        "criteri_totali": tot, "conformi": ok, "non_conformi": no, "valutati": valutati,
        "readiness_pct": round(ok / tot * 100) if tot else 0,
    }}


class AuditBody(BaseModel):
    url: str


@router.post("/audit-url", summary="Audit euristico accessibilità di un URL")
async def audit_url(body: AuditBody, user: UserProfile = Depends(require_user)):
    url = (body.url or "").strip()
    if not re.match(r"^https?://", url):
        url = "https://" + url
    if not re.match(r"^https?://[^/\s]+", url):
        raise HTTPException(400, "URL non valido")
    try:
        async with httpx.AsyncClient(timeout=12, follow_redirects=True,
                                     headers={"User-Agent": "Mozilla/5.0 BAD360-A11y-Audit"}) as cli:
            resp = await cli.get(url)
            html = resp.text[:400000]
    except Exception as e:
        raise HTTPException(502, f"Impossibile raggiungere il sito: {e}")

    findings = []
    def add(ok, titolo, dettaglio):
        findings.append({"ok": ok, "titolo": titolo, "dettaglio": dettaglio})

    has_lang = bool(re.search(r"<html[^>]*\blang\s*=", html, re.I))
    add(has_lang, "Lingua dichiarata (html lang)", "Presente" if has_lang else "Manca l'attributo lang su <html> (WCAG 3.1.1)")
    has_title = bool(re.search(r"<title[^>]*>\s*\S", html, re.I))
    add(has_title, "Titolo pagina", "Presente" if has_title else "Manca un <title> descrittivo (WCAG 2.4.2)")
    imgs = re.findall(r"<img\b[^>]*>", html, re.I)
    img_no_alt = sum(1 for t in imgs if not re.search(r"\balt\s*=", t, re.I))
    add(img_no_alt == 0, "Testo alternativo immagini", f"{img_no_alt} immagini su {len(imgs)} senza attributo alt (WCAG 1.1.1)")
    has_h1 = bool(re.search(r"<h1\b", html, re.I))
    add(has_h1, "Struttura heading (H1)", "H1 presente" if has_h1 else "Nessun <h1> trovato (WCAG 1.3.1)")
    has_viewport = bool(re.search(r'<meta[^>]+name=["\']viewport', html, re.I))
    add(has_viewport, "Viewport responsive", "Presente" if has_viewport else "Manca meta viewport (zoom/ridimensionamento)")
    inputs = re.findall(r"<(input|select|textarea)\b[^>]*>", html, re.I)
    real_inputs = [t for t in re.findall(r"<input\b[^>]*>", html, re.I) if not re.search(r'type\s*=\s*["\'](hidden|submit|button)["\']', t, re.I)]
    inp_no_label = sum(1 for t in real_inputs if not re.search(r'(aria-label|aria-labelledby)\s*=', t, re.I))
    if real_inputs:
        add(inp_no_label == 0, "Etichette campi form", f"{inp_no_label}/{len(real_inputs)} campi senza aria-label (verifica <label> associate) (WCAG 3.3.2)")

    passed = sum(1 for f in findings if f["ok"])
    score = round(passed / len(findings) * 100) if findings else 0

    prompt = (
        "Sei un esperto di accessibilità web (WCAG 2.1 AA / European Accessibility Act). "
        "Dato questo audit euristico di un sito ricettivo, spiega in modo semplice le 3-5 correzioni "
        "PRIORITARIE (impatto su EAA) e come farle. Conciso, pratico.\n\n"
        f"URL: {url}\nESITI: " + "; ".join(f"{'OK' if f['ok'] else 'KO'} {f['titolo']}: {f['dettaglio']}" for f in findings)
    )
    ai = None
    try:
        from backend.ai_agents import _ask_claude
        ai = await _ask_claude(prompt, max_tokens=600)
    except Exception:
        ai = None
    return {"ok": True, "url": url, "score": score, "findings": findings,
            "priorita_ai": (ai or "").strip() or None, "disclaimer": DISCLAIMER}
