"""
BAD.S — Modulo Housekeeping & Lavanderia
Fonti: Cora Hospitality (KPI/ruoli), Finlogic EMS (tracciabilità),
       Detergo Industry 5.0 (automazione), B2Scout (costi/camera)
"""

from datetime import datetime, date, timedelta
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


# ── Pydantic Models ───────────────────────────────────────────────────────────

class HKRoomUpdate(BaseModel):
    stato_hk: Optional[str] = None          # pulita | da_pulire | in_pulizia | ispezionata | fuori_servizio
    stato_occupazione: Optional[str] = None  # libera | occupata | in_partenza | bloccata
    priorita: Optional[int] = None
    addetta_id: Optional[str] = None
    note: Optional[str] = None


class HKTaskCreate(BaseModel):
    room_id: str
    tipo: str = "stay_over"                 # check_out | stay_over | deepclean | ispezione
    priorita: int = 2
    assegnato_a: Optional[str] = None
    assegnato_da: Optional[str] = None
    data_pianificata: Optional[str] = None  # ISO date, default oggi
    note: Optional[str] = None


class HKTaskComplete(BaseModel):
    task_id: str
    checklist: List[Dict] = []              # [{voce, fatto, note}]
    lenzuola_cambiate: bool = False
    asciugamani_cambiati: bool = False
    n_set_biancheria: int = 0
    prodotti_usati: List[Dict] = []         # [{supply_id, quantita}]
    punteggio_ispezione: Optional[int] = None
    nc_rilevate: Optional[str] = None
    ispezionato_da: Optional[str] = None
    note: Optional[str] = None


class SupplyMovement(BaseModel):
    supply_id: str
    tipo: str                               # carico | scarico | inventario
    quantita: float
    riferimento: Optional[str] = None
    operatore: Optional[str] = None
    note: Optional[str] = None


class LaundryCycleCreate(BaseModel):
    contract_id: Optional[str] = None
    data_ritiro: Optional[str] = None       # ISO date
    ora_ritiro: Optional[str] = None        # "HH:MM"
    operatore_ritiro: Optional[str] = None
    lenzuola_out: int = 0
    asciugamani_out: int = 0
    accappatoi_out: int = 0
    tovagliato_out: int = 0
    altro_out_kg: float = 0.0
    note: Optional[str] = None


class LaundryCycleDelivery(BaseModel):
    cycle_id: str
    data_consegna: Optional[str] = None
    ora_consegna: Optional[str] = None
    operatore_consegna: Optional[str] = None
    lenzuola_in: int = 0
    asciugamani_in: int = 0
    accappatoi_in: int = 0
    tovagliato_in: int = 0
    pezzi_scartati: int = 0
    nc_rilevate: Optional[str] = None
    costo_ciclo: Optional[float] = None
    note: Optional[str] = None


class LinenParRequest(BaseModel):
    n_camere: int
    set_per_camera: float = 3.0
    rotation_days: int = 2
    safety_factor: float = 1.2


# ── Checklist standard per tipo pulizia ──────────────────────────────────────

CHECKLIST_TEMPLATES = {
    "check_out": [
        {"voce": "Rimozione biancheria usata", "fatto": False, "note": ""},
        {"voce": "Smaltimento rifiuti e svuotamento cestini", "fatto": False, "note": ""},
        {"voce": "Rifacimento letto con biancheria pulita", "fatto": False, "note": ""},
        {"voce": "Pulizia e sanificazione bagno completo", "fatto": False, "note": ""},
        {"voce": "Sostituzione asciugamani e amenities", "fatto": False, "note": ""},
        {"voce": "Aspirazione/lavaggio pavimenti", "fatto": False, "note": ""},
        {"voce": "Spolveratura mobili e superfici", "fatto": False, "note": ""},
        {"voce": "Pulizia specchi e vetri", "fatto": False, "note": ""},
        {"voce": "Controllo minibar e telefono", "fatto": False, "note": ""},
        {"voce": "Apertura/aerazione camera", "fatto": False, "note": ""},
        {"voce": "Ispezione finale e chiusura", "fatto": False, "note": ""},
    ],
    "stay_over": [
        {"voce": "Riordino letto (o cambio su richiesta)", "fatto": False, "note": ""},
        {"voce": "Svuotamento cestini", "fatto": False, "note": ""},
        {"voce": "Pulizia e sanificazione bagno", "fatto": False, "note": ""},
        {"voce": "Sostituzione asciugamani (se necessario)", "fatto": False, "note": ""},
        {"voce": "Rifornimento amenities esaurite", "fatto": False, "note": ""},
        {"voce": "Aspirazione pavimenti", "fatto": False, "note": ""},
        {"voce": "Spolveratura superfici principali", "fatto": False, "note": ""},
    ],
    "deepclean": [
        {"voce": "Rimozione completa biancheria e tende", "fatto": False, "note": ""},
        {"voce": "Sanificazione profonda bagno (incluse fughe)", "fatto": False, "note": ""},
        {"voce": "Lavaggio pareti e soffitto bagno", "fatto": False, "note": ""},
        {"voce": "Pulizia sotto e dietro mobili", "fatto": False, "note": ""},
        {"voce": "Lavaggio/igienizzazione materasso", "fatto": False, "note": ""},
        {"voce": "Pulizia lampadari e applique", "fatto": False, "note": ""},
        {"voce": "Lavaggio finestre interno/esterno", "fatto": False, "note": ""},
        {"voce": "Pulizia radiatori e termostati", "fatto": False, "note": ""},
        {"voce": "Trattamento moquette/parquet", "fatto": False, "note": ""},
        {"voce": "Controllo e pulizia prese elettriche", "fatto": False, "note": ""},
        {"voce": "Rifornimento completo amenities", "fatto": False, "note": ""},
        {"voce": "Ispezione danni e segnalazione manutenzione", "fatto": False, "note": ""},
    ],
    "ispezione": [
        {"voce": "Biancheria pulita e integra", "fatto": False, "note": ""},
        {"voce": "Bagno pulito e rifornito", "fatto": False, "note": ""},
        {"voce": "Pavimenti puliti", "fatto": False, "note": ""},
        {"voce": "Nessun danno visibile ai mobili", "fatto": False, "note": ""},
        {"voce": "Odore neutro / nessun odore sgradevole", "fatto": False, "note": ""},
        {"voce": "Clima/riscaldamento funzionante", "fatto": False, "note": ""},
        {"voce": "Luci funzionanti", "fatto": False, "note": ""},
        {"voce": "Porta e serratura ok", "fatto": False, "note": ""},
    ],
}

# Tempo standard per tipo pulizia (minuti) — fonte: benchmark Cora Hospitality
DURATA_STANDARD = {
    "check_out": 35,
    "stay_over": 20,
    "deepclean": 90,
    "ispezione": 10,
    "fuori_servizio": 15,
}

# Benchmark costo €/camera (B2Scout 2024)
BENCHMARK_COSTO_CAMERA = {
    3: {"hk_totale": 8.50,  "lavanderia": 3.20, "prodotti": 1.80},
    4: {"hk_totale": 11.00, "lavanderia": 4.50, "prodotti": 2.50},
    5: {"hk_totale": 16.00, "lavanderia": 7.00, "prodotti": 4.00},
}


# ── Funzioni di calcolo ───────────────────────────────────────────────────────

def calcola_par_level_biancheria(
    n_camere: int,
    set_per_camera: float = 3.0,
    rotation_days: int = 2,
    safety_factor: float = 1.2
) -> Dict:
    """
    Calcola il par level ottimale per biancheria.
    Formula: (n_camere × pezzi_per_camera × set_rotazione) × safety_factor

    Standard: 3 set in circolazione (1 in camera, 1 in lavanderia, 1 in magazzino)
    Fonti: Detergo Industry 5.0, Cora Hospitality
    """
    # Lenzuola: 2 per letto matrimoniale, ×set_rotazione
    par_lenzuola = round(n_camere * 2 * set_per_camera * safety_factor)
    # Asciugamani: 2 per camera (bagno + viso)
    par_asciugamani = round(n_camere * 2 * set_per_camera * safety_factor)
    # Accappatoi: 1 per camera
    par_accappatoi = round(n_camere * 1 * set_per_camera * safety_factor)
    # Scorta di sicurezza (copre lead time lavanderia)
    scorta_lenzuola = round(n_camere * 2 * rotation_days * 0.3)

    # Punto di riordino = consumo giornaliero × lead time
    consumo_giornaliero_lenzuola = n_camere * 2 * 0.7  # ~70% occupazione media
    punto_riordino = round(consumo_giornaliero_lenzuola * rotation_days)

    return {
        "par_lenzuola": par_lenzuola,
        "par_asciugamani": par_asciugamani,
        "par_accappatoi": par_accappatoi,
        "scorta_sicurezza_lenzuola": scorta_lenzuola,
        "punto_riordino_lenzuola": punto_riordino,
        "parametri": {
            "n_camere": n_camere,
            "set_per_camera": set_per_camera,
            "rotation_days": rotation_days,
            "safety_factor": safety_factor,
        },
        "logica": "PAR = (n_camere × pezzi × set_rotazione) × safety_factor. "
                  "Standard Detergo: 3 set (camera + lavanderia + magazzino).",
    }


def calcola_costo_ciclo_lavanderia(
    lenzuola: int, asciugamani: int, accappatoi: int, tovagliato: int,
    tariffa_lenzuola: float = 0.80,
    tariffa_asciugamani: float = 0.35,
    tariffa_accappatoi: float = 1.20,
    tariffa_tovagliato: float = 0.45,
    scartati: int = 0,
) -> Dict:
    costo = (
        lenzuola * tariffa_lenzuola +
        asciugamani * tariffa_asciugamani +
        accappatoi * tariffa_accappatoi +
        tovagliato * tariffa_tovagliato
    )
    totale_pezzi = lenzuola + asciugamani + accappatoi + tovagliato
    tasso_scarto = round(scartati / totale_pezzi * 100, 1) if totale_pezzi > 0 else 0
    return {
        "costo_totale": round(costo, 2),
        "totale_pezzi": totale_pezzi,
        "tasso_scarto_pct": tasso_scarto,
        "dettaglio": {
            "lenzuola": round(lenzuola * tariffa_lenzuola, 2),
            "asciugamani": round(asciugamani * tariffa_asciugamani, 2),
            "accappatoi": round(accappatoi * tariffa_accappatoi, 2),
            "tovagliato": round(tovagliato * tariffa_tovagliato, 2),
        },
    }


def kpi_produttivita_hk(
    camere_pulite: int,
    ore_lavorate: float,
    camere_nc: int = 0,
    costo_totale: float = 0.0,
    stelle: int = 4,
) -> Dict:
    """
    Calcola KPI produttività HK con benchmark.
    Benchmark Cora Hospitality: 3* = 4 cam/h, 4* = 3 cam/h, 5* = 2 cam/h
    """
    BENCHMARK = {3: 4.0, 4: 3.0, 5: 2.0}
    benchmark_camere_ora = BENCHMARK.get(stelle, 3.0)

    camere_ora = round(camere_pulite / ore_lavorate, 2) if ore_lavorate > 0 else 0
    tasso_nc = round(camere_nc / camere_pulite * 100, 1) if camere_pulite > 0 else 0
    costo_camera = round(costo_totale / camere_pulite, 2) if camere_pulite > 0 else 0

    delta_vs_benchmark = round(camere_ora - benchmark_camere_ora, 2)
    performance_pct = round(camere_ora / benchmark_camere_ora * 100, 1) if benchmark_camere_ora > 0 else 0

    return {
        "camere_ora": camere_ora,
        "tasso_nc_pct": tasso_nc,
        "costo_camera_euro": costo_camera,
        "benchmark": {
            "stelle": stelle,
            "target_camere_ora": benchmark_camere_ora,
            "delta_vs_target": delta_vs_benchmark,
            "performance_pct": performance_pct,
            "valutazione": (
                "sopra_benchmark" if delta_vs_benchmark > 0 else
                "in_linea" if abs(delta_vs_benchmark) < 0.3 else
                "sotto_benchmark"
            ),
        },
        "fonte_benchmark": "Cora Hospitality — Hotel Management Standards 2024",
    }
