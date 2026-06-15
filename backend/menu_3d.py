"""
BAD360.ai — Menu 3D Cliente (agente C7.8 "AI Menu Designer")
Chiude la catena: Menu Engineering (numeri) → C7.7 (ottimizzazione) →
C7.8 (menu digitale 3D rivolto al cliente, QR-ready).

Regole di menu psychology applicate automaticamente al layout:
- STAR per primi in categoria (sweet spot di lettura)
- PUZZLE evidenziati con badge "Consigliato dallo chef"
- DOG esclusi di default (opzione include_dogs)
- Prezzi senza simbolo € (price anchoring)
- Allergeni per piatto (Reg. UE 1169/2011 — compliance integrata)
"""

import os
import json
from typing import List, Dict, Any

import httpx
from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from backend.database import get_supabase
from backend.menu_engineering import DEMO_RECIPES, classify_matrix

router = APIRouter(prefix="/api/menu-3d", tags=["Menu 3D"])

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

CAT_ORDER = ["antipasti", "primi", "secondi", "dessert"]
CLASS_ORDER = {"STAR": 0, "PUZZLE": 1, "PLOWHORSE": 2, "DOG": 3}

DESIGNER_SYSTEM = (
    "Sei l'agente AI Menu Designer di BAD360.ai. Scrivi descrizioni di menu per il "
    "cliente finale di un ristorante italiano di fascia alta. Per ogni piatto: 15-20 "
    "parole, sensoriali e concrete (ingredienti, territorio, tecnica), niente "
    "aggettivi vuoti ('delizioso'), niente prezzi. Rispondi SOLO in JSON: "
    '{"descriptions": {"<nome piatto>": "<descrizione>"}}'
)

_FALLBACK_DESC = {
    "Culurgiones al pomodoro": "Pasta fresca ripiena di patate, pecorino e menta, chiusa a spiga, con pomodoro fresco e basilico.",
    "Fregola con arselle": "Fregola sarda tostata, arselle del golfo e bottarga di muggine, mantecata nel suo brodo.",
    "Porceddu sardo": "Maialino da latte cotto lentamente, pelle croccante e profumo di mirto, come da tradizione.",
    "Tagliata di tonno rosso": "Tonno rosso del Mediterraneo in crosta di sesamo, scottato, con verdure di stagione.",
    "Seadas con miele": "Sfoglia croccante fritta, cuore di pecorino fresco, miele di corbezzolo amaro.",
    "Zuppa gallurese": "Pane raffermo, brodo di pecora e formaggi fusi al forno: il piatto povero più ricco di Gallura.",
    "Insalata di mare": "Polpo e gamberi al vapore, verdure croccanti, agrumi e olio extravergine sardo.",
}


def _get_recipes() -> List[Dict[str, Any]]:
    db = get_supabase()
    rows = (db.table("me_recipes").select("*").execute().data if db else DEMO_RECIPES) or DEMO_RECIPES
    return classify_matrix(rows)


def build_structure(recipes: List[dict], include_dogs: bool = False) -> Dict[str, Any]:
    """Applica le regole di layout C7.8 e restituisce la struttura del menu."""
    items = [r for r in recipes if include_dogs or r["class"] != "DOG"]
    sections = []
    for cat in CAT_ORDER:
        cat_items = [r for r in items if (r.get("category") or "").lower() == cat]
        cat_items.sort(key=lambda r: (CLASS_ORDER.get(r["class"], 9), -r.get("monthly_sales", 0)))
        if not cat_items:
            continue
        sections.append({
            "category": cat.capitalize(),
            "items": [{
                "name": r["name"],
                "price": r["selling_price"],
                "highlight": r["class"] == "PUZZLE",   # badge "Consigliato"
                "star": r["class"] == "STAR",
                "allergens": r.get("allergens") or [],
                "description": r.get("menu_description") or _FALLBACK_DESC.get(r["name"], ""),
            } for r in cat_items],
        })
    excluded = [r["name"] for r in recipes if r["class"] == "DOG" and not include_dogs]
    return {"sections": sections, "excluded_dogs": excluded}


@router.get("/structure")
async def menu_structure(include_dogs: bool = False, ai_descriptions: bool = False):
    """Struttura del menu cliente con regole C7.8. ai_descriptions=true usa Claude."""
    recipes = _get_recipes()
    structure = build_structure(recipes, include_dogs)

    if ai_descriptions and ANTHROPIC_API_KEY:
        try:
            names = [i["name"] for s in structure["sections"] for i in s["items"]]
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={"x-api-key": ANTHROPIC_API_KEY,
                             "anthropic-version": "2023-06-01",
                             "content-type": "application/json"},
                    json={"model": "claude-haiku-4-5-20251001", "max_tokens": 1200,
                          "system": DESIGNER_SYSTEM,
                          "messages": [{"role": "user", "content": json.dumps(names, ensure_ascii=False)}]},
                )
            resp.raise_for_status()
            desc = json.loads(resp.json()["content"][0]["text"]).get("descriptions", {})
            for s in structure["sections"]:
                for i in s["items"]:
                    if i["name"] in desc:
                        i["description"] = desc[i["name"]]
        except Exception:
            pass  # fallback già nelle descrizioni

    return {"agent": "C7.8 AI Menu Designer", **structure}


# ─── Menu 3D immersivo (BAD360_SPLIT/menu3d.html) con dati iniettati ─────────

import pathlib

MENU3D_FILE = pathlib.Path(__file__).resolve().parent.parent / "BAD360_SPLIT" / "menu3d.html"

DISH_STYLES = {
    "pasta": ["culurgion", "pasta", "ravioli", "gnocch", "spaghett", "malloredd"],
    "soup": ["zupp", "fregola", "brodo", "minestra"],
    "fish": ["tonno", "branzino", "orata", "pesce", "tagliata di tonno"],
    "seafood": ["mare", "polpo", "gamber", "arsell", "cozze"],
    "meat": ["porceddu", "maial", "agnello", "manzo", "tagliata di", "carne"],
    "dessert": ["seadas", "dolce", "torta", "gelato", "sorbetto"],
}


def style_for(name: str, category: str) -> str:
    n = (name or "").lower()
    for style, keys in DISH_STYLES.items():
        if any(k in n for k in keys):
            return style
    return "dessert" if (category or "").lower() == "dessert" else "pasta"


@router.get("/html", response_class=HTMLResponse)
async def menu_html(venue: str = "Hotel Baia Sardinia",
                    subtitle: str = "Cucina di Sardegna",
                    include_dogs: bool = False,
                    ai_descriptions: bool = False):
    """Menu cliente 3D immersivo (WebGL), standalone, pronto per QR code."""
    structure = await menu_structure(include_dogs=include_dogs,
                                     ai_descriptions=ai_descriptions)
    for s in structure["sections"]:
        for i in s["items"]:
            i["style"] = style_for(i["name"], s["category"])
    data = {"venue": venue, "subtitle": subtitle, "sections": structure["sections"]}
    html = MENU3D_FILE.read_text(encoding="utf-8")
    inject = "<script>window.__MENU_DATA__=" + json.dumps(data, ensure_ascii=False) + "</script>"
    return html.replace("<script src=", inject + "\n<script src=", 1)
