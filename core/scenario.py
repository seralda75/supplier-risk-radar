"""Simulador "¿Y si…?": ¿qué pasaría si ocurriera este evento?

    interpret(texto) -> Scenario          (el LLM solo traduce el texto a un escenario estructurado)
    simulate(scenario) -> ScenarioImpact  (el cálculo lo hace el código)

Reparto de papeles, igual que en el juez de noticias:
- El LLM convierte "¿y si se inunda Gujarat 3 semanas?" en {regions: [Gujarat], duración: 3 semanas,
  event_type: natural_disaster}, validado con Pydantic (categorías y materiales solo de la lista real).
  No calcula nada ni elige proveedores.
- El código busca los proveedores con el mismo diccionario geográfico que los candidatos de las noticias
  (matching._supplier_reasons: ciudad, región, río, ruta, país), filtra por categoría o material y aplica
  la cuenta atrás (TTS − TTR) y la acción recomendada de cada proveedor.

El usuario ve y puede corregir el escenario interpretado antes de calcular. Los escenarios de ejemplo
se interpretan una vez con scripts/build_scenarios.py y se guardan en data/scenarios.json, así que el
simulador funciona sin Ollama con esos ejemplos.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, replace
from datetime import datetime
from functools import lru_cache
from typing import Literal, Optional, get_args

import pandas as pd
from pydantic import BaseModel, Field, field_validator

from .actions import supplier_action
from .config import DATA_DIR, LLM_MODEL, TRAIN_XLSX
from .countdown import Countdown, countdown
from .matching import _supplier_reasons, normalize
from .rules import TRANSPORT_EVENTS
from .schemas import EVENT_LABELS_ES, EventType, NewsAssessment, RecoveryUnit, to_days
from .suppliers import COUNTRY_ALIASES, MATERIAL_ALIASES, NON_PHYSICAL_CATEGORIES, Supplier, load_suppliers

EXAMPLES_PATH = DATA_DIR / "scenarios.json"

CATEGORIES = ("API", "Excipients", "Primary packaging", "Secondary packaging", "Single-use bioprocess",
              "Lab reagents", "Logistics", "Services", "Chemicals", "Consumables")
Category = Literal[CATEGORIES]
# Un escenario siempre es un evento negativo: sin "positive_news" ni "not_relevant"
SCENARIO_EVENTS = tuple(e for e in get_args(EventType) if e not in ("positive_news", "not_relevant"))
ScenarioEvent = Literal[SCENARIO_EVENTS]

# Escenarios de ejemplo (los del enunciado + los eventos típicos de la sección 8.1 de CLAUDE.md)
EXAMPLES = [
    "¿Y si China restringe la exportación de API?",
    "¿Y si se inunda Gujarat 3 semanas?",
    "¿Y si cierra el puerto de Rotterdam 10 días?",
    "¿Y si el Rin queda sin navegación durante un mes?",
    "¿Y si un tifón paraliza Shanghái y el este de China dos semanas?",
    "¿Y si hay una huelga de transportistas en España de 5 días?",
    "¿Y si un terremoto en Taiwán para la producción 6 semanas?",
]

SYSTEM = """You turn a what-if supply-chain scenario, written in Spanish by a buyer at Helixa Pharmaceuticals, into a \
structured scope. You do not compute impacts and you do not choose suppliers.

1. event_type: flood, typhoon, hurricane, earthquake, wildfire -> natural_disaster; port closure, river \
not navigable, blocked road or sea route -> logistics_disruption; strike -> labour_strike; export ban or \
restriction -> export_restriction; plant fire or explosion -> fire_plant_incident; power or water cut -> \
utility_outage; bankruptcy -> financial_distress; cyberattack -> cyber_incident; regulator stopping \
production -> regulatory_action; war or sanctions -> geopolitical_conflict.
2. Write every place name in English, translating the Spanish words literally (España -> Spain, Rin -> \
Rhine, Shanghái -> Shanghai, "el este de China" -> eastern China, "el sur de Taiwán" -> southern Taiwan).
3. Places: only the places named in the scenario, as precise as written. Do NOT add the country of a \
region or city ("Gujarat" -> regions [Gujarat], countries []). countries: countries named. regions: \
states, provinces, named regions, rivers, seas, straits or sea routes. cities: cities or ports ("el \
puerto de Rotterdam" -> Rotterdam).
4. categories and materials restrict WHICH suppliers are hit. Fill them only if the scenario names a type \
of supply or a specific material. If a specific material is named, fill only materials, copied as \
written, and leave categories empty. Leave both empty when the event hits everything in the place: a \
flood, a typhoon, an earthquake, a port closure or a transport strike affects every supplier located there \
(transportistas or camioneros on strike is NOT the Logistics category).
5. duration_value and duration_unit: the duration exactly as written ("3 semanas" -> 3 and weeks, "10 \
días" -> 10 and days, "un mes" -> 1 and months); both null if no duration is given.
6. title: a short title in Spanish for the scenario.

Examples:
"¿Y si un tifón paraliza Osaka y su puerto 2 semanas?" -> natural_disaster, countries [], regions [], \
cities [Osaka], categories [], materials [], 2 weeks.
"¿Y si India prohíbe exportar paracetamol?" -> export_restriction, countries [India], regions [], cities \
[], categories [], materials [paracetamol], no duration.
"¿Y si se bloquea el canal de Suez un mes?" -> logistics_disruption, countries [], regions [Suez Canal], \
cities [], categories [], materials [], 1 month."""

# Nombres de país en español (el usuario escribe en español; el diccionario geográfico está en inglés)
SPANISH_COUNTRIES = {
    "espana": "Spain", "alemania": "Germany", "suiza": "Switzerland", "irlanda": "Ireland", "italia": "Italy",
    "noruega": "Norway", "taiwan": "Taiwan", "estados unidos": "USA", "ee uu": "USA", "eeuu": "USA",
    "polonia": "Poland", "japon": "Japan", "mexico": "Mexico", "belgica": "Belgium", "singapur": "Singapore",
    "brasil": "Brazil", "marruecos": "Morocco", "paises bajos": "Netherlands", "holanda": "Netherlands",
    "india": "India", "china": "China", "vietnam": "Vietnam", "puerto rico": "Puerto Rico (USA)",
}


def _canonical_country(name: str) -> str:
    """'Chinese', 'PRC', 'Países Bajos' -> nombre de la hoja Suppliers. Un país sin proveedores se deja
    tal cual (no coincidirá con ninguno y se avisa al usuario)."""
    n = normalize(name).strip()
    if n in SPANISH_COUNTRIES:
        return SPANISH_COUNTRIES[n]
    for country, aliases in COUNTRY_ALIASES.items():
        if n in {normalize(x).strip() for x in (country, *aliases)}:
            return country
    return name.strip()


def _clean(values: list[str]) -> list[str]:
    out: list[str] = []
    for v in values:
        v = (v or "").strip()
        if v and v.lower() not in {x.lower() for x in out}:
            out.append(v)
    return out


# Palabras que tienen que aparecer en el texto del usuario para aceptar una categoría o un material que
# propone el LLM (comienzo de palabra, sin tildes). Misma idea que las duraciones ancladas al texto del
# juez: un modelo de 7B a veces añade restricciones que nadie ha pedido ("huelga de transportistas" ->
# categoría Logistics, que dejaría fuera a todos los fabricantes de la zona).
CATEGORY_TERMS = {
    "API": ["api", "apis", "principio activo", "principios activos", "ingrediente activo", "ingredientes activos",
            "active ingredient"],
    "Excipients": ["excipiente", "excipient"],
    "Primary packaging": ["envase", "primary packaging"],
    "Secondary packaging": ["envase", "cartonaje", "secondary packaging"],
    "Single-use bioprocess": ["bioproceso", "un solo uso", "single use", "bioprocess"],
    "Lab reagents": ["reactivo", "reagent"],
    "Logistics": ["logistic", "operador logistico", "operadores logisticos", "flete", "freight"],
    "Services": ["servicio", "service"],
    "Chemicals": ["quimic", "chemical"],
    "Consumables": ["consumible", "consumable"],
}
MATERIAL_TERMS = {
    "Amoxicillin trihydrate": ["amoxicilina"], "Metformin hydrochloride": ["metformina"],
    "Atorvastatin calcium": ["atorvastatina"], "Paracetamol": ["paracetamol"],
    "Monoclonal antibody drug substance": ["anticuerpo"], "Microcrystalline cellulose": ["celulosa"],
    "Pregelatinised starch": ["almidon"], "Lipid nanoparticle components": ["nanoparticula", "lipid"],
    "Magnesium stearate": ["estearato"], "Type I glass vials": ["vial"], "Rubber stoppers": ["tapon"],
    "Aluminium blister foil": ["blister", "aluminio"], "Pre-filled syringe barrels": ["jeringa"],
    "Folding cartons": ["caja", "estuche", "cartonaje"], "Serialised labels": ["etiqueta"],
    "Patient information leaflets": ["prospecto"], "Bioreactor bags": ["biorreactor"],
    "Sterile filters": ["filtro"], "Chromatography resins": ["resina", "cromatografia"],
    "Quality control assay kits": ["kit", "ensayo"], "Hard gelatin capsules": ["capsula"],
    "Process solvents": ["disolvente"], "Cleanroom garments": ["sala limpia"],
    "Temperature-controlled road freight (EU)": ["refrigerado", "temperatura controlada", "cadena de frio"],
    "Asia to Europe sea freight": ["maritimo", "naviera"], "Asia to Europe rail freight": ["ferrocarril", "tren"],
    "Batch release testing laboratory": ["liberacion de lotes", "laboratorio"],
    "Track-and-trace serialisation platform": ["serializacion", "trazabilidad"],
}


def _has_term(terms: list[str], norm: str) -> bool:
    """¿Aparece alguno de los términos al comienzo de una palabra del texto normalizado?"""
    return any(f" {normalize(t).strip()}" in norm for t in terms)


def _canonical_material(name: str) -> str:
    """'viales de vidrio', 'glass vials' o 'Type I glass vials' -> 'Type I glass vials'. Lo que no está en
    el catálogo se deja tal cual (anchor_to_text lo descarta y se avisa al usuario)."""
    norm = normalize(name)
    for m in MATERIAL_ALIASES:
        if normalize(m) == norm or _has_term(MATERIAL_TERMS.get(m, []) + MATERIAL_ALIASES[m], norm):
            return m
    return name.strip()


class Scenario(BaseModel):
    """Escenario estructurado. Las listas vacías significan "sin restricción" en ese eje."""
    title: str = Field(..., description="Short Spanish title of the scenario")
    event_type: ScenarioEvent = Field(..., description="Kind of event")
    countries: list[str] = Field(..., description="Countries named in the scenario, in English")
    regions: list[str] = Field(..., description="States, provinces, regions, rivers, seas or sea routes, in English")
    cities: list[str] = Field(..., description="Cities or ports named in the scenario, in English")
    categories: list[Category] = Field(..., description="Supplier categories hit; empty if every supplier in "
                                                        "the place is hit")
    # Texto libre (no una lista cerrada): con 30 opciones el modelo rellenaba materiales al azar.
    # El código lo traduce al nombre del catálogo (_canonical_material).
    materials: list[str] = Field(..., description="Specific materials named in the scenario, copied as "
                                                  "written (viales, paracetamol); empty if none")
    duration_value: Optional[float] = Field(..., ge=0, description="Duration number exactly as written; null "
                                                                   "if none")
    duration_unit: Optional[RecoveryUnit] = Field(..., description="Unit of duration_value; null if none")

    @field_validator("countries")
    @classmethod
    def _countries(cls, v: list[str]) -> list[str]:
        return _clean([_canonical_country(x) for x in v])

    @field_validator("regions", "cities")
    @classmethod
    def _places(cls, v: list[str]) -> list[str]:
        return _clean(v)

    @field_validator("categories")
    @classmethod
    def _dedupe(cls, v: list[str]) -> list[str]:
        return list(dict.fromkeys(v))

    @field_validator("materials")
    @classmethod
    def _materials(cls, v: list[str]) -> list[str]:
        return _clean([_canonical_material(x) for x in v])

    @property
    def duration_days(self) -> int | None:
        """Días convertidos por código (el LLM no hace la cuenta), como en el juez de noticias."""
        return to_days(self.duration_value, self.duration_unit)

    @property
    def places(self) -> list[str]:
        return self.countries + self.regions + self.cities


def anchor_to_text(sc: Scenario, text: str) -> tuple[Scenario, list[str]]:
    """Quita las categorías y materiales que no se pueden justificar con el texto. Devuelve los descartes."""
    norm = normalize(text)
    # Un "material" que en realidad es una categoría ("API") pasa a categorías
    proposed_cats, proposed_mats = list(sc.categories), []
    for m in sc.materials:
        cat = next((c for c, terms in CATEGORY_TERMS.items()
                    if normalize(m) in {normalize(t) for t in (c, *terms) if t != "envase"}), None)
        if cat and m not in MATERIAL_ALIASES:
            proposed_cats += [cat] if cat not in proposed_cats else []
        else:
            proposed_mats.append(m)
    cats = [c for c in proposed_cats if _has_term(CATEGORY_TERMS.get(c, []), norm)]
    mats = [m for m in proposed_mats if m in MATERIAL_ALIASES
            and _has_term(MATERIAL_TERMS.get(m, []) + MATERIAL_ALIASES[m], norm)]
    dropped = [f"categoría {c}" for c in proposed_cats if c not in cats] + \
              [f"material {m}" + ("" if m in MATERIAL_ALIASES else " (no está en el catálogo de Helixa)")
               for m in proposed_mats if m not in mats]
    return sc.model_copy(update={"categories": cats, "materials": mats}), dropped


def interpret(text: str, model: str = LLM_MODEL) -> tuple[Scenario, list[str]]:
    """Texto libre -> (escenario estructurado, restricciones descartadas por no estar en el texto).
    Requiere Ollama."""
    from . import llm
    sc = llm.extract(f"Scenario: {text.strip()}", Scenario, system=SYSTEM, model=model)
    return anchor_to_text(sc, text)


# ---------------------------------------------------------------------------
# Escenarios de ejemplo precalculados (funcionan sin Ollama)
# ---------------------------------------------------------------------------

def save_examples(items: list[dict], model: str) -> None:
    EXAMPLES_PATH.write_text(json.dumps({"model": model, "generated": datetime.now().isoformat(timespec="seconds"),
                                         "examples": items}, ensure_ascii=False, indent=2), encoding="utf-8")


def load_examples() -> list[dict]:
    """[{text, scenario, dropped}] con el escenario ya validado; vacío si aún no se han generado."""
    if not EXAMPLES_PATH.exists():
        return []
    data = json.loads(EXAMPLES_PATH.read_text(encoding="utf-8"))
    return [{"text": e["text"], "scenario": Scenario.model_validate(e["scenario"]), "dropped": e.get("dropped", [])}
            for e in data["examples"]]


# ---------------------------------------------------------------------------
# Cálculo (solo código)
# ---------------------------------------------------------------------------

@dataclass
class ScopeHit:
    supplier: Supplier
    reasons: list[str] = field(default_factory=list)     # p. ej. "region 'gujarat'", "categoría API"


@dataclass
class ScenarioImpact:
    scenario: Scenario
    hits: list[ScopeHit]
    countdowns: list[Countdown]
    unmatched_places: list[str]              # lugares sin ningún proveedor (o mal escritos)
    excluded: list[str]                      # proveedores de la zona descartados (categoría, material, servicio)
    note: str = ""

    @property
    def supplier_ids(self) -> list[str]:
        return [h.supplier.id for h in self.hits]

    @property
    def spend_exposed(self) -> float:
        return sum(h.supplier.annual_spend_eur or 0 for h in self.hits)

    @property
    def spend_at_risk(self) -> float:
        """Gasto de los proveedores con déficit (rotura prevista o sin inventario y con corte)."""
        sup = load_suppliers()
        return sum(sup[c.supplier_id].annual_spend_eur or 0 for c in self.countdowns if c.deficit_days > 0)

    def actions(self) -> list[tuple[str, str]]:
        sup = load_suppliers()
        cds = sorted(self.countdowns, key=lambda c: (c.inventory_days is None, c.margin_days))
        return [(c.supplier_id, supplier_action(c, sup[c.supplier_id])) for c in cds]

    def materials_table(self) -> list[dict]:
        return _materials_table(self)

    def products_table(self) -> list[dict]:
        return _products_table(self)


def _place_reasons(s: Supplier, place: str) -> list[str]:
    """¿Está el proveedor en este lugar? Mismo diccionario que los candidatos de las noticias."""
    return [f"{r.level} '{r.alias}'" for r in _supplier_reasons(s, place, normalize(place))
            if r.kind in ("location", "route")]


def scope(sc: Scenario) -> tuple[list[ScopeHit], list[str], list[str]]:
    """(proveedores afectados con sus motivos, lugares sin proveedores, descartados por categoría/material)."""
    sup = load_suppliers()
    by_place: dict[str, list[str]] = {}
    unmatched = []
    for place in sc.places:
        found = False
        for s in sup.values():
            reasons = _place_reasons(s, place)
            if reasons:
                by_place.setdefault(s.id, []).extend(r for r in reasons if r not in by_place.get(s.id, []))
                found = True
        if not found:
            unmatched.append(place)

    # Igual que en los candidatos de las noticias: si en un país ya hay coincidencias concretas (ciudad,
    # región, río), las que solo coinciden por ese país sobran ("Shanghái y China" no es toda China)
    only_country = {i for i, rs in by_place.items() if all(r.startswith("country ") for r in rs)}
    specific = {sup[i].country for i in by_place if i not in only_country}
    by_place = {i: rs for i, rs in by_place.items() if not (i in only_country and sup[i].country in specific)}

    # Un material es más concreto que una categoría: si hay materiales, mandan ellos
    content = bool(sc.categories or sc.materials)
    pool = by_place if sc.places else ({i: [] for i in sup} if content else {})
    hits, excluded = [], []
    for sid, reasons in pool.items():
        s = sup[sid]
        why = list(reasons)
        if sc.materials:
            if s.material not in sc.materials:
                excluded.append(sid)
                continue
            why.append(f"material {s.material}")
        elif sc.categories:
            if s.category not in sc.categories:
                excluded.append(sid)
                continue
            why.append(f"categoría {s.category}")
        # Igual que en las noticias: un evento de transporte no afecta a servicios (software, laboratorio)
        if sc.event_type in TRANSPORT_EVENTS and s.category in NON_PHYSICAL_CATEGORIES:
            excluded.append(sid)
            continue
        hits.append(ScopeHit(s, why))
    hits.sort(key=lambda h: h.supplier.id)
    # Sin lugar, «descartados» serían todos los demás proveedores: solo se listan los de la zona
    return hits, unmatched, sorted(excluded) if sc.places else []


def as_assessment(sc: Scenario, ids: list[str]) -> NewsAssessment:
    """El escenario con la forma de un veredicto, para reutilizar la cuenta atrás tal cual."""
    return NewsAssessment(evidence=sc.title, affected_ids=ids, event_type=sc.event_type, is_risk=True, severity=4,
                          stops_supply_soon=True, recovery_value=sc.duration_days,
                          recovery_unit="days" if sc.duration_days is not None else None, confidence=1.0)


def simulate(sc: Scenario) -> ScenarioImpact:
    hits, unmatched, excluded = scope(sc)
    note = ""
    if not sc.places and not (sc.categories or sc.materials):
        note = "El escenario no indica ningún lugar, categoría ni material: no se puede delimitar."
    cds = countdown(as_assessment(sc, [h.supplier.id for h in hits]), urgent=True) if hits else []
    # La duración viene del escenario, no de una noticia
    cds = [replace(c, ttr_basis="duración del escenario") if not c.ttr_estimated else c for c in cds]
    return ScenarioImpact(sc, hits, cds, unmatched, excluded, note)


@lru_cache(maxsize=1)
def load_materials() -> pd.DataFrame:
    return pd.read_excel(TRAIN_XLSX, sheet_name="Materials")


def _materials_table(imp: ScenarioImpact) -> list[dict]:
    """Por material: qué proveedores (principal y alternativo de la hoja Materials) quedan afectados y el
    peor margen entre ellos. Los dos tienen gasto e inventario propios, así que cuentan los dos."""
    cd = {c.supplier_id: c for c in imp.countdowns}
    rows = []
    for m in load_materials().itertuples(index=False):
        alt = None if pd.isna(m.Alternate_Supplier_ID) else m.Alternate_Supplier_ID
        hit = [c for c in (cd.get(m.Primary_Supplier_ID), cd.get(alt)) if c is not None]
        if not hit:
            continue
        w = min(hit, key=lambda c: c.margin_days)
        rows.append({"material_id": m.Material_ID, "material": m.Material, "primary": m.Primary_Supplier_ID,
                     "primary_hit": m.Primary_Supplier_ID in cd, "alternate": alt or "", "alternate_hit": alt in cd,
                     "margin": w.margin_days, "deficit": w.deficit_days, "status": w.status,
                     "products": [x.strip() for x in str(m.Used_In_Products).split(";") if x.strip()],
                     "monthly": f"{m.Monthly_Requirement:g} {m.Unit}"})
    return sorted(rows, key=lambda r: r["margin"])


def _products_table(imp: ScenarioImpact) -> list[dict]:
    """Por producto: materiales afectados y el peor margen (el material que antes se acaba)."""
    prods: dict[str, dict] = {}
    for m in _materials_table(imp):
        for p in m["products"]:
            row = prods.setdefault(p, {"product": p, "materials": [], "margin": m["margin"], "status": m["status"],
                                       "deficit": m["deficit"]})
            row["materials"].append(m["material"])
            if m["margin"] < row["margin"]:
                row.update(margin=m["margin"], status=m["status"], deficit=m["deficit"])
    return sorted(prods.values(), key=lambda r: r["margin"])


def label(sc: Scenario) -> str:
    dur = f"{sc.duration_days} días" if sc.duration_days is not None else "duración sin indicar"
    return f"{EVENT_LABELS_ES.get(sc.event_type, sc.event_type)} · {dur}"
