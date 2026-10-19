"""Nombres en español para las vistas de negocio (panel, plan de acción, bot).

Los datos del reto están en inglés ("HX-mAb 100 mg injection", "Bioreactor bags", "Puerto Rico (USA)").
El director de compras lee el panel en español y sin jerga: estas tablas solo traducen etiquetas,
no cambian ningún dato ni ninguna decisión.
"""
from __future__ import annotations

COUNTRY_ES = {
    "India": "India", "China": "China", "Switzerland": "Suiza", "Ireland": "Irlanda", "Germany": "Alemania",
    "Italy": "Italia", "Spain": "España", "Norway": "Noruega", "Taiwan": "Taiwán", "USA": "EE. UU.",
    "Puerto Rico (USA)": "Puerto Rico", "Poland": "Polonia", "Japan": "Japón", "Mexico": "México",
    "Belgium": "Bélgica", "Singapore": "Singapur", "Brazil": "Brasil", "Vietnam": "Vietnam",
    "Morocco": "Marruecos", "Netherlands": "Países Bajos",
}

CITY_ES = {"Cologne": "Colonia", "Milan": "Milán", "Zurich": "Zúrich", "Basel": "Basilea",
           "Antwerp": "Amberes", "Tangier": "Tánger", "Sao Paulo": "São Paulo", "Xi'an": "Xi'an",
           "Ho Chi Minh City": "Ciudad Ho Chi Minh", "Mainz": "Maguncia", "Ludwigshafen": "Ludwigshafen",
           "Rotterdam": "Róterdam", "Singapore": "Singapur", "Osaka": "Osaka"}

MATERIAL_ES = {
    "Amoxicillin trihydrate": "amoxicilina trihidrato", "Metformin hydrochloride": "metformina clorhidrato",
    "Atorvastatin calcium": "atorvastatina cálcica", "Paracetamol": "paracetamol",
    "Monoclonal antibody drug substance": "principio activo de anticuerpo monoclonal",
    "Microcrystalline cellulose": "celulosa microcristalina", "Pregelatinised starch": "almidón pregelatinizado",
    "Lipid nanoparticle components": "componentes de nanopartículas lipídicas",
    "Magnesium stearate": "estearato de magnesio", "Type I glass vials": "viales de vidrio tipo I",
    "Rubber stoppers": "tapones de caucho", "Aluminium blister foil": "lámina de aluminio para blíster",
    "Pre-filled syringe barrels": "cuerpos de jeringa precargada", "Folding cartons": "estuches plegables",
    "Serialised labels": "etiquetas serializadas", "Patient information leaflets": "prospectos",
    "Bioreactor bags": "bolsas de biorreactor de un solo uso", "Sterile filters": "filtros esterilizantes",
    "Chromatography resins": "resinas de cromatografía", "Quality control assay kits": "kits de control de calidad",
    "Hard gelatin capsules": "cápsulas duras de gelatina", "Process solvents": "disolventes de proceso",
    "Cleanroom garments": "ropa de sala limpia",
    "Temperature-controlled road freight (EU)": "transporte por carretera a temperatura controlada (UE)",
    "Asia to Europe sea freight": "transporte marítimo Asia-Europa",
    "Asia to Europe rail freight": "transporte ferroviario Asia-Europa",
    "Batch release testing laboratory": "laboratorio de liberación de lotes",
    "Track-and-trace serialisation platform": "plataforma de serialización y trazabilidad",
}

# Regiones y ríos del diccionario geográfico (core/suppliers.py) que tienen nombre propio en español
ZONE_ES = {"Rhine": "Rin", "Rhineland-Palatinate": "Renania-Palatinado", "Lombardy": "Lombardía",
           "Yangtze": "Yangtsé", "North Rhine-Westphalia": "Renania del Norte-Westfalia", "Hesse": "Hesse",
           "South Holland": "Holanda Meridional", "Flanders": "Flandes", "Catalonia": "Cataluña",
           "Valencian Community": "Comunidad Valenciana", "Telangana": "Telangana", "Zhejiang": "Zhejiang",
           "Gujarat": "Gujarat", "Pennsylvania": "Pensilvania", "Massachusetts": "Massachusetts"}

CATEGORY_ES = {
    "API": "Principios activos", "Excipients": "Excipientes", "Primary packaging": "Envase primario",
    "Secondary packaging": "Envase secundario", "Single-use bioprocess": "Bioproceso de un solo uso",
    "Lab reagents": "Reactivos de laboratorio", "Logistics": "Logística", "Services": "Servicios",
    "Chemicals": "Químicos", "Consumables": "Consumibles",
}

CRITICALITY_ES = {"High": "alta", "Medium": "media", "Low": "baja"}

_PRODUCT_FORMS = [(" injection", " inyectable"), (" tablets", " comprimidos"), (" capsules", " cápsulas")]


def product_es(name: str) -> str:
    """'HX-mAb 100 mg injection' -> 'HX-mAb 100 mg inyectable'; 'HX-RSV mRNA vaccine' -> 'vacuna HX-RSV (ARNm)'."""
    if name == "HX-RSV mRNA vaccine":
        return "vacuna HX-RSV (ARNm)"
    for en, es in _PRODUCT_FORMS:
        if name.endswith(en):
            return name[: -len(en)] + es
    return name


def product_short(name: str) -> str:
    """Nombre corto del medicamento: 'HX-mAb 100 mg injection' -> 'HX-mAb'."""
    return name.split()[0]


def place_es(city: str, country: str) -> str:
    return f"{CITY_ES.get(city, city)}, {COUNTRY_ES.get(country, country)}"


def material_es(material: str) -> str:
    return MATERIAL_ES.get(material, material)


def short_supplier(name: str) -> str:
    """Nombre sin la forma jurídica ni la última palabra genérica, para los gráficos."""
    for suffix in (" Ltd", " GmbH", " SpA", " AG", " AS", " Inc.", " Co.", " SL", " Sp. z o.o."):
        if name.endswith(suffix):
            name = name[: -len(suffix)]
    return name
