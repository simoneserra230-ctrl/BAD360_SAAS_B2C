"""
BAD.S Platform — Supabase Client
Gestione connessione e query database
"""

import os
from typing import Optional, Dict, Any, List
from datetime import datetime

try:
    from supabase import create_client, Client
    SUPABASE_AVAILABLE = True
except ImportError:
    SUPABASE_AVAILABLE = False

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")

_client: Optional[Any] = None


def get_client():
    """Restituisce istanza Supabase (singleton)"""
    global _client
    if not SUPABASE_AVAILABLE:
        raise RuntimeError("Libreria supabase non installata. Esegui: pip install supabase")
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise RuntimeError("SUPABASE_URL o SUPABASE_SERVICE_KEY non configurati nel .env")
    if _client is None:
        _client = create_client(SUPABASE_URL, SUPABASE_KEY)
    return _client


# ─── HACCP Temperature Helpers ───────────────────────────────────────────────

async def save_temperature_log(data: Dict) -> Dict:
    """Salva log temperatura HACCP su Supabase"""
    try:
        client = get_client()
        result = client.table("haccp_temperature").insert(data).execute()
        return {"ok": True, "data": result.data}
    except Exception as e:
        return {"ok": False, "error": str(e)}


async def get_temperature_history(hotel_id: str, zona: str = None, limit: int = 100) -> List[Dict]:
    """Recupera storico temperature"""
    try:
        client = get_client()
        query = client.table("haccp_temperature").select("*").eq("hotel_id", hotel_id)
        if zona:
            query = query.eq("zona", zona)
        result = query.order("timestamp", desc=True).limit(limit).execute()
        return result.data or []
    except Exception as e:
        return []


async def get_active_alerts(hotel_id: str) -> List[Dict]:
    """Recupera alert temperatura attivi"""
    try:
        client = get_client()
        result = (
            client.table("haccp_temperature")
            .select("*")
            .eq("hotel_id", hotel_id)
            .eq("alert", True)
            .gte("timestamp", (datetime.utcnow().replace(hour=0, minute=0, second=0)).isoformat())
            .order("timestamp", desc=True)
            .execute()
        )
        return result.data or []
    except Exception as e:
        return []


# ─── Fornitori Helpers ────────────────────────────────────────────────────────

async def get_fornitori(hotel_id: str, categoria: str = None) -> List[Dict]:
    """Recupera lista fornitori"""
    try:
        client = get_client()
        query = client.table("fornitori").select("*").eq("hotel_id", hotel_id).eq("stato", "attivo")
        if categoria:
            query = query.eq("categoria", categoria)
        result = query.order("ragione_sociale").execute()
        return result.data or []
    except Exception as e:
        return []


async def save_fornitore(data: Dict) -> Dict:
    """Salva/aggiorna fornitore"""
    try:
        client = get_client()
        if data.get("id"):
            result = client.table("fornitori").update(data).eq("id", data["id"]).execute()
        else:
            result = client.table("fornitori").insert(data).execute()
        return {"ok": True, "data": result.data}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ─── Inventario Helpers ───────────────────────────────────────────────────────

async def get_scorte_critiche(hotel_id: str) -> List[Dict]:
    """Recupera articoli sotto il punto di riordino"""
    try:
        client = get_client()
        # Articoli dove giacenza < punto_riordino
        result = (
            client.table("inventario")
            .select("*")
            .eq("hotel_id", hotel_id)
            .execute()
        )
        items = result.data or []
        # Filtra in Python (Supabase non supporta column comparison direttamente)
        critici = [
            item for item in items
            if item.get("giacenza_attuale", 0) <= (item.get("punto_riordino") or 0)
        ]
        return sorted(critici, key=lambda x: x.get("giacenza_attuale", 0))
    except Exception as e:
        return []


# ─── ESG Helpers ─────────────────────────────────────────────────────────────

async def save_esg_report(data: Dict) -> Dict:
    """Salva report ESG (upsert per anno)"""
    try:
        client = get_client()
        result = (
            client.table("esg_reports")
            .upsert(data, on_conflict="hotel_id,anno")
            .execute()
        )
        return {"ok": True, "data": result.data}
    except Exception as e:
        return {"ok": False, "error": str(e)}


async def get_esg_history(hotel_id: str) -> List[Dict]:
    """Recupera storico report ESG"""
    try:
        client = get_client()
        result = (
            client.table("esg_reports")
            .select("anno,co2_kg_camera,energia_kwh_camera,acqua_litri_ospite,rifiuti_riciclo_pct,stato")
            .eq("hotel_id", hotel_id)
            .order("anno", desc=True)
            .execute()
        )
        return result.data or []
    except Exception as e:
        return []


# ─── Alias richiesto da non_conformita.py e tracciabilita.py ─────────────────
def get_supabase():
    """Alias di get_client() — restituisce il client Supabase o None se non configurato."""
    try:
        return get_client()
    except RuntimeError:
        return None
