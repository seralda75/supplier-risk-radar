"""Fichas de proveedores + diccionario geográfico.

Una ficha une la hoja Suppliers con Materials (qué material, para qué productos, si es
proveedor único, quién es el alternativo, criticidad, inventario...). El LLM razona con
estos datos de negocio reales en lugar de con su "memoria".

El diccionario geográfico se construye a partir de las 40 ciudades de los proveedores y de
conocimiento geográfico general (estado/provincia, regiones, ríos, si es ciudad portuaria),
NO a partir de las noticias de validación o test. Permite detectar riesgos por ubicación:
"inundaciones en Gujarat" -> proveedores de Ahmedabad y Vadodara.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache

import pandas as pd

from .config import TRAIN_XLSX

# ---------------------------------------------------------------------------
# Diccionario geográfico por ciudad de proveedor
#   aliases: nombres de la ciudad (con variantes ortográficas)
#   regions: estado/provincia y regiones con nombre propio en las que está la ciudad
#   rivers:  ríos navegables en los que está la ciudad (el Main de Mainz no se incluye:
#            "main" es una palabra común en inglés y daría falsos positivos)
#   port:    ciudad con puerto propio (huelgas o cierres "del puerto de X")
# ---------------------------------------------------------------------------
CITY_GEO: dict[str, dict] = {
    "Hyderabad": dict(aliases=["Hyderabad"], regions=["Telangana", "Deccan", "South India", "southern India"]),
    "Ahmedabad": dict(aliases=["Ahmedabad", "Amdavad"], regions=["Gujarat", "western India"], rivers=["Sabarmati"]),
    "Vadodara": dict(aliases=["Vadodara", "Baroda"], regions=["Gujarat", "western India"]),
    "Bengaluru": dict(aliases=["Bengaluru", "Bangalore"], regions=["Karnataka", "South India", "southern India"]),
    "Taizhou": dict(aliases=["Taizhou"], regions=["Zhejiang", "eastern China", "east China", "Yangtze River Delta"]),
    "Hangzhou": dict(aliases=["Hangzhou"], regions=["Zhejiang", "eastern China", "east China", "Yangtze River Delta"]),
    "Shanghai": dict(aliases=["Shanghai"], regions=["eastern China", "east China", "Yangtze River Delta"],
                     rivers=["Yangtze", "Huangpu"], port=True),
    "Wuhan": dict(aliases=["Wuhan"], regions=["Hubei", "central China"], rivers=["Yangtze"]),
    "Xi'an": dict(aliases=["Xi'an", "Xian"], regions=["Shaanxi", "northwest China", "northwestern China"]),
    "Basel": dict(aliases=["Basel", "Basle"], regions=["northwestern Switzerland"], rivers=["Rhine"], port=True),
    "Zurich": dict(aliases=["Zurich"], regions=["northern Switzerland"]),
    "Cork": dict(aliases=["Cork"], regions=["County Cork", "Munster", "southern Ireland"], port=True),
    "Dublin": dict(aliases=["Dublin"], regions=["Leinster", "eastern Ireland"], port=True),
    "Ludwigshafen": dict(aliases=["Ludwigshafen"], regions=["Rhineland-Palatinate", "Rhine-Neckar"], rivers=["Rhine"]),
    "Mainz": dict(aliases=["Mainz"], regions=["Rhineland-Palatinate", "Rhine-Main"], rivers=["Rhine"]),
    "Cologne": dict(aliases=["Cologne", "Koln"], regions=["North Rhine-Westphalia", "Rhineland"], rivers=["Rhine"]),
    "Darmstadt": dict(aliases=["Darmstadt"], regions=["Hesse", "Rhine-Main"]),
    "Milan": dict(aliases=["Milan", "Milano"], regions=["Lombardy", "Lombardia", "northern Italy", "Po Valley"]),
    "Bergamo": dict(aliases=["Bergamo"], regions=["Lombardy", "Lombardia", "northern Italy"]),
    "Valencia": dict(aliases=["Valencia"], regions=["Valencian Community", "eastern Spain"], port=True),
    "Barcelona": dict(aliases=["Barcelona"], regions=["Catalonia", "Catalunya", "northeastern Spain"], port=True),
    "Madrid": dict(aliases=["Madrid"], regions=["central Spain"]),
    "Oslo": dict(aliases=["Oslo"], regions=["eastern Norway"], port=True),
    "Kaohsiung": dict(aliases=["Kaohsiung"], regions=["southern Taiwan", "south Taiwan"], port=True),
    "Hsinchu": dict(aliases=["Hsinchu"], regions=["northern Taiwan", "north Taiwan"]),
    "Lancaster": dict(aliases=["Lancaster"], regions=["Pennsylvania", "US Northeast", "northeastern US"]),
    "Boston": dict(aliases=["Boston"], regions=["Massachusetts", "New England", "US Northeast", "northeastern US"],
                   port=True),
    "San Juan": dict(aliases=["San Juan"], regions=["Puerto Rico", "Caribbean"], port=True),
    "Lodz": dict(aliases=["Lodz"], regions=["central Poland"]),
    "Osaka": dict(aliases=["Osaka"], regions=["Kansai", "western Japan"], port=True),
    "Monterrey": dict(aliases=["Monterrey"], regions=["Nuevo Leon", "northern Mexico"]),
    "Antwerp": dict(aliases=["Antwerp", "Antwerpen"], regions=["Flanders"], rivers=["Scheldt"], port=True),
    "Singapore": dict(aliases=["Singapore"], regions=["Southeast Asia", "Strait of Malacca"], port=True),
    "Sao Paulo": dict(aliases=["Sao Paulo"], regions=["southeastern Brazil"]),
    "Ho Chi Minh City": dict(aliases=["Ho Chi Minh City", "Saigon", "HCMC"], regions=["southern Vietnam"], port=True),
    "Tangier": dict(aliases=["Tangier", "Tangiers", "Tanger"], regions=["northern Morocco", "Strait of Gibraltar"],
                    port=True),
    "Rotterdam": dict(aliases=["Rotterdam"], regions=["South Holland", "Rhine-Meuse delta"], port=True),
}

# Nombres y gentilicios de país. Los alias en MAYÚSCULAS (US, USA, PRC) se comparan
# distinguiendo mayúsculas para no confundir "US" con el pronombre "us".
COUNTRY_ALIASES: dict[str, list[str]] = {
    "India": ["India", "Indian"],
    "China": ["China", "Chinese", "PRC"],
    "Switzerland": ["Switzerland", "Swiss"],
    "Ireland": ["Ireland", "Irish"],
    "Germany": ["Germany", "German"],
    "Italy": ["Italy", "Italian"],
    "Spain": ["Spain", "Spanish"],
    "Norway": ["Norway", "Norwegian"],
    "Taiwan": ["Taiwan", "Taiwanese"],
    "USA": ["United States", "USA", "US", "U.S.", "American"],
    "Puerto Rico (USA)": ["Puerto Rico", "Puerto Rican"],
    "Poland": ["Poland", "Polish"],
    "Japan": ["Japan", "Japanese"],
    "Mexico": ["Mexico", "Mexican"],
    "Belgium": ["Belgium", "Belgian"],
    "Singapore": ["Singapore"],
    "Brazil": ["Brazil", "Brazilian"],
    "Vietnam": ["Vietnam", "Vietnamese", "Viet Nam"],
    "Morocco": ["Morocco", "Moroccan"],
    "Netherlands": ["Netherlands", "Dutch", "Holland"],
}

# Rutas o corredores de los que depende un proveedor logístico (su "zona" no es su ciudad):
# una noticia sobre el mar Rojo afecta a la agencia marítima Asia-Europa aunque esté en Singapur.
SUPPLIER_ROUTES: dict[str, list[str]] = {
    "S032": ["Red Sea", "Suez Canal", "Suez", "Bab el-Mandeb", "Cape of Good Hope", "Strait of Malacca",
             "Asia to Europe", "Asia-Europe", "container lines", "container line", "shipping lines",
             "container shipping", "sea freight", "ocean freight"],
    "S033": ["China-Europe rail", "China-Europe Railway", "rail freight", "Trans-Siberian", "Kazakhstan",
             "Belarus"],
    "S031": ["Gotthard", "Brenner", "Alpine pass", "Alpine passes", "Alpine tunnel"],
}

# Sinónimos de cada material (para "restricciones a la exportación de paracetamol", "escasez de viales"...)
MATERIAL_ALIASES: dict[str, list[str]] = {
    "Amoxicillin trihydrate": ["amoxicillin", "amoxycillin"],
    "Metformin hydrochloride": ["metformin"],
    "Atorvastatin calcium": ["atorvastatin"],
    "Paracetamol": ["paracetamol", "acetaminophen"],
    "Monoclonal antibody drug substance": ["monoclonal antibody", "monoclonal antibodies"],
    "Microcrystalline cellulose": ["microcrystalline cellulose", "MCC"],
    "Pregelatinised starch": ["pregelatinised starch", "pregelatinized starch", "starch"],
    "Lipid nanoparticle components": ["lipid nanoparticle", "lipid nanoparticles", "LNP"],
    "Magnesium stearate": ["magnesium stearate"],
    "Type I glass vials": ["glass vials", "vials", "pharmaceutical glass"],
    "Rubber stoppers": ["rubber stoppers", "stoppers"],
    "Aluminium blister foil": ["blister foil", "aluminium foil", "aluminum foil"],
    "Pre-filled syringe barrels": ["pre-filled syringe", "prefilled syringe", "syringe barrels", "syringes"],
    "Folding cartons": ["folding cartons", "cartons"],
    "Serialised labels": ["serialised labels", "serialized labels"],
    "Patient information leaflets": ["patient information leaflets", "leaflets"],
    "Bioreactor bags": ["bioreactor bags", "bioreactor"],
    "Sterile filters": ["sterile filters", "sterile filter"],
    "Chromatography resins": ["chromatography resin", "chromatography resins"],
    "Quality control assay kits": ["assay kits", "quality control kits"],
    "Hard gelatin capsules": ["gelatin capsules", "hard capsules"],
    "Process solvents": ["process solvents", "solvents"],
    "Cleanroom garments": ["cleanroom garments", "cleanroom apparel"],
    "Temperature-controlled road freight (EU)": ["temperature-controlled", "cold chain", "refrigerated trucks"],
    "Asia to Europe sea freight": [],
    "Asia to Europe rail freight": [],
    "Batch release testing laboratory": ["batch release", "release testing"],
    "Track-and-trace serialisation platform": ["serialisation", "serialization", "track-and-trace"],
}

# Palabras de cada categoría (para noticias que hablan de "ingredientes farmacéuticos" sin nombrar el material)
CATEGORY_ALIASES: dict[str, list[str]] = {
    "API": ["active ingredient", "active ingredients", "active pharmaceutical ingredient",
            "active pharmaceutical ingredients", "pharmaceutical ingredients", "API", "APIs", "drug substance"],
    "Excipients": ["excipient", "excipients"],
    "Primary packaging": ["primary packaging", "pharmaceutical packaging"],
    "Secondary packaging": ["secondary packaging", "printed packaging"],
    "Single-use bioprocess": ["single-use", "bioprocess"],
    "Lab reagents": ["reagents", "lab reagents"],
    "Logistics": ["freight", "logistics", "shipping"],
    "Chemicals": ["chemicals", "chemical"],
    "Services": [],
    "Consumables": ["consumables"],
}

# Categorías que no mueven bienes físicos: una huelga de transporte no les afecta
NON_PHYSICAL_CATEGORIES = {"Services"}


@dataclass
class Supplier:
    """Ficha de un proveedor con todo lo que el negocio necesita para decidir."""
    id: str
    name: str
    category: str
    material: str
    country: str
    city: str
    annual_spend_eur: float
    share_of_category_pct: float
    single_source: bool
    alternate_id: str | None
    alternate_name: str | None
    lead_time_days: float | None
    inventory_cover_days: float | None
    criticality: str
    quality_score: float | None
    products: list[str] = field(default_factory=list)
    material_ids: list[str] = field(default_factory=list)
    role: str = ""                       # "primario", "alternativo" o "" (sin material en la hoja Materials)
    monthly_requirement: str = ""        # p. ej. "3500 kg"
    geo: dict = field(default_factory=dict)

    @property
    def physical(self) -> bool:
        return self.category not in NON_PHYSICAL_CATEGORIES

    def card(self) -> str:
        """Ficha en una línea para el prompt del LLM."""
        inv = "n/a" if self.inventory_cover_days is None else f"{self.inventory_cover_days:.0f}"
        alt = f"{self.alternate_id} {self.alternate_name}" if self.alternate_id else "none"
        prods = ", ".join(self.products) or "n/a"
        return (f"{self.id} {self.name} | {self.category}: {self.material} | {self.city}, {self.country} | "
                f"single source: {'yes' if self.single_source else 'no'} | approved alternate: {alt} | "
                f"criticality: {self.criticality} | inventory cover days: {inv} | used in: {prods}")


def _opt(v):
    return None if pd.isna(v) else v


@lru_cache(maxsize=1)
def load_suppliers() -> dict[str, Supplier]:
    """Lee Suppliers + Materials del Excel de entrenamiento y devuelve {id: Supplier}."""
    sup = pd.read_excel(TRAIN_XLSX, sheet_name="Suppliers").rename(
        columns={"Share_of_Category_Spend_%": "Share_pct"})
    mat = pd.read_excel(TRAIN_XLSX, sheet_name="Materials")
    names = dict(zip(sup.Supplier_ID, sup.Supplier_Name))

    out: dict[str, Supplier] = {}
    for r in sup.itertuples(index=False):
        primary = mat[mat.Primary_Supplier_ID == r.Supplier_ID]
        alternate = mat[mat.Alternate_Supplier_ID == r.Supplier_ID]
        rows = pd.concat([primary, alternate])
        products: list[str] = []
        for p in rows.Used_In_Products.dropna():
            products += [x.strip() for x in str(p).split(";") if x.strip() and x.strip() not in products]
        role = "primario" if len(primary) else ("alternativo" if len(alternate) else "")
        monthly = "; ".join(f"{m.Monthly_Requirement:g} {m.Unit}" for m in rows.itertuples())
        alt_id = _opt(r.Approved_Alternate_ID)
        out[r.Supplier_ID] = Supplier(
            id=r.Supplier_ID, name=r.Supplier_Name, category=r.Category, material=r.Material_Supplied,
            country=r.Country, city=r.City, annual_spend_eur=float(r.Annual_Spend_EUR),
            share_of_category_pct=float(r.Share_pct), single_source=r.Single_Source == "Y",
            alternate_id=alt_id, alternate_name=names.get(alt_id) if alt_id else None,
            lead_time_days=_opt(r.Lead_Time_Days), inventory_cover_days=_opt(r.Inventory_Cover_Days),
            criticality=r.Criticality, quality_score=_opt(r.Quality_Score), products=products,
            material_ids=rows.Material_ID.tolist(), role=role, monthly_requirement=monthly,
            geo=CITY_GEO.get(r.City, {"aliases": [r.City], "regions": []}),
        )
    return out


def suppliers_df() -> pd.DataFrame:
    """Las fichas como DataFrame (para el panel y los informes)."""
    return pd.DataFrame([{k: v for k, v in s.__dict__.items() if k != "geo"} for s in load_suppliers().values()])


def suppliers_in_place(place: str) -> list[Supplier]:
    """Proveedores en una ciudad, región, río o país (para el bot: '¿qué tenemos en Gujarat?')."""
    p = place.strip().lower()
    hits = []
    for s in load_suppliers().values():
        names = ([s.city, s.country] + s.geo.get("aliases", []) + s.geo.get("regions", [])
                 + s.geo.get("rivers", []) + COUNTRY_ALIASES.get(s.country, []))
        if any(p == n.lower() for n in names):
            hits.append(s)
    return hits
